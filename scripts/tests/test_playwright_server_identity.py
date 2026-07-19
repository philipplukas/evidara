"""Self-test for scripts/e2e/playwright-server-identity.mjs.

This guard exists because four separate lanes in one day reported results that
described the WRONG SERVER: one attached to another lane's dev server on :3000,
another bound to a stale Docker container on :3101 and reproduced a bug it had
already fixed. A guard against that class of problem is only worth anything if
it demonstrably FIRES — a silent guard is indistinguishable from no guard, and
worse, because it is trusted.

So, like scripts/tests/test_check_js_workspace_hygiene.py, these tests assert
BOTH directions: the check passes against a server presenting this run's nonce,
and fails — loudly, naming the likely cause — against every way a foreign
server can occupy the port.
"""

import json
import shutil
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "scripts" / "e2e" / "playwright-server-identity.mjs"

RUN_ID = "run-under-test"
SURFACE = "legal-search-frontend"


class _IdentityHandler(BaseHTTPRequestHandler):
    """Stands in for a Next surface's /api/e2e-identity route."""

    payload: object = None
    status: int = 200

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/api/e2e-identity":
            self.send_error(404)
            return
        if self.status != 200:
            self.send_response(self.status)
            self.end_headers()
            self.wfile.write(b"<!DOCTYPE html><html>a stale build</html>")
            return
        body = json.dumps(self.payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):  # silence the test output
        return


class _FakeServer:
    """A server occupying a port, presenting whatever identity we tell it to."""

    def __init__(self, payload, status=200):
        handler = type(
            "Handler", (_IdentityHandler,), {"payload": payload, "status": status}
        )
        self.httpd = HTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def _run_check(url, surface=SURFACE, expected_run_id=RUN_ID, enforce=True):
    """Drive the real assertServerIdentity export; return (exit_code, output)."""
    script = f"""
import {{ assertServerIdentity }} from {json.dumps(str(MODULE))};
await assertServerIdentity(
  {{ url: {json.dumps(url)}, surface: {json.dumps(surface)} }},
  {{ expectedRunId: {json.dumps(expected_run_id)}, enforceRunId: {json.dumps(enforce)}, timeoutMs: 5000 }},
);
console.log("IDENTITY_OK");
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
    )
    return proc.returncode, proc.stdout + proc.stderr


@unittest.skipIf(shutil.which("node") is None, "node is not installed")
class PlaywrightServerIdentityTest(unittest.TestCase):
    def test_passes_against_the_server_this_run_started(self):
        """The healthy direction: right app, right nonce."""
        payload = {"surface": SURFACE, "runId": RUN_ID, "pid": 1, "startedAt": "now"}
        with _FakeServer(payload) as server:
            code, output = _run_check(server.url)
        self.assertEqual(code, 0, output)
        self.assertIn("IDENTITY_OK", output)

    def test_fires_on_a_stale_server_of_the_same_app(self):
        """Right app, WRONG nonce — a stale container or a leaked dev server.

        This is the case unique ports cannot catch, and the one that made a
        lane re-report a bug it had already fixed.
        """
        payload = {
            "surface": SURFACE,
            "runId": "run-from-yesterday",
            "pid": 2,
            "startedAt": "yesterday",
        }
        with _FakeServer(payload) as server:
            code, output = _run_check(server.url)
        self.assertEqual(code, 1, output)
        self.assertIn("DIFFERENT SERVER", output)
        self.assertIn("STALE DOCKER CONTAINER", output)
        self.assertIn("run-from-yesterday", output)

    def test_fires_when_the_port_serves_something_without_an_identity_route(self):
        """A build predating the guard, or an unrelated process on the port."""
        with _FakeServer(None, status=404) as server:
            code, output = _run_check(server.url)
        self.assertEqual(code, 1, output)
        self.assertIn("NOT THIS TEST RUN'S SERVER", output)

    def test_fires_when_the_port_serves_a_different_surface(self):
        """Two surfaces configured onto one port — the :3000 collision."""
        payload = {
            "surface": "platform-control-admin",
            "runId": RUN_ID,
            "pid": 3,
            "startedAt": "now",
        }
        with _FakeServer(payload) as server:
            code, output = _run_check(server.url)
        self.assertEqual(code, 1, output)
        self.assertIn("WRONG APPLICATION", output)

    def test_fires_when_nothing_is_listening(self):
        with _FakeServer({"surface": SURFACE, "runId": RUN_ID}) as server:
            dead_url = server.url  # captured, then the server is torn down
        code, output = _run_check(dead_url)
        self.assertEqual(code, 1, output)
        self.assertIn("Could not reach the identity endpoint", output)

    def test_external_targets_verify_surface_but_not_nonce(self):
        """A deployed environment cannot be stamped; the surface still is."""
        payload = {"surface": SURFACE, "runId": "whatever-is-deployed", "pid": 4}
        with _FakeServer(payload) as server:
            code, output = _run_check(server.url, enforce=False)
        self.assertEqual(code, 0, output)
        self.assertIn("run id NOT enforced", output)


@unittest.skipIf(shutil.which("node") is None, "node is not installed")
class ReuseDefaultTest(unittest.TestCase):
    def test_reuse_is_opt_in(self):
        """`reuseExistingServer: true` is what let a run attach to another
        lane's server. It must be off unless explicitly requested."""
        script = f"""
import {{ reuseExistingServer }} from {json.dumps(str(MODULE))};
console.log(JSON.stringify({{ value: reuseExistingServer() }}));
"""
        for env_value, expected in [(None, False), ("1", True), ("true", True), ("0", False)]:
            with self.subTest(env=env_value):
                env = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
                if env_value is not None:
                    env["PLAYWRIGHT_REUSE_SERVER"] = env_value
                proc = subprocess.run(
                    ["node", "--input-type=module", "-e", script],
                    capture_output=True,
                    text=True,
                    cwd=REPO_ROOT,
                    env=env,
                    timeout=60,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(json.loads(proc.stdout)["value"], expected)


if __name__ == "__main__":
    unittest.main()
