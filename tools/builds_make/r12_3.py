"""R12.3 Alert the owner when a measure crosses its threshold, as Make scenarios: rules only, no AI step.

Source: book Chapter 12, recipe R12.3, build steps 1 to 9 (recipes/R12.3/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r12_3.py), run through n8n_rule.
Two scenarios, because a Make scenario has one trigger: a table version becoming current
(webhook, steps 1 to 7 and 9) and the Friday check (schedule, every Friday at 16:00, step 8).
The rules use plain Date in UTC, which Make's Code app has, so no shim is needed.

Steps 4 and 6 post the alert three times before they email it (book). n8n retries the post and
sends its error output to the email; Make's Retry handler has no fallback, so here the post reads
its own status: three tries, each followed by a router, and the email after the third failure.
Branches never meet again, so each delivery route repeats the closing steps.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R12.3"
N8N = n8n_build(R)
T, F = N8N.T, N8N.F
OUTCOME = "Step 2: Rule: each measure's outcome"
CONFIG = {
    "table_url": "https://<your weekly table API>",
    "thresholds_url": "https://<your threshold list API>",
    "chat_url": "https://<your Teams or chat API>",
    "email_url": "https://<your email API>",
    "alert_log_url": "https://<your alert log API>",
    "preread_url": "https://<your pre-read API>",
    "second_week_only": False,
    "list_editor": "<your threshold list editor>",
}

# The n8n build's "Steps 4 and 6: Alert text" Code node, unchanged, run inside the outcome step for
# each measure that needs an alert: one Code step per version instead of one per measure.
ALERT_TEXT = ("// Steps 4 and 6: the alert text, the n8n build's own JavaScript; $(...) answers with this measure's outcome.\n"
              "const alertText = (measure) => {\n  const $ = () => ({ item: { json: measure } });\n"
              + N8N.ALERT_JS.strip() + "\n};\n")
ALERTS = "['stale', 'past the line']"
A = f"({ALERTS}.includes(out.outcome) ? alertText(out).json : {{}})"
ITEM = "out.week + ':' + out.measure"
RULES = ("{ version: out.version, value: out.value, change: out.change, status: out.status, line_version: out.line_version, "
         "line: out.line, field: out.field, direction: out.direction }")
BODIES = {
    "alert": f"{ALERTS}.includes(out.outcome) ? 'yes' : 'no'",
    "key_q": "encodeURIComponent(out.key)",
    "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.key }})",
    "post_body": f"JSON.stringify((a => ({{ to: a.to, subject: a.subject, text: a.text }}))({A}))",
    "alert_log_body": f"JSON.stringify((a => ({{ id: out.key, week: out.week, measure: out.measure, outcome: out.outcome, "
                      f"to: a.to, subject: a.subject, cutoff: out.cutoff, seen: false }}))({A}))",
    "done_body": f"JSON.stringify({{ status: 'done', result: {A}.kind + ' alert sent' }})",
    # Step 7: every check is logged, alert or not.
    "log_sent": f"JSON.stringify({{ recipe: '{R}', item: {ITEM}, decision: out.outcome + ': alert sent', rules: {RULES} }})",
    "log_none": f"JSON.stringify({{ recipe: '{R}', item: {ITEM}, decision: out.outcome + ': no alert', rules: {RULES} }})",
    "log_copy": f"JSON.stringify({{ recipe: '{R}', item: {ITEM}, decision: out.outcome + ': alert suppressed, outcome unchanged', rules: {RULES} }})",
    "failed_key_body": "JSON.stringify({ status: 'failed', result: 'alert failed' })",
    "failed_body": f"JSON.stringify({{ recipe: '{R}', item: {ITEM}, reason: 'alert failed', "
                   f"detail: 'Post and email failed for ' + {A}.to + '; reassign the measure or fix the address', "
                   "owner: $('Config').first().json.list_editor })",
}


def both(label: str, *conds: tuple[str, str, str]) -> dict:
    """A filter whose conditions must all hold: (a, b, operator)."""
    return {"name": label, "conditions": [[{"a": a, "b": b, "o": o} for a, b, o in conds]]}


def version_current() -> Scenario:
    s = Scenario(R, "R12.3 Alert the owner when a measure crosses its threshold", "webhook", test_key="r12-3-version-current")
    s.flow.append(s.webhook(T))  # your weekly table calls this when R12.1 marks a version written: {version}
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    reads = [("Read the version", cfg("table_url") + "/versions/{{encodeURL(1.version)}}", None),
             ("Read the table rows", cfg("table_url") + "/weekly_table", {"_wrap": "1", "version": "{{1.version}}"}),
             ("Read the threshold list", cfg("thresholds_url") + "/lines", {"_wrap": "1"}),  # every line version, with its approval stamp
             ("Read versions", cfg("table_url") + "/versions", {"_wrap": "1"}),
             ("Read earlier rows", cfg("table_url") + "/weekly_table", {"_wrap": "1"})]  # last week's, for the second-week rule
    for i, (name, url, q) in enumerate(reads):
        m = s.http(name, "GET", url, query=q)
        if i == 0:
            m["filter"] = s.continue_unless_stopped()
        s.flow.append(m)
    # One item per measure; steps 5 and 9 are applied here. A measure marked "fewer than 3" is never checked.
    code, inputs = n8n_rule(N8N.OUTCOME_JS, {"Config": "{{" + f"{c}.result" + "}}", **{n: data(n) for n, *_ in reads}},
                            many=True, prelude=ALERT_TEXT, bodies=BODIES)
    s.flow.append(s.code(OUTCOME, code, inputs))
    s.flow.append(s.iterator("Each measure", "{{" + f"{s.ref(OUTCOME)}.result.items" + "}}"))
    it = s.ref("Each measure")
    out = lambda f: "{{" + f"{it}.{f}" + "}}"  # noqa: E731
    # Step 3: the key is the week, measure, line version and outcome, so an unchanged outcome alerts once.
    s.flow.append(s.rpc("Step 3: Reserve key", "reserve_key", out("reserve_body")))
    is_new = "{{" + f"{s.ref('Step 3: Reserve key')}.data" + "}}"

    def failed(step: str) -> list[dict]:
        # Post and email both failed, or the alert log refused the entry: mark the key failed, queue it for the list editor.
        return [s.finish_key(f"{step}: mark key failed", out("key_q"), out("failed_key_body")),
                s.exception(f"{step}: exception queue", out("failed_body")), s.ignore()]

    def closing(tag: str) -> list[dict]:
        # Owners read the alert log and mark each alert seen (step 8 reads it on Friday).
        log = f"Steps 4 and 6: Add to the alert log ({tag})"
        return [s.http(log, "POST", cfg("alert_log_url") + "/alerts", body=out("alert_log_body"), parse=False, onerror=failed(log)),
                s.finish_key(f"Mark key done ({tag})", out("key_q"), out("done_body")),
                s.decision_log(f"Step 7: Log every check ({tag})", out("log_sent"))]

    def deliver(attempt: int) -> list[dict]:
        """Post the alert; on an error status try again, up to three posts, then email it.
        Safe to repeat because step 3's key stops a double alert."""
        name = f"Steps 4 and 6: Post the alert (try {attempt})"
        post = s.http(name, "POST", cfg("chat_url") + "/messages", body=out("post_body"), parse=False)
        post["mapper"]["stopOnHttpError"] = False  # the status decides the route below
        status = "{{" + f"{s.ref(name)}.statusCode" + "}}"
        if attempt < 3:
            otherwise = deliver(attempt + 1)
        else:
            email = "Steps 4 and 6: Email the alert"  # a write: never retried
            otherwise = [s.http(email, "POST", cfg("email_url") + "/messages", body=out("post_body"), parse=False,
                                onerror=failed(email))] + closing("emailed")
        return [post, s.router(f"Posted? (try {attempt})", [
            (s.when("posted", status, "300", "number:less"), closing(f"posted, try {attempt}")),
            (s.when("post failed", status, "300", "number:greaterorequal"), otherwise),
        ])]

    s.flow.append(s.router("Outcome", [
        # A copy: the outcome is unchanged since the last version, so the alert is suppressed.
        (s.when("outcome unchanged (a copy)", is_new, "false"),
         [s.decision_log("Step 7: Log every check (suppressed)", out("log_copy"))]),
        (both("new outcome that alerts", (is_new, "true", "text:equal"), (out("alert"), "yes", "text:equal")), deliver(1)),
        (both("new outcome, no alert", (is_new, "true", "text:equal"), (out("alert"), "no", "text:equal")),
         [s.decision_log("Step 7: Log every check (no alert)", out("log_none"))]),
    ]))
    return s


def friday_check() -> Scenario:
    s = Scenario(R, "R12.3 Alert the owner: Friday open issues", "schedule", test_key=F, schedule="every Friday at 16:00")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    s.flow += s.stop_flag()
    read = s.http("Read the alert log", "GET", "{{" + f"{c}" + ".result.alert_log_url}}/alerts", query={"_wrap": "1"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    # Step 8: alerts from the last week not marked "seen" become open issues in the pre-read.
    rule = "Step 8: Rule: alerts not seen"
    code, inputs = n8n_rule(N8N.UNSEEN_JS, {"Read the alert log": "{{" + f"{s.ref('Read the alert log')}.data" + "}}"}, many=True,
                            bodies={"issue_body": "JSON.stringify({ alert: out.id, measure: out.measure, owner: out.owner, text: out.text })"})
    s.flow.append(s.code(rule, code, inputs))
    s.flow.append(s.iterator("Each alert not seen", "{{" + f"{s.ref(rule)}.result.items" + "}}"))
    s.flow.append(s.http("Step 8: Open issue in the pre-read", "POST", "{{" + f"{c}" + ".result.preread_url}}/open_issues",
                         body="{{" + f"{s.ref('Each alert not seen')}.issue_body" + "}}", parse=False))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R12.3/make/, scenario)."""
    return [("blueprint.json", version_current()), ("friday.blueprint.json", friday_check())]
