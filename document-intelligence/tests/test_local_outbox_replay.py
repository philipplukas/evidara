from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from document_intelligence.jobs.local_outbox_replay import LocalOutboxReplayer, main
from support import build_bundle_event, build_manifest_payload


def _write_local_outbox_fixture(root: Path) -> Path:
    outbox = root / "event-outbox"
    bundle_dir = outbox / "artifact-bundle-available"
    bundle_dir.mkdir(parents=True)
    artifact_path = root / "document.html"
    manifest_path = root / "bundle-manifest.json"
    artifact_path.write_text(
        "<html><head><title>Replay Doc</title></head><body><h1>Replay Doc</h1><p>Body</p></body></html>",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(build_manifest_payload(str(artifact_path), artifact_role="primary_document")),
        encoding="utf-8",
    )
    event = build_bundle_event(str(manifest_path))
    event["event_id"] = "evt_local_outbox_replay_test"
    (bundle_dir / "evt_local_outbox_replay_test.json").write_text(
        json.dumps(event),
        encoding="utf-8",
    )
    return outbox


class _ProjectionHandler(BaseHTTPRequestHandler):
    posts: list[tuple[str, dict]] = []

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.posts.append((self.path, payload))
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"applied"}')

    def log_message(self, format: str, *args: object) -> None:
        del format, args


class ProjectionServer:
    def __enter__(self) -> str:
        _ProjectionHandler.posts = []
        self.server = HTTPServer(("127.0.0.1", 0), _ProjectionHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @staticmethod
    def posts() -> list[tuple[str, dict]]:
        return list(_ProjectionHandler.posts)


class LocalOutboxReplayTests(unittest.TestCase):
    def test_replay_processes_bundle_posts_projection_and_withdraws_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, ProjectionServer() as api_url:
            root = Path(temp_dir)
            outbox = _write_local_outbox_fixture(root)
            env = {"DI_SURFACES_ROOT_URI": str(root / "surfaces")}
            with patch.dict(os.environ, env, clear=False):
                summary = LocalOutboxReplayer(
                    outbox_dir=outbox,
                    legal_search_api_url=api_url,
                ).replay()

            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["processed"], 1)
            posts = ProjectionServer.posts()
            self.assertEqual(
                [path for path, _ in posts],
                [
                    "/v1/projections/events/document-processed",
                    "/v1/projections/events/document-withdrawn",
                ],
            )
            marker = json.loads((outbox / "processed" / "evt_local_outbox_replay_test.json").read_text())
            self.assertEqual(marker["cleanup_status"], "withdrawn")
            self.assertEqual(marker["document_withdrawn_event"]["payload"]["search_disposition"], "remove")

    def test_keep_then_withdraw_only_reuses_processed_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, ProjectionServer() as api_url:
            root = Path(temp_dir)
            outbox = _write_local_outbox_fixture(root)
            replayer = LocalOutboxReplayer(outbox_dir=outbox, legal_search_api_url=api_url)
            with patch.dict(os.environ, {"DI_SURFACES_ROOT_URI": str(root / "surfaces")}, clear=False):
                summary = replayer.replay(keep_projections=True)
                withdraw_summary = replayer.withdraw_marked_projections()

            self.assertEqual(summary["processed"], 1)
            self.assertEqual(withdraw_summary["withdrawn"], 1)
            self.assertEqual(
                [path for path, _ in ProjectionServer.posts()],
                [
                    "/v1/projections/events/document-processed",
                    "/v1/projections/events/document-withdrawn",
                ],
            )

    def test_cli_requires_legal_search_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code = main(["--outbox-dir", temp_dir])

        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
