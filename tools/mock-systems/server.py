"""Mock business systems for running the companion's golden sets.

Stands in for the helpdesk, CRM, ledger, HR platform, scheduler, document
store and messaging service a recipe talks to, so an n8n build can be run
against its golden set without a real account anywhere. Generic by design:
any system and collection name works, and every call is recorded so a test
can assert on what the workflow did, not only on the final state.

    GET    /health
    POST   /_reset                      body {"seed": {system: {collection: {id: record}}}}
    GET    /_state                      whole store
    GET    /_calls                      every call since the last reset
    POST   /_fail                       body {"method", "path", "status", "times"}: inject failures
    POST   /anthropic/v1/messages        pass-through to the Anthropic Messages API (the recipe's own
                                         key travels in x-api-key), so tests can inject an AI failure
    GET    /{system}/{collection}        list records (query params filter on top-level fields;
                                         _wrap=1 returns {"items": [...]}, as most real APIs do)
    GET    /{system}/{collection}/{id}   one record, 404 if absent
    POST   /{system}/{collection}        create; id from body["id"] or generated
    PUT    /{system}/{collection}/{id}   replace (create if absent)
    PATCH  /{system}/{collection}/{id}   merge top-level fields, 404 if absent
    DELETE /{system}/{collection}/{id}   remove

Standard library only. Not for production use: no authentication, in memory.
"""

from __future__ import annotations

import itertools
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LOCK = threading.Lock()
STORE: dict = {}
CALLS: list = []
FAILS: list = []
IDS = itertools.count(1)


def reset(seed: dict | None) -> None:
    global IDS
    STORE.clear()
    CALLS.clear()
    FAILS.clear()
    IDS = itertools.count(1)
    for system, collections in (seed or {}).items():
        for collection, records in collections.items():
            STORE.setdefault(system, {})[collection] = {str(k): v for k, v in records.items()}


class Handler(BaseHTTPRequestHandler):
    server_version = "companion-mocks/1"

    def log_message(self, *args) -> None:  # keep container logs quiet
        pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return None
        raw = self.rfile.read(n)
        try:
            return json.loads(raw)
        except ValueError:
            return raw.decode("utf-8", "replace")

    def _send(self, status: int, payload) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _injected_failure(self, method: str, path: str) -> int | None:
        for f in FAILS:
            if f["method"] == method and path.startswith(f["path"]) and f["times"] > 0:
                f["times"] -= 1
                return int(f["status"])
        return None

    def _handle(self, method: str) -> None:
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        body = self._body() if method in ("POST", "PUT", "PATCH") else None
        with LOCK:
            if url.path == "/health":
                return self._send(200, {"ok": True})
            if url.path == "/_reset" and method == "POST":
                reset((body or {}).get("seed") if isinstance(body, dict) else None)
                return self._send(200, {"ok": True})
            if url.path == "/_state":
                return self._send(200, STORE)
            if url.path == "/_calls":
                return self._send(200, CALLS)
            if url.path == "/_fail" and method == "POST":
                FAILS.append({"method": body["method"].upper(), "path": body["path"],
                              "status": int(body.get("status", 500)), "times": int(body.get("times", 1))})
                return self._send(200, {"ok": True})

            CALLS.append({"method": method, "path": url.path, "query": url.query, "body": body})
            status = self._injected_failure(method, url.path)
            if status:
                return self._send(status, {"error": "injected failure"})
            if url.path == "/anthropic/v1/messages" and method == "POST":
                return self._forward_anthropic(body)
            if len(parts) < 2:
                return self._send(404, {"error": "use /{system}/{collection}[/{id}]"})
            system, collection = parts[0], parts[1]
            rid = "/".join(parts[2:]) or None
            table = STORE.setdefault(system, {}).setdefault(collection, {})

            if method == "GET" and rid is None:
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                wrap = q.pop("_wrap", None)
                rows = [r for r in table.values() if all(str(r.get(k)) == v for k, v in q.items())]
                return self._send(200, {"items": rows} if wrap else rows)
            if method == "GET":
                return self._send(200, table[rid]) if rid in table else self._send(404, {"error": "not found"})
            if method == "POST" and rid is None:
                rec = dict(body or {}) if isinstance(body, dict) else {"value": body}
                rec.setdefault("id", str(next(IDS)))
                table[str(rec["id"])] = rec
                return self._send(201, rec)
            if method == "PUT" and rid:
                rec = dict(body or {})
                rec["id"] = rid
                table[rid] = rec
                return self._send(200, rec)
            if method == "PATCH" and rid:
                if rid not in table:
                    return self._send(404, {"error": "not found"})
                table[rid].update(body or {})
                return self._send(200, table[rid])
            if method == "DELETE" and rid:
                table.pop(rid, None)
                return self._send(204, {})
            return self._send(405, {"error": "unsupported"})

    def _forward_anthropic(self, body) -> None:
        import urllib.error
        import urllib.request
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
            headers={"content-type": "application/json", "x-api-key": self.headers.get("x-api-key", ""),
                     "anthropic-version": self.headers.get("anthropic-version", "2023-06-01")})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return self._send(r.status, json.loads(r.read()))
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read())
            except ValueError:
                payload = {"error": "upstream error"}
            return self._send(e.code, payload)

    def do_GET(self): self._handle("GET")
    def do_POST(self): self._handle("POST")
    def do_PUT(self): self._handle("PUT")
    def do_PATCH(self): self._handle("PATCH")
    def do_DELETE(self): self._handle("DELETE")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
