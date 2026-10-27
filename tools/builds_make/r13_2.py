"""R13.2 Flag stale documents to their owners and pull expired ones from answers, as Make scenarios: rules only, no AI step.

Source: book Chapter 13, recipe R13.2, build steps 1 to 11 (recipes/R13.2/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r13_2.py), run through n8n_rule.
Two scenarios, because a Make scenario has one trigger: a published version (webhook, step 9)
and the weekly check (schedule, every Monday at 06:00; move it if Monday is not your first
working day). The rules use plain Date in UTC, which Make's Code app has, so no shim is needed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R13.2"
N8N = n8n_build(R)
W, V = N8N.W, N8N.V
CONFIG = {
    "register_url": "https://<your source register API>",
    "directory_url": "https://<your directory API>",
    "documents_url": "https://<your document home API>",
    "index_url": "https://<your answer index API>",
    "messaging_url": "https://<your messaging API>",
    "due_within_days": 14,
    "expiry_after_review_days": 30,
    "inactive_statuses": ["withdrawn", "retired"],
    "archive_folder": "<your archive no bought assistant can open>",
    "owner_form_url": "https://<your owner form>",
    "register_admin": "<your register admin, who edits owners and dates>",
}

# The n8n build's "Split the actions" node only turns the rule's actions into items; here the
# iterator does that, and each action carries the request bodies its route maps whole.
ACTION_BODIES = f"""
// Each action's request bodies, the same fields the n8n build's steps write.
const actionBodies = (a) => {{
  const cfg = $('Config').first().json;
  const admin = cfg.register_admin, form = cfg.owner_form_url;
  return Object.assign({{}}, a, {{
    key_q: encodeURIComponent(a.key), source_q: encodeURIComponent(a.source), file_q: encodeURIComponent(a.file_id || ''),
    reserve_body: JSON.stringify({{ p_recipe: '{R}', p_key: a.key }}),
    withdrawn_body: JSON.stringify({{ status: 'withdrawn', withdrawn_reason: a.reason }}),
    withdraw_message: JSON.stringify({{ to: admin, subject: 'Source withdrawn: ' + (a.title || a.source),
      text: a.title + ' has ' + a.reason + ', so it is withdrawn and answers nothing until it has an owner and dates.' }}),
    reassign_exception: JSON.stringify({{ recipe: '{R}', item: a.source, reason: 'owner left',
      detail: a.title + ': ' + a.reason + ' (' + a.owner + ')', owner: admin }}),
    reassign_message: JSON.stringify({{ to: admin, subject: 'Reassign the owner: ' + a.title,
      text: a.title + ': ' + a.reason + ' (' + a.owner + '). Name a new owner in the register.' }}),
    remind_message: JSON.stringify({{ to: a.recipient, subject: 'Review due: ' + a.title,
      text: a.title + ' is due for review on ' + a.review_date + '. It is withdrawn from answers on ' + a.pull_date +
            ' unless you renew, replace or retire it: ' + form }}),
    archive_body: JSON.stringify({{ folder: cfg.archive_folder }}),
    expired_message: JSON.stringify({{ to: a.recipient, cc: admin, subject: 'Withdrawn: ' + a.title,
      text: a.title + ' passed its expiry date (' + a.pull_date + ') and is withdrawn and archived. Renew, replace or retire it: ' + form }}),
    mismatch_exception: JSON.stringify({{ recipe: '{R}', item: a.source, reason: 'register mismatch', detail: a.title + ': ' + a.reason, owner: admin }}),
    mismatch_message: JSON.stringify({{ to: admin, subject: 'Register mismatch: ' + a.title, text: a.title + ': ' + a.reason }}),
    done_body: JSON.stringify({{ status: 'done', result: a.action }}),
    log_body: JSON.stringify({{ recipe: '{R}', item: a.source, decision: a.action,
      rules: {{ reason: a.reason, week_key: a.key, recipient: a.recipient || null, pull_date: a.pull_date || null }} }}),
    failed_body: JSON.stringify({{ recipe: '{R}', item: a.source, reason: 'write failed',
      detail: 'Step ' + a.action + ' failed part way; check the source, never retried', owner: admin }}),
  }});
}};
"""


def both(label: str, *conds: tuple[str, str, str]) -> dict:
    """A filter whose conditions must all hold: (a, b, operator)."""
    return {"name": label, "conditions": [[{"a": a, "b": b, "o": o} for a, b, o in conds]]}


def weekly_check() -> Scenario:
    s = Scenario(R, "R13.2 Flag stale documents: weekly check", "schedule", test_key=W, schedule="every Monday at 06:00")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    reads = [("Step 2: Read the register", "register_url", "/sources"),
             ("Read the directory", "directory_url", "/users"),  # read-only: who is active, and who is on leave
             ("Step 10: Read sharing", "documents_url", "/files"),
             ("Step 10: Read the index", "index_url", "/sources")]
    for i, (name, url, path) in enumerate(reads):
        m = s.http(name, "GET", cfg(url) + path, query={"_wrap": "1"})
        if i == 0:
            m["filter"] = s.continue_unless_stopped()
        s.flow.append(m)
    rules = "Rules: steps 2, 4 to 7 and 10"
    code, inputs = n8n_rule(N8N.RULES_JS, {"Config": "{{" + f"{c}.result" + "}}", **{n: data(n) for n, *_ in reads}},
                            prelude=ACTION_BODIES, bodies={
        "weekly_log_body": f"JSON.stringify({{ recipe: '{R}', item: 'week ' + out.week, decision: 'weekly check', "
                           "rules: { sources_checked: out.checked, actions: out.actions.map(a => a.source + ': ' + a.action) } })",
        "split": "out.actions.map(actionBodies)",
    })
    s.flow.append(s.code(rules, code, inputs))
    ru = s.ref(rules)
    s.flow.append(s.decision_log("Step 11: Log the weekly check", "{{" + f"{ru}.result.weekly_log_body" + "}}"))
    s.flow.append(s.iterator("Split the actions", "{{" + f"{ru}.result.split" + "}}"))
    it = s.ref("Split the actions")
    act = lambda f: "{{" + f"{it}.{f}" + "}}"  # noqa: E731
    s.flow.append(s.rpc("Step 3: Reserve key", "reserve_key", act("reserve_body")))
    new = ("{{" + f"{s.ref('Step 3: Reserve key')}.data" + "}}", "true", "text:equal")
    msg = cfg("messaging_url") + "/messages"
    src = cfg("register_url") + "/sources/" + act("source_q")

    def write(name: str, method: str, url: str, body: str) -> dict:
        # A write: never retried; a failure marks the key failed and goes to the exception queue.
        return s.http(name, method, url, body=act(body), parse=False, onerror=s.write_failed(name, act("key_q"), act("failed_body")))

    def route(action: str, tag: str, steps: list[dict]):
        # A copy (this source, week and action was handled before) matches no route and stops here.
        flow = steps + [s.finish_key(f"Mark key done ({tag})", act("key_q"), act("done_body")),
                        s.decision_log(f"Step 11: Decision log ({tag})", act("log_body"))]
        return both(f"new key, action is {action}", new, (act("action"), action, "text:equal")), flow

    s.flow.append(s.router("Action", [
        # Step 4: no owner or review date means withdrawn, with the register admin alerted.
        route("withdraw_missing", "withdrawn, missing", [
            write("Step 4: Set withdrawn", "PATCH", src, "withdrawn_body"),
            write("Step 4: Alert the register admin", "POST", msg, "withdraw_message")]),
        # Step 5: a departed owner goes to the register admin to reassign.
        route("reassign", "reassign", [
            s.exception("Step 5: Exception queue: reassign the owner", act("reassign_exception")),
            write("Step 5: Tell the register admin to reassign", "POST", msg, "reassign_message")]),
        # Step 6: due within the window, or past review: remind the owner with the pull date.
        route("remind", "remind", [write("Step 6: Remind the owner, with the pull date", "POST", msg, "remind_message")]),
        # Step 7: past expiry: withdraw, archive where no bought assistant's search reaches, tell the owner and admin.
        route("withdraw_expired", "withdrawn, expired", [
            write("Step 7: Set withdrawn", "PATCH", src, "withdrawn_body"),
            write("Step 7: Archive the file", "PATCH", cfg("documents_url") + "/files/" + act("file_q"), "archive_body"),
            write("Step 7: Tell the owner and the register admin", "POST", msg, "expired_message")]),
        # Step 10: stored audience against live sharing, and register version against the index.
        route("mismatch", "mismatch", [
            s.exception("Step 10: Exception queue: mismatch", act("mismatch_exception")),
            write("Step 10: Tell the register admin", "POST", msg, "mismatch_message")]),
    ]))
    # Step 8 (the owner renews, replaces or retires the source) is a person step, through the
    # owner form linked in every reminder and withdrawal; a published version starts step 9.
    return s


def version_published() -> Scenario:
    s = Scenario(R, "R13.2 Flag stale documents: major version published", "webhook", test_key="r13-2-version-published")
    s.flow.append(s.webhook(V))  # your document home calls this with {source_id, version, major}
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    s.flow += s.stop_flag()
    # Step 9: only a major version rebuilds the passages (step 10 compares major versions); a minor one stops here.
    key = "{{1.source_id}}:{{1.version}}:rebuild"
    reserve = s.reserve_key("Step 9: Reserve key", key)
    stop = s.continue_unless_stopped()["conditions"][0][0]
    reserve["filter"] = both("stop flag not set, major version", (stop["a"], stop["b"], stop["o"]), ("{{1.major}}", "true", "text:equal"))
    s.flow.append(reserve)
    key_q = "{{encodeURL(1.source_id)}}%3A{{encodeURL(1.version)}}%3Arebuild"
    fail = [s.finish_key("Step 9: Mark key failed", key_q, '{"status": "failed", "result": "rebuild request failed"}'),
            s.exception("Step 9: Exception queue: rebuild failed",
                        '{"recipe": "' + R + '", "item": "{{1.source_id}}", "reason": "write failed", '
                        '"detail": "Index rebuild request failed; rerun it (step 10 also flags the version)", '
                        '"owner": "{{' + f"{c}" + '.result.register_admin}}"}'),
            s.ignore()]
    # The index cuts the new version at headings and removes the old version's passages. Only IDs are in these bodies.
    rebuild = s.http("Step 9: Index: rebuild the source's passages", "POST", "{{" + f"{c}" + ".result.index_url}}/rebuilds",
                     body='{"source_id": "{{1.source_id}}", "version": "{{1.version}}", "remove_older_versions": true}',
                     parse=False, onerror=fail)
    rebuild["filter"] = s.is_new_key("Step 9: Reserve key")  # a copy stops here: this version was rebuilt before
    s.flow.append(rebuild)
    s.flow.append(s.finish_key("Step 9: Mark key done", key_q, '{"status": "done", "result": "rebuild requested"}'))
    s.flow.append(s.decision_log("Step 9: Decision log",
                                 '{"recipe": "' + R + '", "item": "{{1.source_id}}", "decision": "rebuild passages", '
                                 '"rules": {"version": "{{1.version}}", "major": true}}'))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R13.2/make/, scenario)."""
    return [("blueprint.json", version_published()), ("weekly.blueprint.json", weekly_check())]
