#!/usr/bin/env python3
"""Build a recipe's n8n workflow, run its golden set, and write the results.

    python3 tools/n8n/golden.py R11.2            build, test, write report
    python3 tools/n8n/golden.py R11.2 --build    only write recipes/R11.2/n8n/workflow.json

Needs the companion test stack (tools/stack/): n8n 2.42.7 on N8N_URL, the mock
systems on MOCKS_URL, and the Postgres container for the key log, decision log
and exception queue. Environment:

    N8N_URL (default http://127.0.0.1:5679)   N8N_API_KEY
    MOCKS_URL (default http://127.0.0.1:5680)  MOCKS_INTERNAL_URL (default http://mocks:8080)
    PG_CREDENTIAL_ID   ANTHROPIC_CREDENTIAL_ID (recipes with an AI step)
    PG_CONTAINER (default companion-postgres)

What is committed (n8n/workflow.json) is the builder's output with the reader's
defaults in the Config node and placeholder credentials. What is tested is the
same workflow with three changes only: Config points at the mock systems, the
credentials are real, and each schedule trigger becomes a webhook the runner
can call. The report lists the n8n version, the date and every case's result.

tests.json shape (recipes/<ID>/n8n/tests.json):
{
  "config": {"<Config field>": "<test value; {mocks} expands to MOCKS_INTERNAL_URL>"},
  "seed":   {"<system>": {"<collection>": {"<id>": {...}}}},
  "cases": [{
    "case": "Normal", "row": 1, "input": "what the golden row says",
    "seed": {... merged over the base seed ...},
    "fail": [{"method": "PATCH", "path": "/sharepoint/requests/REQ-1", "status": 500}],
    "trigger": [{"webhook": "<path>", "body": {...}}, ...]   # several = several events
    "expect": [
      {"mock": "sharepoint/requests/REQ-1", "field": "status", "equals": "checked; to approval"},
      {"mock": "messaging/messages", "count": 1},
      {"calls": "PATCH /sharepoint/requests/REQ-1", "count": 1},
      {"sql": "select count(*) from exception_queue", "equals": "0"}
    ]
  }]
}
"""

from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import _uid  # noqa: E402

N8N = os.environ.get("N8N_URL", "http://127.0.0.1:5679")
MOCKS = os.environ.get("MOCKS_URL", "http://127.0.0.1:5680")
MOCKS_IN = os.environ.get("MOCKS_INTERNAL_URL", "http://mocks:8080")
PG = os.environ.get("PG_CONTAINER", "companion-postgres")


def http(method: str, url: str, body=None, headers=None, ok=(200, 201, 204)):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw and raw[:1] in b"[{" else raw.decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        if e.code in ok:
            return e.code, raw
        raise RuntimeError(f"{method} {url} -> {e.code}: {raw[:300]}") from None


def api(method: str, path: str, body=None):
    return http(method, f"{N8N}/api/v1{path}", body, {"X-N8N-API-KEY": os.environ["N8N_API_KEY"]})[1]


def sql(q: str) -> str:
    out = subprocess.run(["docker", "exec", PG, "psql", "-U", "companion", "-d", "companion", "-tAc", q],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def load_build(rid: str):
    path = ROOT / "tools" / "builds" / f"r{rid[1:].replace('.', '_')}.py"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build()


def reader_copy(wf: dict) -> dict:
    out = copy.deepcopy(wf)
    for k in ("id", "versionId", "meta", "active", "staticData", "tags", "shared", "isArchived"):
        out.pop(k, None)
    out["pinData"] = {}
    return out


def test_copy(wf: dict, tests: dict) -> tuple[dict, dict]:
    """Return the test workflow and a map of schedule node -> test webhook path."""
    t = copy.deepcopy(wf)
    t["name"] = f"[test] {t['name']}"
    cfg = {k: (v.replace("{mocks}", MOCKS_IN) if isinstance(v, str) else v) for k, v in tests.get("config", {}).items()}
    sched = {}
    for n in t["nodes"]:
        if n["name"] == "Config":
            for a in n["parameters"]["assignments"]["assignments"]:
                if a["name"] in cfg:
                    v = cfg[a["name"]]
                    a["value"] = json.dumps(v) if a["type"] in ("array", "object") else v
        for cred in (n.get("credentials") or {}).values():
            if cred["id"] == "POSTGRES_CREDENTIAL_ID":
                cred.update(id=os.environ["PG_CREDENTIAL_ID"], name="Companion Postgres")
            if cred["id"] == "ANTHROPIC_CREDENTIAL_ID":
                cred.update(id=os.environ["ANTHROPIC_CREDENTIAL_ID"], name="Companion Anthropic")
        if n["type"] == "n8n-nodes-base.scheduleTrigger":
            path = "test-" + n["name"].lower().replace(" ", "-").replace(":", "")
            sched[n["name"]] = path
            n.update(type="n8n-nodes-base.webhook", typeVersion=2.1, webhookId=_uid(f"test/{wf['name']}/{path}"),
                     parameters={"httpMethod": "POST", "path": path, "responseMode": "onReceived", "options": {}})
    return t, sched


def deploy(wf: dict) -> str:
    for w in api("GET", "/workflows?limit=250")["data"]:
        if w["name"] == wf["name"]:
            if w.get("active"):
                api("POST", f"/workflows/{w['id']}/deactivate")
            for _ in range(30):  # n8n 2.x unpublishes asynchronously
                try:
                    api("DELETE", f"/workflows/{w['id']}")
                    break
                except RuntimeError as e:
                    if "409" not in str(e):
                        raise
                    time.sleep(1)
    body = {k: wf[k] for k in ("name", "nodes", "connections", "settings")}
    wid = api("POST", "/workflows", body)["id"]
    api("POST", f"/workflows/{wid}/activate")
    time.sleep(4)  # n8n registers production webhooks a moment after activation
    return wid


def wait_executions(wid: str, after: set, expected: int, timeout: float = 90) -> list:
    deadline = time.time() + timeout
    while time.time() < deadline:
        ex = [e for e in api("GET", f"/executions?workflowId={wid}&limit=100")["data"] if e["id"] not in after]
        if len(ex) >= expected and all(e.get("finished") or e.get("status") in ("success", "error", "crashed", "canceled") for e in ex):
            time.sleep(0.5)
            return ex
        time.sleep(0.5)
    raise RuntimeError(f"timed out waiting for {expected} execution(s)")


def dates(v):
    """Expand {today}, {today+N} and {today-N} (calendar days, ISO format) anywhere in a value."""
    import re
    if isinstance(v, str):
        def sub(m):
            n = int(m.group(2) or 0) * (-1 if m.group(1) == "-" else 1)
            return (dt.date.today() + dt.timedelta(days=n)).isoformat()
        return re.sub(r"\{today(?:([+-])(\d+))?\}", sub, v)
    if isinstance(v, list):
        return [dates(x) for x in v]
    if isinstance(v, dict):
        return {k: dates(x) for k, x in v.items()}
    return v


def merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        out[k] = merge(out.get(k, {}), v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def check(exp: dict) -> tuple[bool, str]:
    if "mock" in exp:
        _, state = http("GET", f"{MOCKS}/_state")
        node = state
        for p in exp["mock"].split("/"):
            node = node.get(p, {}) if isinstance(node, dict) else {}
        if "count" in exp:
            got = len(node) if isinstance(node, dict) else 0
            return got == exp["count"], f"{exp['mock']}: {got} records"
        got = node.get(exp["field"]) if isinstance(node, dict) else None
        if "in" in exp:
            return got in exp["in"], f"{exp['mock']}.{exp['field']} = {json.dumps(got)}"
        if "contains" in exp:
            return exp["contains"] in json.dumps(got), f"{exp['mock']}.{exp['field']} = {json.dumps(got)}"
        return got == exp["equals"], f"{exp['mock']}.{exp['field']} = {json.dumps(got)}"
    if "calls" in exp:
        method, path = exp["calls"].split(" ", 1)
        _, calls = http("GET", f"{MOCKS}/_calls")
        got = sum(1 for c in calls if c["method"] == method and c["path"] == path)
        return got == exp["count"], f"{exp['calls']}: {got} call(s)"
    if "sql" in exp:
        got = sql(exp["sql"])
        return got == str(exp["equals"]), f"{exp['sql']} -> {got}"
    return False, f"unknown expectation {exp}"


def import_check(wf: dict) -> None:
    """The reader's copy, placeholder credentials and all, must import into n8n as is."""
    body = {k: wf[k] for k in ("name", "nodes", "connections", "settings")}
    body["name"] = f"[import check] {wf['name']}"
    wid = api("POST", "/workflows", body)["id"]
    api("DELETE", f"/workflows/{wid}")


def run(rid: str, build_only: bool = False) -> int:
    import fcntl
    lock = open("/tmp/companion-golden.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)  # one golden-set run at a time: they share the mocks and tables
    return _run(rid, build_only)


def _run(rid: str, build_only: bool = False) -> int:
    folder = ROOT / "recipes" / rid / "n8n"
    folder.mkdir(parents=True, exist_ok=True)
    wf = load_build(rid).to_json()
    (folder / "workflow.json").write_text(json.dumps(reader_copy(wf), indent=2) + "\n")
    if build_only:
        print(f"wrote {folder / 'workflow.json'}")
        return 0
    import_check(reader_copy(wf))
    tests = dates(json.loads((folder / "tests.json").read_text()))
    twf, sched = test_copy(wf, tests)
    wid = deploy(twf)
    lines, failed = [], 0
    ai_live = os.environ.get("AI_LIVE") == "1"
    for case in tests["cases"]:
        if case.get("needs_ai") and not ai_live:
            lines.append((case, None, [], 0))
            print(f"SKIP  {case['case']}: {case['input']} (needs the AI key)")
            continue
        http("POST", f"{MOCKS}/_reset", {"seed": merge(tests.get("seed", {}), case.get("seed", {}))})
        sql("TRUNCATE key_log, decision_log, exception_queue RESTART IDENTITY")
        for f in case.get("fail", []):
            http("POST", f"{MOCKS}/_fail", f)
        before = {e["id"] for e in api("GET", f"/executions?workflowId={wid}&limit=100")["data"]}
        for trig in case["trigger"]:
            path = sched.get(trig.get("schedule"), trig.get("webhook"))
            http("POST", f"{N8N}/webhook/{path}", trig.get("body", {}))
            time.sleep(trig.get("pause", 0.3))
        ex = wait_executions(wid, before, len(case["trigger"]))
        results = [check(e) for e in case["expect"]]
        errors = [e for e in ex if e.get("status") == "error"]
        ok = all(r[0] for r in results) and (not errors or case.get("allow_error"))
        failed += not ok
        lines.append((case, ok, results, len(errors)))
        print(f"{'PASS' if ok else 'FAIL'}  {case['case']}: {case['input']}")
        for good, msg in results:
            if not good:
                print(f"      expected {msg}")
        if errors and not case.get("allow_error"):
            print(f"      {len(errors)} execution(s) ended in error")
    version = subprocess.run(["docker", "exec", "companion-n8n", "n8n", "--version"], capture_output=True, text=True).stdout.strip()
    today = dt.date.today().isoformat()
    md = [f"# {rid} n8n build: golden-set run", "",
          f"Run {today} on n8n {version} (self-hosted), against the companion's mock systems (`tools/mock-systems/`).",
          f"Result: {sum(1 for l in lines if l[1])} of {len(lines)} cases passed"
          + (f"; {sum(1 for l in lines if l[1] is None)} not run until the AI key is installed." if any(l[1] is None for l in lines) else "."), "",
          "| Case | Input | Result | Checked |", "|---|---|---|---|"]
    for case, ok, results, _ in lines:
        verdict = "Not run (needs the AI key)" if ok is None else ("Pass" if ok else "Fail")
        md.append(f"| {case['case']} | {case['input']} | {verdict} | {'; '.join(m for _, m in results)} |")
    md += ["", "The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16)."]
    (folder / "test-report.md").write_text("\n".join(md) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1], "--build" in sys.argv[2:]))
