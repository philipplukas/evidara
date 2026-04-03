#!/usr/bin/env python3
"""Verify OpenSearch runtime readiness (auth, index create, alias cutover)."""

from __future__ import annotations

import argparse
import base64
import json
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class Client:
    endpoint: str
    auth_header: str
    insecure: bool

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = None
        headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url=f"{self.endpoint}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        context = None
        if self.insecure:
            context = ssl._create_unverified_context()

        try:
            with urllib.request.urlopen(req, context=context) as response:
                raw = response.read().decode("utf-8").strip()
                return {} if not raw else json.loads(raw)
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed ({exc.code}): {message}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc.reason}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify OpenSearch auth and alias operations against a runtime endpoint."
    )
    parser.add_argument("--endpoint", required=True, help="OpenSearch endpoint, for example https://10.0.1.20:9200")
    parser.add_argument("--username", required=True, help="OpenSearch username")
    parser.add_argument("--password", required=True, help="OpenSearch password")
    parser.add_argument("--index", default="evidara-runtime-smoke-index", help="Index name used for verification")
    parser.add_argument("--alias", default="evidara-runtime-smoke-alias", help="Alias name used for verification")
    parser.add_argument(
        "--keep-index",
        action="store_true",
        help="Do not delete the verification index at the end.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS certificate verification (only for controlled bootstrap testing).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    endpoint = args.endpoint.rstrip("/")
    token = base64.b64encode(f"{args.username}:{args.password}".encode("utf-8")).decode("utf-8")
    client = Client(endpoint=endpoint, auth_header=f"Basic {token}", insecure=args.insecure)

    try:
        info = client.request("GET", "/")
        cluster_name = info.get("cluster_name", "<unknown>")
        version = info.get("version", {}).get("number", "<unknown>")
        print(f"Auth OK. cluster={cluster_name} version={version}")

        client.request(
            "PUT",
            f"/{args.index}",
            payload={"settings": {"number_of_shards": 1, "number_of_replicas": 1}},
        )
        print(f"Index created: {args.index}")

        client.request(
            "POST",
            "/_aliases",
            payload={"actions": [{"add": {"index": args.index, "alias": args.alias}}]},
        )
        alias_result = client.request("GET", f"/_alias/{args.alias}")
        if args.index not in alias_result:
            raise RuntimeError(f"Alias verification failed for {args.alias}")
        print(f"Alias verified: {args.alias} -> {args.index}")

        if not args.keep_index:
            client.request("DELETE", f"/{args.index}")
            print(f"Index deleted: {args.index}")

        print("OpenSearch runtime verification completed successfully.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
