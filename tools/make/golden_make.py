#!/usr/bin/env python3
"""Build a recipe's Make scenarios, run its golden set on Make, and write the results.

    python3 tools/make/golden_make.py R11.2            build, test, write report
    python3 tools/make/golden_make.py R11.2 --build    only write recipes/R11.2/make/*.json
    python3 tools/make/golden_make.py R11.2 --case Normal --case Edge
                                                       run only these cases (to debug for fewer
                                                       credits); never writes the report

The golden set is the recipe's n8n one (recipes/<ID>/n8n/tests.json): the same seeds,
triggers and expectations, checked against the same mock systems and tables. Make runs
in Make's cloud, so the runner reaches the mocks and the tables through the companion
stack's public test route. Environment:

    MAKE_API_TOKEN  MAKE_ZONE (such as us2.make.com)  MAKE_TEAM_ID
    MOCKS_PUBLIC_URL   the mocks as Make reaches them (https://<host>/<secret>)
    TABLE_API_URL      the key log, decision log and exception queue over PostgREST
                       (default MOCKS_PUBLIC_URL + /db)
    MAKE_PLAN (default Core)  the plan the report is stamped with (Make has no versions)
    MAKE_ADOPT_SCENARIOS  existing scenario IDs to take over as test slots (see slots())
    MAKE_ORG_ID  MAKE_MIN_CREDITS (default 1500): refuse to start below this many credits left
    MOCKS_URL, PG_CONTAINER as for tools/n8n/golden.py (the runner's own view)

What is committed (make/*.json) is the builder's output with the reader's defaults in
each Config step and no webhook chosen. What is tested is the same blueprint with two
changes only: Config points at the mock systems, and the webhook step has a test hook.
Every run loads its blueprints into a few kept test slots (see slots()), first the reader's
copy as the import check and then the test copy, because Make limits scenario creation.
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

sys.path.insert(0, str(ROOT / "tools" / "make"))
import mk  # noqa: E402

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
            if e.code == 429 and "IM011" in raw:  # the creation limit: waiting seconds will not lift it
                raise RuntimeError(f"Make {method} {path} -> 429 IM011: Make's limit on creating scenarios is reached; "
                                   "try again later (the window is not documented)") from None
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
    m["mapper"]["codeEditorJavascript"] = head + "\nreturn " + mk.settings_js(cfg) + ";"


def public(v):
    """{mocks}, and the stack-internal mocks address some golden sets spell out, -> the mocks as Make reaches them."""
    if isinstance(v, str):
        return v.replace("{mocks}", MOCKS_PUBLIC).replace(golden.MOCKS_IN, MOCKS_PUBLIC)
    if isinstance(v, list):
        return [public(x) for x in v]
    if isinstance(v, dict):
        return {public(k): public(x) for k, x in v.items()}
    return v


SLOTS = int(os.environ.get("MAKE_TEST_SLOTS", "5"))  # the most scenarios one recipe has (R7.3, R15.3)


def slots(n: int) -> list[tuple[int, str, dict]]:
    """n test slots: (scenario id, slot name, webhook) named "[companion test slot k]", kept in the team.
    Make limits how many scenarios a team may create over time, so every golden-set run loads its
    blueprints into the same few slots (stopped when idle) instead of creating scenarios; the whole
    Make phase creates SLOTS scenarios and webhooks once."""
    if n > SLOTS:
        raise SystemExit(f"this recipe has {n} scenarios; raise MAKE_TEST_SLOTS (now {SLOTS})")
    have, offset = {}, 0
    while True:
        page = make("GET", f"/scenarios?teamId={team()}&pg[limit]=100&pg[offset]={offset}").get("scenarios", [])
        have.update({x["name"]: x for x in page})
        if len(page) < 100:
            break
        offset += 100
    hooks = {h["name"]: h for h in make("GET", f"/hooks?teamId={team()}&pg[limit]=200").get("hooks", [])}
    # MAKE_ADOPT_SCENARIOS: IDs of existing scenarios to take over as missing slots (renamed on first load),
    # for when Make's creation limit is reached.
    adopt = [int(x) for x in os.environ.get("MAKE_ADOPT_SCENARIOS", "").split(",") if x.strip()]
    by_id = {x["id"]: x for x in have.values()}
    out = []
    for k in range(1, n + 1):
        name = f"[companion test slot {k}]"
        hook = hooks.get(name) or make("POST", "/hooks", {"name": name, "teamId": team(), "typeName": "gateway-webhook",
                                                         "method": False, "headers": False, "stringify": False})["hook"]
        sc = have.get(name)
        while not sc and adopt:
            sc = by_id.get(adopt.pop(0))
        if sc and sc.get("isActive"):
            make("POST", f"/scenarios/{sc['id']}/stop")
        if not sc:
            stub = {"name": name, "flow": [], "metadata": {"instant": False, "version": 1, "designer": {"orphans": []},
                                                          "scenario": {"dlq": True, "slots": None, "dataloss": False, "maxErrors": 3,
                                                                       "autoCommit": True, "roundtrips": 1, "sequential": False,
                                                                       "confidential": False, "freshVariables": False,
                                                                       "autoCommitTriggerLast": True}}}
            sc = make("POST", "/scenarios?confirmed=true", {"teamId": team(), "blueprint": json.dumps(stub),
                                                            "scheduling": json.dumps({"type": "on-demand"})})["scenario"]
        out.append((sc["id"], name, hook))
    return out


def load(sid: int, slot_name: str, bp: dict, scheduling: dict) -> None:
    """Replace a slot's blueprint; Make validates it as an import would. The blueprint keeps the
    slot's name, so the slot is found again on the next run."""
    bp = dict(bp, name=slot_name)
    make("PATCH", f"/scenarios/{sid}?confirmed=true", {"blueprint": json.dumps(bp), "scheduling": json.dumps(scheduling)})


def ended(sid: int) -> list[dict]:
    logs = make("GET", f"/scenarios/{sid}/logs?pg[limit]=50").get("scenarioLogs", [])
    return [entry for entry in logs if entry.get("eventType") == "EXECUTION_END"]


def credits_left() -> float | None:
    org = os.environ.get("MAKE_ORG_ID")
    if not org:
        return None
    o = make("GET", f"/organizations/{org}")["organization"]
    return float(o["license"]["operations"]) - float(o.get("operations") or 0)


def retrying(sids: list[int], since: str) -> bool:
    """A run stopped at a Retry handler waits in Incomplete executions until Make resumes it."""
    for sid in sids:
        for d in make("GET", f"/dlqs?scenarioId={sid}").get("dlqs", []):
            if d["created"] >= since and not d.get("resolved") and (d.get("isBeingReprocessed") or d.get("attempts", 0) <= 3):
                return True
    return False


def wait_runs(sids: list[int], before: set, expected: int, since: str, timeout: float = 180) -> list[dict]:
    """Wait for the case's runs to end, then for any Retry handler to finish (up to 3 retries a minute apart)."""
    deadline = time.time() + timeout
    while True:
        time.sleep(POLL)
        runs = [e for sid in sids for e in ended(sid) if e["id"] not in before]
        if len(runs) >= expected:
            break
        if time.time() > deadline:
            inactive = [sid for sid in sids if not make("GET", f"/scenarios/{sid}")["scenario"].get("isActive")]
            raise RuntimeError(f"timed out waiting for {expected} Make run(s)" + (f"; Make switched off {inactive}" if inactive else ""))
    deadline = time.time() + 300
    while retrying(sids, since) and time.time() < deadline:
        time.sleep(15)
    return [e for sid in sids for e in ended(sid) if e["id"] not in before]


def ensure_active(sids: list[int]) -> list[int]:
    """Make switches a webhook scenario off after one error (book Chapter 16); start it again for the next case."""
    off = [sid for sid in sids if not make("GET", f"/scenarios/{sid}")["scenario"].get("isActive")]
    for sid in off:
        make("POST", f"/scenarios/{sid}/start")
    return off


def deploy(builds, tests: dict) -> tuple[dict, list[int]]:
    """Load the test copies into the test slots and start them. Returns (trigger key -> how to fire it, scenario ids)."""
    cfg = public(tests.get("config", {}))
    cfg.update(stop_flag_url=f"{MOCKS_PUBLIC}/control/stop_flags/{tests['_rid']}", table_api_url=TABLE_API)
    fire, sids = {}, []
    for (sid, slot, hook), (_, s) in zip(slots(len(builds)), builds):
        # Import check first: the reader's copy, no webhook chosen, must load into Make as is.
        reader = copy.deepcopy(s.blueprint())
        load(sid, slot, reader, {"type": "on-demand"})
        bp = copy.deepcopy(s.blueprint())
        set_config(bp, cfg)
        if s.trigger == "webhook":
            bp["flow"][0]["parameters"]["hook"] = hook["id"]
            load(sid, slot, bp, {"type": "immediately"})
            fire[s.test_key] = ("webhook", hook["url"], sid)
        else:
            load(sid, slot, bp, {"type": "on-demand"})
            fire[s.test_key] = ("run", sid, sid)
        make("POST", f"/scenarios/{sid}/start")
        sids.append(sid)
    return fire, sids


def run(rid: str, build_only: bool = False, only: list[str] | None = None) -> int:
    import fcntl
    lock = open("/tmp/companion-golden.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)  # one golden-set run at a time: they share the mocks and tables
    return _run(rid, build_only, only or [])


def _run(rid: str, build_only: bool, only: list[str]) -> int:
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
    left = credits_left()
    if left is not None:
        print(f"Make credits left: {left:g}")
        if left < float(os.environ.get("MAKE_MIN_CREDITS", "1500")):
            raise SystemExit(f"only {left:g} Make credits left; not starting (MAKE_MIN_CREDITS)")
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
    if only:
        missing = set(only) - {c["case"] for c in tests["cases"]}
        if missing:
            raise SystemExit(f"no such case: {sorted(missing)}")
        tests["cases"] = [c for c in tests["cases"] if c["case"] in only]
    fire, sids = deploy(builds, tests)
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
            since = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            for trig in case["trigger"]:
                if "sql" in trig:
                    golden.sql(trig["sql"])
                    time.sleep(trig.get("pause", 0.3))
                    continue
                key = trig.get("schedule") or trig.get("webhook")
                if key not in fire:
                    raise SystemExit(f"case {case['case']!r}: no scenario has test_key {key!r} (have {sorted(fire)})")
                kind, target, _ = fire[key]
                if kind == "webhook":
                    golden.http("POST", target, trig.get("body", {}), UA)
                else:
                    make("POST", f"/scenarios/{target}/run", {"responsive": True})
                time.sleep(trig.get("pause", 0.3))
            try:
                runs = wait_runs(sids, before, sum(1 for t in case["trigger"] if "sql" not in t), since)
            except RuntimeError as e:
                runs = []
                print(f"      {e}")
            time.sleep(1)
            results = [golden.check(e) for e in case["expect"]]
            if case.get("needs_ai"):
                _, calls = golden.http("GET", f"{golden.MOCKS}/_calls")
                bad = [c.get("status") for c in calls if c["path"] == "/anthropic/v1/messages" and c.get("status") != 200]
                if bad:
                    results.append((False, f"AI call(s) failed with status {bad}, so the model's answer was never tested"))
            errors = [r for r in runs if END.get(r.get("status")) == "error"]
            switched_off = ensure_active(sids)
            if switched_off:
                results.append((False, f"Make switched off scenario(s) {switched_off} after an error"))
            if not runs:
                results.append((False, "no Make run ended"))
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
    left = credits_left()
    if left is not None:
        print(f"Make credits left: {left:g}")
    if only:
        print("partial run (--case): report not written")
        return 1 if failed else 0
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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("recipe")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--case", action="append", default=[])
    a = ap.parse_args()
    sys.exit(run(a.recipe, a.build, a.case))
