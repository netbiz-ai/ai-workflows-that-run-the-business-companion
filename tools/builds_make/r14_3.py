"""R14.3 Chase overdue actions and carry them into the next agenda, as Make scenarios: rules only, no AI step.

Source: book Chapter 14, recipe R14.3, build steps 1 to 10 (recipes/R14.3/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r14_3.py), run through n8n_rule.
Three scenarios, because a Make scenario has one trigger: the chair's decisions after each
meeting (webhook, step 9), the morning chase (schedule, every day at 06:00; step 1's rule skips
weekends and holidays) and the Friday comparison and count (schedule, Fridays at 06:00, step 8).
The morning and Friday scenarios share one builder; each keeps only the routes its rules can
produce (the morning run never tracks or counts, the Friday run never reminds or marks closed).
The rules use plain Date in UTC, which Make's Code app has, so no shim is needed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R14.3"
N8N = n8n_build(R)
D, F, A = N8N.D, N8N.F, N8N.A
CONFIG = {
    "register_url": "https://<your meeting register API>",
    "tasks_url": "https://<your task system API>",
    "tracking_url": "https://<your tracking list API>",
    "calendar_url": "https://<your calendar API>",
    "agenda_url": "https://<your agenda list API>",
    "workdays_url": "https://<your working-day calendar API>",
    "messaging_url": "https://<your messaging API>",
    "working_weekdays": [1, 2, 3, 4, 5],
    "meeting_window_days": 14,
    "register_owner": "<your register owner>",
    "exception_owner": "<your workflow editor>",
}
CFG = "$('Config').first().json"
CHAIR = "Step 9: Read the chair's decisions"
# The decision a keyed route records, as in the n8n build's "Mark key done" and "Decision log".
DECISION = ("(out.kind === 'remind' ? 'reminded' : out.kind === 'agenda' ? 'on agenda ' + out.meeting_id : "
            "'register owner told: no meeting')")
BODIES = {
    "key_q": "encodeURIComponent(out.key || '')",
    "task_q": "encodeURIComponent(out.task_id || '')",
    "agenda_item_q": "encodeURIComponent(out.agenda_item_id || '')",
    "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.key }})",
    "row_body": "JSON.stringify(out.row || {})",
    "remind_message": "JSON.stringify({ to: [out.owner_email], subject: 'Overdue action: ' + out.title, "
                      "text: out.title + ' was due ' + out.due_date + ' (' + out.series + '). Source: ' + out.source_link })",
    "sent_body": "JSON.stringify({ reminder_state: 'sent', reminded_on: new Date().toISOString().slice(0, 10) })",
    "pending_body": f"JSON.stringify({{ p_recipe: '{R}', p_item: out.key, p_reason: 'reminder key pending', "
                    "p_detail: 'The reminder may have been sent but was never marked sent; it is not resent. Release or close the key.', "
                    f"p_owner: {CFG}.exception_owner }})",
    "agenda_body": "JSON.stringify({ meeting_id: out.meeting_id, series_id: out.series_id, task_id: out.task_id, action: out.title, "
                   "owner: out.owner, verified_date: out.verified_date, due_date: out.due_date, days_overdue: out.days_overdue, "
                   "reason: out.why, status: 'listed' })",
    "register_message": f"JSON.stringify({{ to: [{CFG}.register_owner], subject: 'No meeting within ' + {CFG}.meeting_window_days + ' days: ' + out.series, "
                        f"text: out.title + ' (' + out.owner + '), verified for ' + out.verified_date + ', is ' + out.days_overdue + ' day(s) overdue (' + out.why + '), and ' + out.series + ' has no meeting within ' + {CFG}.meeting_window_days + ' days.' }})",
    "done_body": f"JSON.stringify({{ status: 'done', result: {DECISION} }})",
    "log_body": f"JSON.stringify({{ recipe: '{R}', item: out.task_id, decision: {DECISION}, "
                "rules: { key: out.key, series: out.series_id, reason: out.why || 'overdue', days_overdue: out.days_overdue } })",
    "failed_body": f"JSON.stringify({{ recipe: '{R}', item: out.key, reason: 'write failed', "
                   f"detail: 'A send or write failed; never retried. Check, then release or close the key.', owner: {CFG}.exception_owner }})",
    "other_failed_body": f"JSON.stringify({{ recipe: '{R}', item: out.task_id || ('weekly count ' + out.date), reason: 'write failed', "
                         f"detail: 'A tracking-list, agenda or count write failed; never retried.', owner: {CFG}.exception_owner }})",
    "track_log_body": f"JSON.stringify({{ recipe: '{R}', item: out.task_id, decision: out.row && out.row.changes ? 'due date change tracked' : 'first seen', "
                      "rules: { changes: out.row && out.row.changes, series: out.row && out.row.series_id } })",
    "count_message": f"JSON.stringify({{ to: [{CFG}.register_owner], subject: 'Open overdue actions by series: ' + out.total, "
                     "text: Object.entries(out.counts || {}).map(([s, n]) => s + ': ' + n).join('\\n') || 'None overdue.' })",
    "count_log_body": f"JSON.stringify({{ recipe: '{R}', item: 'weekly count ' + out.date, decision: 'weekly count sent', "
                      "rules: { by_series: out.counts, total: out.total } })",
}


def chase(trigger: str) -> Scenario:
    """The morning chase (steps 1 to 7 and 10) or the Friday run (step 8), by trigger."""
    friday = trigger == F
    s = (Scenario(R, "R14.3 Chase overdue actions: Friday comparison and count", "schedule", test_key=F, schedule="every Friday at 06:00")
         if friday else
         Scenario(R, "R14.3 Chase overdue actions: each working morning", "schedule", test_key=D,
                  schedule="every day at 06:00 (step 1's rule skips weekends and holidays)"))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    hol = s.http("Read holidays", "GET", cfg("workdays_url") + "/holidays", query={"_wrap": "1"})
    hol["filter"] = s.continue_unless_stopped()
    s.flow.append(hol)
    # Step 1: the Friday count always runs, as the heartbeat; the morning run skips weekends and holidays.
    code, inputs = n8n_rule(N8N.WORKDAY_JS, {"Config": "{{" + f"{c}.result" + "}}", "Read holidays": data("Read holidays")},
                            executed=(trigger,))
    s.flow.append(s.code("Step 1: Rule: working day?", code, inputs))
    wd = s.ref("Step 1: Rule: working day?")
    reads = [("Read the register", "register_url", "/series", {}),
             ("Read tasks", "tasks_url", "/tasks", {}),
             ("Read the tracking list", "tracking_url", "/rows", {}),
             ("Read series meetings", "calendar_url", "/meetings", {}),
             ("Read listed agenda items", "agenda_url", "/items", {"status": "listed"})]
    for i, (name, url, path, q) in enumerate(reads):
        m = s.http(name, "GET", cfg(url) + path, query={"_wrap": "1", **q})
        if i == 0:
            m["filter"] = s.when("run today", "{{" + f"{wd}.result.run" + "}}", "true")  # not a working day: stop
        s.flow.append(m)
    code, inputs = n8n_rule(N8N.RULES_JS, {
        "Config": "{{" + f"{c}.result" + "}}",
        "Step 1: Rule: working day?": "{{" + f"{wd}.result" + "}}",
        "Read holidays": data("Read holidays"),
        **{name: data(name) for name, *_ in reads},
    }, many=True, bodies=BODIES)
    s.flow.append(s.code("Steps 2 to 8: Rules", code, inputs))
    s.flow.append(s.iterator("Each action", "{{" + f"{s.ref('Steps 2 to 8: Rules')}.result.items" + "}}"))
    it = s.ref("Each action")
    out = lambda f: "{{" + f"{it}.{f}" + "}}"  # noqa: E731
    msg = cfg("messaging_url") + "/messages"
    track_url = cfg("tracking_url") + "/rows/" + out("task_q")
    keyed_failed = lambda step: s.write_failed(step, out("key_q"), out("failed_body"))  # noqa: E731

    def other_failed(step: str) -> list[dict]:
        """A tracking-list, agenda or count write holds no key: the exception row, then skip this action."""
        return [s.exception(f"{step}: exception queue", out("other_failed_body")), s.ignore()]

    def keyed(tag: str, reserve: str, writes: list[tuple[str, str, str, str]]) -> list[dict]:
        """Reserve the route's key; a new key gets the writes, then the closing steps."""
        flow = [s.rpc(reserve, "reserve_key", out("reserve_body"))]
        for i, (name, method, url, body) in enumerate(writes):
            w = s.http(name, method, url, body=body, parse=False, onerror=keyed_failed(name))
            if i == 0:
                w["filter"] = s.is_new_key(reserve)  # a copy stops here: reminded, listed or told already
            flow.append(w)
        flow.append(s.finish_key(f"Mark key done ({tag})", out("key_q"), out("done_body")))
        flow.append(s.decision_log(f"Decision log ({tag})", out("log_body")))
        return flow

    def agenda(tag: str) -> list[dict]:
        # Steps 5 and 6: the series' next meeting within the window gets an agenda item, for the chair to decide.
        return keyed(tag, "Step 6: Reserve agenda key",
                     [("Step 6: Add the agenda item", "POST", cfg("agenda_url") + "/items", out("agenda_body"))])

    def no_meeting(tag: str) -> list[dict]:
        # Step 7: no meeting within the window, and the register owner is told once.
        return keyed(tag, "Step 7: Reserve no-meeting key",
                     [("Step 7: Tell the register owner", "POST", msg, out("register_message"))])

    kind = lambda k: s.when(f"action is {k}", out("kind"), k)  # noqa: E731
    if not friday:
        # Steps 3 and 4: one reminder per verified date; the key is written "pending" before the message.
        remind = keyed("reminded", "Step 3: Reserve reminder key", [
            ("Step 4: Write the key pending", "PUT", track_url, out("row_body")),
            ("Step 4: Remind the owner", "POST", msg, out("remind_message")),
            ("Step 4: Mark it sent", "PATCH", track_url, out("sent_body")),
        ])
        # A "pending" key is never resent; one open exception per key.
        pending = [s.rpc("Step 4: Pending key: Owen checks", "add_exception_once", out("pending_body"))]
        # Step 10: a task closed after listing is marked, never removed.
        closed = [s.http("Step 10: Mark closed since listed", "PATCH", cfg("agenda_url") + "/items/" + out("agenda_item_q"),
                         body='{"status": "closed since listed"}', parse=False,
                         onerror=other_failed("Step 10: Mark closed since listed"))]
        routes = [(kind("remind"), remind), (kind("pending"), pending), (kind("agenda"), agenda("on agenda")),
                  (kind("no_meeting"), no_meeting("no meeting")), (kind("closed"), closed)]
    else:
        # Step 8: compare due dates with the tracking list; a second change goes on the agenda.
        track = [s.http("Step 8: Update the tracking list", "PUT", track_url, body=out("row_body"), parse=False,
                        onerror=other_failed("Step 8: Update the tracking list")),
                 s.decision_log("Step 8: Decision log: date change", out("track_log_body"))]
        # By series, never by person: a per-person ranking is a performance record nobody approved.
        count = [s.http("Step 8: Send the weekly count", "POST", msg, body=out("count_message"), parse=False,
                        onerror=other_failed("Step 8: Send the weekly count")),
                 s.decision_log("Step 8: Decision log: weekly count", out("count_log_body"))]
        routes = [(kind("agenda"), agenda("on agenda")), (kind("no_meeting"), no_meeting("no meeting")),
                  (kind("track"), track), (kind("count"), count)]
    s.flow.append(s.router("Action", routes))
    return s


def meeting_decided() -> Scenario:
    """Step 9: after each meeting, a new date the chair decided becomes the verified date."""
    s = Scenario(R, "R14.3 Chase overdue actions: after each meeting", "webhook", test_key="r14-3-meeting-decided")
    s.flow.append(s.webhook(A))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    read = s.http(CHAIR, "GET", cfg("agenda_url") + "/items",
                  query={"_wrap": "1", "meeting_id": "{{1.meeting_id}}"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    code, inputs = n8n_rule(N8N.DECISIONS_JS, {
        "Config": "{{" + f"{c}.result" + "}}",
        CHAIR: "{{" + f"{s.ref(CHAIR)}.data" + "}}",
    }, many=True, bodies={
        "task_q": "encodeURIComponent(out.task_id)",
        "verify_body": "JSON.stringify({ verified_date: out.new_date, last_due_seen: out.new_date, changes: 0 })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: out.task_id, decision: 'new date verified', "
                    "rules: { meeting: out.meeting_id, verified_date: out.new_date } })",
        "failed_body": f"JSON.stringify({{ recipe: '{R}', item: out.task_id, reason: 'write failed', "
                       f"detail: 'Verified-date write failed; never retried', owner: {CFG}.exception_owner }})",
    })
    s.flow.append(s.code("Step 9: Rule: new dates", code, inputs))
    s.flow.append(s.iterator("Each new date", "{{" + f"{s.ref('Step 9: Rule: new dates')}.result.items" + "}}"))
    it = s.ref("Each new date")
    # A new date becomes verified and resets the change count; the chair moves the task, not this workflow.
    s.flow.append(s.http("Step 9: Verify the new date", "PATCH", cfg("tracking_url") + "/rows/{{" + f"{it}.task_q" + "}}",
                         body="{{" + f"{it}.verify_body" + "}}", parse=False,
                         onerror=[s.exception("Step 9: Exception queue: write failed", "{{" + f"{it}.failed_body" + "}}"), s.ignore()]))
    s.flow.append(s.decision_log("Step 9: Decision log", "{{" + f"{it}.log_body" + "}}"))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R14.3/make/, scenario)."""
    return [("blueprint.json", meeting_decided()), ("morning.blueprint.json", chase(D)), ("friday.blueprint.json", chase(F))]
