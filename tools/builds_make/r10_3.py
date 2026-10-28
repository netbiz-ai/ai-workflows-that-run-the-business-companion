"""R10.3 Prepare tomorrow's dispatch briefing, read-only, as Make scenarios.

Source: book Chapter 10, recipe R10.3, build steps 1 to 11 (recipes/R10.3/build-spec.md);
AI step: recipes/R10.3/prompts/briefing-notes.md. Step 6 uses R10.1's step 4 masking rule.
The rules are the n8n build's own JavaScript (tools/builds/r10_3.py), run through n8n_rule.
Step 11 is the lead dispatcher's: nothing in these scenarios writes to the schedule.
Two scenarios, because a Make scenario has one trigger: each working afternoon (schedule,
Monday to Friday at 15:00, blueprint.json) and the second start (schedule, Monday to Friday
at 17:00, second-start.blueprint.json). Both run the same steps.

Where the Make build differs from the n8n canvas, and why:
- Branches never meet again after a router, so the full and partial routes each carry
  step 10, with the route in the step's name.
- Step 4's reads keep an HTTP error as their answer (no retry, stopOnHttpError off), and a
  timeout or lost connection reaches step 5 as an empty answer through Make's Resume handler,
  as n8n's reads flow on with an error item; either is listed "not available". The time limit
  is Config's source_timeout_ms, in seconds as Make takes it.
- The step 7 AI call (one try, as in n8n) hands a failed call on in the same way, so step 8
  reports it as "AI error".
- "Tomorrow" for the step 4 reads is computed in step 2's rule (UTC, as n8n's expression),
  because Make's date functions use the scenario's time zone.
- The write-failure row records which write failed by its step, without the HTTP error text,
  which Make's error route does not hand to a later body.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R10.3"
N8N = n8n_build(R)
T1, T2, RULE2, TABLE, MASK, CHECK, SOURCES = N8N.T1, N8N.T2, N8N.RULE2, N8N.TABLE, N8N.MASK, N8N.CHECK, N8N.SOURCES
CONFIG = {
    "scheduling_url": "https://<your scheduling system API, read-only, no restricted fields>",
    "crews_url": "https://<your crew schedule API, read-only>",
    "helpdesk_url": "https://<your helpdesk API, read-only>",
    "overdue_url": "https://<your overdue-work list API, read-only>",
    "stock_url": "https://<your stock-exception list API, read-only>",
    "budget_url": "https://<your budget table API>",
    "messaging_url": "https://<your messaging API>",
    "dispatch_channel": "<your dispatch channel>",
    "systems_owner": "<your systems owner>",
    "max_starts": 2,
    "run_cap_usd": 3,
    "monthly_cap_usd": 70,
    "source_timeout_ms": 10000,
    "note_max_words": 25,
    "ai_price_input_per_mtok": 0.10,
    "ai_price_output_per_mtok": 0.50,
    "ai_us_only_multiplier": 1.1,
    "masking_list": ["code", "gate", "keypad", "PIN", "key safe"],
    "address_words": ["<your floor, unit and street words, such as floor, unit, apartment, street, road>"],
    "mask_token": "<your mask token>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
CFG = "$('Config').first().json"


def resume(s: Scenario) -> dict:
    """Make's Resume handler: a call that could not answer at all goes on with an empty answer,
    as n8n's node sends its error item on to the same next step."""
    return {"id": s._id(f"_resume{s._next}"), "module": "builtin:Resume", "version": 1, "parameters": {},
            "mapper": {"data": ""}, "metadata": {"designer": {"x": 0, "y": 0}}}


def briefing(trigger: str, schedule: str) -> Scenario:
    s = Scenario(R, f"R10.3 Prepare tomorrow's dispatch briefing: {trigger.split(': ', 1)[1].lower()} ({schedule})",
                 "schedule", test_key=trigger, schedule=schedule)
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    cfg_all = "{{" + f"{c}.result" + "}}"
    s.flow += s.stop_flag()
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731

    # ---- steps 2 and 3: the budget table, before anything else -------------------------------
    budget = s.http("Read the budget table", "GET", cfg("budget_url") + "/days", query={"_wrap": "1"})
    budget["filter"] = s.continue_unless_stopped()
    s.flow.append(budget)
    code, inputs = n8n_rule(N8N.STEP2_JS, {"Config": cfg_all, "Read the budget table": data("Read the budget table")}, bodies={
        "starts_body": "JSON.stringify(Object.assign({}, out.row, { starts: out.start }))",
        "alert_body": (f"JSON.stringify({{ to: {CFG}.systems_owner, subject: 'R10.3 stopped: AI cap', "
                       "text: out.reason + '. Find the cause before raising any cap.' })"),
        "today_q": "encodeURIComponent(out.today)",
        "tomorrow": "new Date(Date.now() + 86400000).toISOString().slice(0, 10)",
        "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: 'briefing ' + out.today, reason: 'write failed', "
                        f"detail: 'A budget-table write or the post failed; check the budget table and the channel', owner: {CFG}.systems_owner }})"),
    })
    s.flow.append(s.code(RULE2, code, inputs))
    r2 = s.ref(RULE2)
    r2_out = lambda f: "{{" + f"{r2}.result.{f}" + "}}"  # noqa: E731
    day_url = cfg("budget_url") + "/days/" + r2_out("today_q")

    def write(name: str, method: str, url: str, body: str) -> dict:
        """A write: never retried; a failure goes to the exception queue and ends the run."""
        return s.http(name, method, url, body=body, parse=False,
                      onerror=[s.exception(f"{name}: exception queue", r2_out("failed_body")), s.ignore()])

    # ---- step 4: each source once, a time limit, no retry --------------------------------------
    tomorrow = r2_out("tomorrow")
    reads = [
        (SOURCES["work orders"], cfg("scheduling_url") + "/work_orders", {"_wrap": "1", "slot_date": tomorrow}),
        (SOURCES["crew schedule"], cfg("crews_url") + "/assignments", {"_wrap": "1", "date": tomorrow}),
        (SOURCES["helpdesk messages"], cfg("helpdesk_url") + "/tickets", {"_wrap": "1", "status": "open"}),
        (SOURCES["overdue work"], cfg("overdue_url") + "/items", {"_wrap": "1"}),
        (SOURCES["stock exceptions"], cfg("stock_url") + "/exceptions", {"_wrap": "1"}),
    ]
    timeout = "{{" + f"{c}.result.source_timeout_ms / 1000" + "}}"
    run = [write("Step 3: Add one to today's starts", "PUT", day_url, r2_out("starts_body"))]
    for name, url, q in reads:
        run.append(s.http(name, "GET", url, query=q, stop_on_error=False, timeout=timeout, onerror=[resume(s)]))
    read_sources = {n: data(n) for n, _, _ in reads}

    # ---- steps 5 and 6: the briefing table by rule; codes masked -------------------------------
    code, inputs = n8n_rule(N8N.STEP5_JS, read_sources)
    run.append(s.code(TABLE, code, inputs))
    table = "{{" + f"{s.ref(TABLE)}.result" + "}}"
    code, inputs = n8n_rule(N8N.STEP6_JS, {"Config": cfg_all, TABLE: table, **read_sources})
    run.append(s.code(MASK, code, inputs))
    mask = "{{" + f"{s.ref(MASK)}.result" + "}}"

    # ---- step 7: one AI call, no retry ----------------------------------------------------------
    vars_js = (f"{{ mask_token: $('Config').first().json.mask_token, unavailable_sources: $('{MASK}').first().json.unavailable_sources, "
               f"jobs: $('{MASK}').first().json.jobs_text }}")
    ai = s.ai_step("Step 7", ROOT / "recipes/R10.3/prompts/briefing-notes.md", vars_js, {"Config": cfg_all, MASK: mask},
                   max_tokens=2000, tries=1)
    ai[-1]["onerror"] = [resume(s)]
    run += ai

    # ---- step 8: the rules decide what is posted -------------------------------------------------
    call = s.ref("Step 7: AI call")
    code, inputs = n8n_rule(N8N.CHECK_JS, {"Config": cfg_all, RULE2: "{{" + f"{r2}.result" + "}}", TABLE: table,
                                           "Step 7: AI call": "{{" + f"{call}.data" + "}}"}, input_node="Step 7: AI call", bodies={
        "post_body": "JSON.stringify(out.post)",
        "spend_body": f"JSON.stringify({{ ai_spend: Math.round((Number($('{RULE2}').first().json.row.ai_spend || 0) + out.cost) * 1e6) / 1e6 }})",
    })
    run.append(s.code(CHECK, code, inputs))
    ck = s.ref(CHECK)
    ck_out = lambda f: "{{" + f"{ck}.result.{f}" + "}}"  # noqa: E731

    # ---- steps 9 and 10: post the briefing or the partial list, record AI spend -----------------
    post_url = cfg("messaging_url") + "/messages"
    run.append(s.router("Pass?", [
        (s.when("pass", ck_out("pass"), "true"), [
            write("Step 9: Post the briefing", "POST", post_url, ck_out("post_body")),
            write("Step 9: Mark full briefing posted", "PATCH", day_url, '{"full_briefing_posted": true}'),
            write("Step 10: Record AI spend (full)", "PATCH", day_url, ck_out("spend_body")),
        ]),
        (s.when("fail", ck_out("pass"), "true", "text:notequal"), [
            write("Step 9: Post the partial list", "POST", post_url, ck_out("post_body")),
            write("Step 10: Record AI spend (partial)", "PATCH", day_url, ck_out("spend_body")),
        ]),
    ]))

    # Step 2: run, or stop; a stop at the AI cap alerts Owen. Already posted, or two starts used: stop quietly.
    capped = {"name": "not run, capped", "conditions": [[{"a": r2_out("run"), "b": "true", "o": "text:notequal"},
                                                          {"a": r2_out("capped"), "b": "true", "o": "text:equal"}]]}
    s.flow.append(s.router("Run?", [
        (s.when("run", r2_out("run"), "true"), run),
        (capped, [s.http("Step 2: Alert Owen", "POST", cfg("messaging_url") + "/messages", body=r2_out("alert_body"), parse=False)]),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R10.3/make/, scenario)."""
    return [("blueprint.json", briefing(T1, "Monday to Friday at 15:00")),
            ("second-start.blueprint.json", briefing(T2, "Monday to Friday at 17:00"))]
