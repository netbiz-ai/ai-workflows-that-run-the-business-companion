#!/usr/bin/env python3
"""Build a recipe's Make scenarios, run its golden set on Make, and write the results.

    python3 tools/make/golden_make.py R11.2            build, test, write report
    python3 tools/make/golden_make.py R11.2 --build    only write recipes/R11.2/make/*.json

The golden set is the recipe's n8n one (recipes/<ID>/n8n/tests.json): the same seeds,
triggers and expectations, checked against the same mock systems and tables. Make runs
in Make's cloud, so the runner reaches the mocks and the tables through the companion
stack's public test route. Environment:

    MAKE_API_TOKEN  MAKE_ZONE (such as us2.make.com)  MAKE_TEAM_ID
    MOCKS_PUBLIC_URL   the mocks as Make reaches them (https://<host>/<secret>)
    TABLE_API_URL      the key log, decision log and exception queue over PostgREST
                       (default MOCKS_PUBLIC_URL + /db)
    MAKE_PLAN (default Core)  the plan the report is stamped with (Make has no versions)
    MOCKS_URL, PG_CONTAINER as for tools/n8n/golden.py (the runner's own view)

What is committed (make/*.json) is the builder's output with the reader's defaults in
each Config step and no webhook chosen. What is tested is the same blueprint with two
changes only: Config points at the mock systems, and the webhook step has a test hook.
A schedule scenario is run on demand, which is what its schedule would do at 07:00.
The report lists the date, every case's result and the Make credits each case used.
"""

from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
import golden  # noqa: E402

UA = {"User-Agent": "companion-golden/1.0"}  # Make refuses Python's default agent
MOCKS_PUBLIC = os.environ.get("MOCKS_PUBLIC_URL", "").rstrip("/")
TABLE_API = os.environ.get("TABLE_API_URL", MOCKS_PUBLIC + "/db")
POLL = 3  # seconds between log reads: Make Core allows 60 API calls a minute
END = {1: "success", 2: "warning", 3: "error"}


def make(method: str, path: str, body=None):
    """Make API call; waits and retries on the per-minute rate limit."""
    url = f"https://{os.environ['MAKE_ZONE']}/api/v2{path}"
    headers = {"Authorization": "Token " + os.environ["MAKE_API_TOKEN"], "Content-Type": "application/json", **UA}
    for attempt in range(6):
        req = urllib.request.Request(url, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            if e.code == 429 and attempt < 5:
                time.sleep(15 * (attempt + 1))
                continue
            raise RuntimeError(f"Make {method} {path} -> {e.code}: {raw[:400]}") from None
    raise RuntimeError("unreachable")


def team() -> int:
    return int(os.environ["MAKE_TEAM_ID"])


def load_build(rid: str):
    path = ROOT / "tools" / "builds_make" / f"r{rid[1:].replace('.', '_')}.py"
    spec = importlib.util.spec_from_file_location(f"make_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build()


def config_module(bp: dict) -> dict:
    return next(m for m in bp["flow"] if m["module"] == "code:ExecuteCode" and m["metadata"]["designer"].get("name") == "Config")


def set_config(bp: dict, values: dict) -> None:
    """Overwrite fields of the Config step's settings object (the JSON after `return`)."""
    m = config_module(bp)
    js = m["mapper"]["codeEditorJavascript"]
    head, _, rest = js.partition("\nreturn ")
    cfg = json.loads(rest.rstrip().rstrip(";"))
    unknown = set(values) - set(cfg)
    if unknown:
        raise ValueError(f"tests.json config has fields the Config step does not: {sorted(unknown)}")
    cfg.update(values)
    m["mapper"]["codeEditorJavascript"] = head + "\nreturn " + json.dumps(cfg, indent=2) + ";"


def public(v):
    """{mocks} -> the mocks as Make reaches them."""
    if isinstance(v, str):
        return v.replace("{mocks}", MOCKS_PUBLIC)
    if isinstance(v, list):
        return [public(x) for x in v]
    if isinstance(v, dict):
        return {public(k): public(x) for k, x in v.items()}
    return v


def create(bp: dict, scheduling: dict) -> int:
    r = make("POST", "/scenarios?confirmed=true",
             {"teamId": team(), "blueprint": json.dumps(bp), "scheduling": json.dumps(scheduling)})
    return r["scenario"]["id"]


def remove_old(names: set[str]) -> None:
    for s in make("GET", f"/scenarios?teamId={team()}&pg[limit]=200").get("scenarios", []):
        if s["name"] in names:
            if s.get("isActive"):
                make("POST", f"/scenarios/{s['id']}/stop")
            make("DELETE", f"/scenarios/{s['id']}")
    for h in make("GET", f"/hooks?teamId={team()}&pg[limit]=200").get("hooks", []):
        if h["name"] in names:
            make("DELETE", f"/hooks/{h['id']}?confirmed=true")


def import_check(bp: dict, scheduling: dict) -> None:
    """The reader's copy, no webhook chosen, must import into Make as is."""
    b = copy.deepcopy(bp)
    b["name"] = f"[import check] {bp['name']}"
    remove_old({b["name"]})
    make("DELETE", f"/scenarios/{create(b, scheduling)}")


def ended(sid: int) -> list[dict]:
    logs = make("GET", f"/scenarios/{sid}/logs?pg[limit]=50").get("scenarioLogs", [])
    return [entry for entry in logs if entry.get("eventType") == "EXECUTION_END"]


def wait_runs(sids: list[int], before: set, expected: int, timeout: float = 180) -> list[dict]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(POLL)
        runs = [e for sid in sids for e in ended(sid) if e["id"] not in before]
        if len(runs) >= expected:
            return runs
    raise RuntimeError(f"timed out waiting for {expected} Make run(s)")


def deploy(builds, tests: dict) -> tuple[dict, list[int], list[int]]:
    """Create the test scenarios. Returns (trigger key -> how to fire it, scenario ids, hook ids)."""
    cfg = public(tests.get("config", {}))
    cfg.update(stop_flag_url=f"{MOCKS_PUBLIC}/control/stop_flags/{tests['_rid']}", table_api_url=TABLE_API)
    names = {f"[test] {s.name}" for _, s in builds}
    remove_old(names)
    fire, sids, hooks = {}, [], []
    for _, s in builds:
        bp = copy.deepcopy(s.blueprint())
        bp["name"] = f"[test] {s.name}"
        set_config(bp, cfg)
        if s.trigger == "webhook":
            h = make("POST", "/hooks", {"name": bp["name"], "teamId": team(), "typeName": "gateway-webhook",
                                        "method": False, "headers": False, "stringify": False})["hook"]
            hooks.append(h["id"])
            bp["flow"][0]["parameters"]["hook"] = h["id"]
            sid = create(bp, {"type": "immediately"})
            fire[s.test_key] = ("webhook", h["url"], sid)
        else:
            sid = create(bp, {"type": "on-demand"})
            fire[s.test_key] = ("run", sid, sid)
        make("POST", f"/scenarios/{sid}/start")
        sids.append(sid)
    return fire, sids, hooks


def run(rid: str, build_only: bool = False) -> int:
    import fcntl
    lock = open("/tmp/companion-golden.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)  # one golden-set run at a time: they share the mocks and tables
    return _run(rid, build_only)


def _run(rid: str, build_only: bool) -> int:
    folder = ROOT / "recipes" / rid / "make"
    folder.mkdir(parents=True, exist_ok=True)
    builds = load_build(rid)
    for fname, s in builds:
        (folder / fname).write_text(json.dumps(s.blueprint(), indent=2) + "\n")
    if build_only:
        print(f"wrote {', '.join(f for f, _ in builds)} in {folder}")
        return 0
    if not MOCKS_PUBLIC:
        raise SystemExit("set MOCKS_PUBLIC_URL to the mocks' public test route")
    for _, s in builds:
        import_check(s.blueprint(), {"type": "immediately" if s.trigger == "webhook" else "on-demand"})
    tests = golden.dates(json.loads((ROOT / "recipes" / rid / "n8n" / "tests.json").read_text()))
    tests["_rid"] = rid
    stop = {"control": {"stop_flags": {rid: {"id": rid, "stopped": False}}}}
    tests["seed"] = golden.merge(stop, tests.get("seed", {}))
    first = tests["cases"][0]
    tests["cases"].append({
        "case": "Stop flag", "input": "The stop flag is set (companion extension)", "auto": True,
        "seed": golden.merge(first.get("seed", {}), {"control": {"stop_flags": {rid: {"stopped": True}}}}),
        "trigger": [t for t in first["trigger"] if "sql" not in t][:1],
        "expect": [{"writes": 0}, {"sql": "select count(*) from key_log", "equals": "0"},
                   {"sql": "select count(*) from decision_log", "equals": "0"}]})
    fire, sids, hooks = deploy(builds, tests)
    lines, failed = [], 0
    try:
        for case in tests["cases"]:
            if case.get("needs_ai") and os.environ.get("AI_LIVE") != "1":
                lines.append((case, None, [], 0, 0))
                print(f"SKIP  {case['case']}: {case['input']} (needs the AI key)")
                continue
            golden.http("POST", f"{golden.MOCKS}/_reset", {"seed": golden.merge(tests.get("seed", {}), case.get("seed", {}))})
            golden.sql("TRUNCATE key_log, decision_log, exception_queue RESTART IDENTITY")
            for q in case.get("sql_seed", []):
                golden.sql(q)
            for f in case.get("fail", []):
                golden.http("POST", f"{golden.MOCKS}/_fail", f)
            before = {e["id"] for sid in sids for e in ended(sid)}
            for trig in case["trigger"]:
                if "sql" in trig:
                    golden.sql(trig["sql"])
                    time.sleep(trig.get("pause", 0.3))
                    continue
                kind, target, _ = fire[trig.get("schedule") or trig.get("webhook")]
                if kind == "webhook":
                    golden.http("POST", target, trig.get("body", {}), UA)
                else:
                    make("POST", f"/scenarios/{target}/run", {"responsive": True})
                time.sleep(trig.get("pause", 0.3))
            runs = wait_runs(sids, before, sum(1 for t in case["trigger"] if "sql" not in t))
            time.sleep(1)
            results = [golden.check(e) for e in case["expect"]]
            if case.get("needs_ai"):
                _, calls = golden.http("GET", f"{golden.MOCKS}/_calls")
                bad = [c.get("status") for c in calls if c["path"] == "/anthropic/v1/messages" and c.get("status") != 200]
                if bad:
                    results.append((False, f"AI call(s) failed with status {bad}, so the model's answer was never tested"))
            errors = [r for r in runs if END.get(r.get("status")) == "error"]
            credits = sum(r.get("centicredits") or 0 for r in runs) / 100
            ok = all(r[0] for r in results) and (not errors or case.get("allow_error"))
            failed += not ok
            lines.append((case, ok, results, len(errors), credits))
            print(f"{'PASS' if ok else 'FAIL'}  {case['case']}: {case['input']}  ({credits:g} credits)")
            for good, msg in results:
                if not good:
                    print(f"      expected {msg}")
            if errors and not case.get("allow_error"):
                print(f"      {len(errors)} run(s) ended in error")
    finally:
        for sid in sids:
            make("POST", f"/scenarios/{sid}/stop")
            make("DELETE", f"/scenarios/{sid}")
        for h in hooks:
            make("DELETE", f"/hooks/{h}?confirmed=true")
    today = dt.date.today().isoformat()
    total = sum(entry[4] for entry in lines)
    md = [f"# {rid} Make build: golden-set run", "",
          f"Run {today} on Make (cloud service, {os.environ.get('MAKE_PLAN', 'Core')} plan, {os.environ['MAKE_ZONE']}), against the companion's mock systems (`tools/mock-systems/`).",
          f"Result: {sum(1 for entry in lines if entry[1])} of {len(lines)} cases passed"
          + (f"; {sum(1 for entry in lines if entry[1] is None)} not run until the AI key is installed." if any(entry[1] is None for entry in lines) else "."),
          f"Make credits used by the whole set: {total:g}.", "",
          "| Case | Input | Result | Credits | Checked |", "|---|---|---|---|---|"]
    for case, ok, results, _, credits in lines:
        verdict = "Not run (needs the AI key)" if ok is None else ("Pass" if ok else "Fail")
        md.append(f"| {case['case']} | {case['input']} | {verdict} | {credits:g} | {'; '.join(m for _, m in results)} |")
    md += ["", "The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16)."]
    (folder / "test-report.md").write_text("\n".join(md) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1], "--build" in sys.argv[2:]))
