"""R15.2 Check delivery and installation capacity before a promotion launches, as Make scenarios: rules only, no AI step.

Source: book Chapter 15, recipe R15.2, build steps 1 to 8 and Table 15.2 (recipes/R15.2/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r15_2.py), run through n8n_rule.
Two scenarios, because a Make scenario has one trigger: the brief Ben marks "ready" (webhook)
and the working-morning run (schedule, Monday to Friday at 07:00): live briefs (step 8), and
held briefs checked again (step 7).
The n8n build's chain of If nodes after the status write (tell someone? to the exception queue?)
becomes one router on the result's path, because Make's branches never meet again: each route
repeats the closing steps, and a failed write on any route still marks the key failed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R15.2"
N8N = n8n_build(R)
T, M, RULES = N8N.T, N8N.M, N8N.RULES
CONFIG = {
    "briefs_url": "https://<your promotion brief list API>",
    "scheduling_url": "https://<your delivery-scheduling export API>",
    "messaging_url": "https://<your messaging API>",
    "export_max_age_hours": 24,
    "watch_share_pct": 90,
    "capacity_owner": "<your operations manager>",
    "promotion_owner": "<your promotion owner>",
    "systems_owner": "<your systems owner>",
}
CFG = "$('Config').first().json"
BODIES = {
    # Which of the n8n build's If nodes pass: a status to write, someone to tell, an exception row.
    "path": "out.body === null ? 'no promise' : ['set', out.notify !== null ? 'tell' : '', out.exception !== null ? 'queue' : '']"
            ".filter(Boolean).join(' + ')",
    "key_q": "encodeURIComponent(out.key)",
    "brief_q": "encodeURIComponent(out.brief_id)",
    "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.key }})",
    "status_body": "JSON.stringify(out.body)",
    "message": "JSON.stringify(out.notify)",
    "held_body": f"out.exception && JSON.stringify({{ recipe: '{R}', item: out.brief_id, reason: 'capacity held', "
                 "detail: out.exception.reason + ': ' + out.exception.detail, owner: out.exception.owner })",
    "done_body": "JSON.stringify({ status: 'done', result: out.outcome })",
    "log_body": f"JSON.stringify({{ recipe: '{R}', item: out.brief_id, decision: out.mode + ': ' + out.outcome, "
                "rules: { reasons: out.reasons, figures: (out.body || {}).capacity_figures || (out.body || {}).live_watch || null } })",
    "failed_body": f"JSON.stringify({{ recipe: '{R}', item: out.brief_id, reason: 'write failed', "
                   f"detail: 'Capacity status or message write failed; check the brief, never retried', owner: {CFG}.systems_owner }})",
}
# (path, tag in the step names): every combination the n8n build's If nodes allow.
PATHS = [("no promise", "no promise"), ("set", "status"), ("set + tell", "told"),
         ("set + queue", "queued"), ("set + tell + queue", "told, queued")]


def closing(s: Scenario, out) -> None:
    """Reserve the key, then one route per path: write the status, tell, queue, mark done, log.
    out(field) is the Make expression for one result field (the rule's own step or an iterator's bundle)."""
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow.append(s.rpc("Reserve key", "reserve_key", out("reserve_body")))
    failed = lambda step: s.write_failed(step, out("key_q"), out("failed_body"))  # noqa: E731
    routes = []
    for path, tag in PATHS:
        flow = []
        if path != "no promise":
            # Writes the capacity field only: "cleared" with the figures, or "held" with the shortfall by week.
            name = f"Steps 5, 6 and 8: Set capacity status ({tag})"
            flow.append(s.http(name, "PATCH", cfg("briefs_url") + "/briefs/" + out("brief_q"), body=out("status_body"),
                               parse=False, onerror=failed(name)))
        if "tell" in path:
            name = f"Steps 2, 6 and 8: Tell Tom, Ben or Owen ({tag})"
            flow.append(s.http(name, "POST", cfg("messaging_url") + "/messages", body=out("message"), parse=False, onerror=failed(name)))
        if "queue" in path:
            flow.append(s.exception(f"Exception queue: held for a person ({tag})", out("held_body")))
        flow.append(s.finish_key(f"Mark key done ({tag})", out("key_q"), out("done_body")))
        flow.append(s.decision_log(f"Decision log ({tag})", out("log_body")))
        # Every route also needs a new key: a copy stops here, as this brief version was checked against this export before.
        flt = s.when(f"new key, path is {path}", out("path"), path)
        flt["conditions"][0] += s.is_new_key("Reserve key")["conditions"][0]
        routes.append((flt, flow))
    s.flow.append(s.router("Promise to check?", routes))


def reads(s: Scenario) -> list[dict]:
    """Steps 2 and 3: one read of each per run, however many briefs the morning checks."""
    cfg = "{{" + f"{s.ref('Config')}.result.scheduling_url" + "}}"
    return [s.http("Step 2: Read the slot export", "GET", cfg + "/exports/latest"),
            s.http("Step 3: Read the non-promoted average", "GET", cfg + "/averages/non-promoted")]


def brief_ready() -> Scenario:
    s = Scenario(R, "R15.2 Check capacity before a promotion launches", "webhook", test_key="r15-2-brief-ready")
    s.flow.append(s.webhook(T))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    s.flow += s.stop_flag()
    read = s.http("Read the brief", "GET", "{{" + f"{c}.result.briefs_url" + "}}/briefs/{{encodeURL(1.brief_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    code, inputs = n8n_rule(N8N.READY_JS, {"Read the brief": "{{" + f"{s.ref('Read the brief')}.data" + "}}"})
    s.flow.append(s.code("Brief to check", code, inputs))
    s.flow += reads(s)
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    code, inputs = n8n_rule(N8N.RULES_JS, {
        "Config": "{{" + f"{c}.result" + "}}",
        "Brief to check": "{{" + f"{s.ref('Brief to check')}.result" + "}}",
        "Step 2: Read the slot export": data("Step 2: Read the slot export"),
        "Step 3: Read the non-promoted average": data("Step 3: Read the non-promoted average"),
    }, executed=(T,), bodies=BODIES)
    s.flow.append(s.code(RULES, code, inputs))
    ru = s.ref(RULES)
    closing(s, lambda f: "{{" + f"{ru}.result.{f}" + "}}")
    return s


def working_morning() -> Scenario:
    s = Scenario(R, "R15.2 Check capacity before a promotion launches: each working morning", "schedule",
                 test_key=M, schedule="Monday to Friday at 07:00 (edit for your week)")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    s.flow += s.stop_flag()
    every = s.http("Read every brief", "GET", "{{" + f"{c}.result.briefs_url" + "}}/briefs", query={"_wrap": "1"})
    every["filter"] = s.continue_unless_stopped()
    s.flow.append(every)
    pick = "Rule: briefs to check this morning"
    code, inputs = n8n_rule(N8N.MORNING_JS, {"Read every brief": "{{" + f"{s.ref('Read every brief')}.data" + "}}"}, many=True)
    s.flow.append(s.code(pick, code, inputs))
    first, second = reads(s)
    # No brief to check this morning: stop, as the n8n rule's empty output does.
    first["filter"] = s.when("a brief to check", "{{length(" + f"{s.ref(pick)}.result.items" + ")}}", "0", "number:greater")
    s.flow += [first, second]
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    code, inputs = n8n_rule(N8N.RULES_JS, {
        "Config": "{{" + f"{c}.result" + "}}",
        pick: "{{" + f"{s.ref(pick)}.result.items" + "}}",
        "Step 2: Read the slot export": data("Step 2: Read the slot export"),
        "Step 3: Read the non-promoted average": data("Step 3: Read the non-promoted average"),
    }, items=(pick,), executed=(M,), many=True, bodies=BODIES)
    s.flow.append(s.code(RULES, code, inputs))
    s.flow.append(s.iterator("Each brief", "{{" + f"{s.ref(RULES)}.result.items" + "}}"))
    it = s.ref("Each brief")
    closing(s, lambda f: "{{" + f"{it}.{f}" + "}}")
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R15.2/make/, scenario)."""
    return [("blueprint.json", brief_ready()), ("morning.blueprint.json", working_morning())]
