"""R9.1 Run onboarding: accounts, equipment, training tasks and first-week checklist, as Make scenarios.

Source: book Chapter 9, recipe R9.1, build steps 1 to 9 (recipes/R9.1/build-spec.md);
AI step: recipes/R9.1/prompts/draft-checklist.md. The rules are the n8n build's own JavaScript
(tools/builds/r9_1.py), run through n8n_rule.
Three scenarios, because a Make scenario has one trigger: a hire confirmed, edited or withdrawn
(webhook, steps 1 to 9), the manager's answer (webhook, steps 8 and 9) and the morning check for
silent managers (schedule, every day at 07:00, steps 8 and 9). n8n's "Which event?" node only
asked which trigger ran, so it is not built.

Differences from the n8n build, all forced by Make:
- The rules read the webhook as n8n's $('<trigger>').first().json.body; a Make webhook's output
  cannot be mapped whole, so each field is its own input and the adapter rebuilds the body
  (with_body()), the notes and rows lists included.
- n8n runs three branches from "Step 4: Write the account to the inventory" (groups, tasks, the
  AI draft). Make's router runs the same three routes in that order, each with its own iterator.
- The n8n AI call tries three times (mk's ai_step, tries=3): each try's error route holds the
  next try, and Make's Resume handler hands the last answer on.
- n8n's "Step 7: AI error: template's checklist" node runs inside "Step 7: Rule: use the draft?"
  (on_ai_error), because Make branches never meet again; "Step 7: Read the directory" therefore
  runs before that rule on an AI error too (a read; nothing changes).
- n8n's "Step 9: Checklist that goes" node only joins three paths (start too near, the manager's
  answer, the manager silent). Make's routes never meet again, so step 9 is built once per path,
  named for it, with its bodies computed by the rule before it.
- Each write's error route marks the key failed and adds its exception-queue row (write_failed
  and account_failed()); step 9's writes add the "welcome pack not sent" row, whose detail says
  "send error" because Make's error route does not hand the error text to the next step.
- "Mark key done" never overwrites a failure another route logged: the key-log update matches
  only a key whose status is not "failed" (n8n's finish_unless_failed SQL, over the table API).
- The withdrawn-hire exception row, the message to HR and the decision log carry only IDs, a
  count and fixed text, so their bodies are written by hand (n8n has no Code node there).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R9.1"
N8N = n8n_build(R)
T, A, M = N8N.T, N8N.A, N8N.M
HIRE_FIELDS = ("id", "person_id", "name", "email", "role", "manager", "start_date", "status", "notes")
ANSWER_FIELDS = ("person_id", "decision", "rows")
LISTS = ("notes", "rows")  # webhook fields that are lists of {day, task, owner}
CONFIG = {
    "templates_url": "https://<your role-template list API>",
    "directory_url": "https://<your directory API>",
    "inventory_url": "https://<your access inventory API>",
    "tasks_url": "https://<your task list API>",
    "messaging_url": "https://<your messaging API>",
    "user_group": "<the one group your onboarding service account may create users in>",
    "hr_owner": "<your HR owner>",
    "it_owner": "<your IT owner>",
    "approval_working_days": 2,
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
H = f"$('{T}').first().json.body"
CFG = "$('Config').first().json"
TPL = "$('Step 2: Rule: complete hire?').first().json.template"
COMPLETE = "Step 2: Rule: complete hire?"
CHECK = "Step 7: Rule: use the draft?"
ROUTE = "Step 8: Rule: time for the manager?"
ROWS = "(out.rows || []).map(r => 'Day ' + r.day + ': ' + r.task + ' (' + r.owner + ')').join('\\n')"
NOW = "new Date().toISOString()"


def exc(fields: str) -> str:
    """An exception-queue body: recipe plus the given JavaScript object fields."""
    return f"JSON.stringify({{ recipe: '{R}', {fields} }})"


# Step 9's bodies, from the checklist that goes (out: person_id, email, manager, rows, how, ...).
# A rule that found nothing to send (the manager's answer for a checklist no longer waiting) gets none.
STEP9 = {k: f"(out.person_id ? {v} : null)" for k, v in {
    "goes": "'yes'",
    "person_q": "encodeURIComponent(out.person_id)",
    "record_body": "JSON.stringify(Object.assign({}, out, { route: undefined, status: 'sent' }))",
    "welcome_body": f"JSON.stringify({{ to: out.email, cc: out.manager, subject: 'Welcome: your first week from ' + out.start_date, text: {ROWS} }})",
    "done9_body": "JSON.stringify({ status: 'done', result: 'welcome pack sent: ' + out.how })",
    "log9_body": (f"JSON.stringify({{ recipe: '{R}', item: out.person_id, decision: 'welcome pack sent (' + out.how + ')', "
                  "rules: { template_version: out.template_version, source: out.source, how: out.how, items: (out.rows || []).length } })"),
    "welcome_failed_body": exc("item: out.person_id, reason: 'welcome pack not sent', "
                               f"detail: 'Welcome pack not sent (send error); HR sends it', owner: {CFG}.hr_owner"),
}.items()}


def with_body(m: dict, trigger: str, fields: tuple[str, ...]) -> dict:
    """Give a Code step n8n's $('<trigger>').first().json.body, from the webhook's fields one by one.
    A list field may reach the step as a list, as JSON text or not at all; the rule gets a list."""
    pairs = ", ".join(f"{json.dumps(f)}: " + (f"__list(input.t_{f})" if f in LISTS else f"input.t_{f}") for f in fields)
    shim = ("// The webhook's fields, as the rule reads them in n8n.\n"
            "const __list = v => { if (typeof v === 'string') { try { v = JSON.parse(v); } catch (e) { v = []; } }\n"
            "  return Array.isArray(v) ? v : v && typeof v === 'object' ? Object.values(v) : []; };\n"
            f"DATA[{json.dumps(trigger)}] = [{{ json: {{ body: {{ {pairs} }} }} }}];\n")
    m["mapper"]["codeEditorJavascript"] = m["mapper"]["codeEditorJavascript"].replace("const BODIES = ", shim + "const BODIES = ", 1)
    m["mapper"]["input"] += [{"name": f"t_{f}", "value": "{{1." + f + "}}"} for f in fields]
    return m




def both(label: str, *conds: tuple[str, str, str]) -> dict:
    """A filter whose conditions must all hold: (a, b, operator)."""
    return {"name": label, "conditions": [[{"a": a, "b": b, "o": o} for a, b, o in conds]]}


def start(s: Scenario, trigger: str | None):
    if trigger:
        s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    s.flow += s.stop_flag()
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    res = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    return cfg, res, data, "{{" + f"{c}.result" + "}}"


def done_unless_failed(s: Scenario, name: str, key_q: str, body: str) -> dict:
    """Mark the key done, but never over a failure another route of the same run logged."""
    return s.http(name, "PATCH", s.table(f"/key_log?recipe=eq.{R}&status=neq.failed&key=eq.") + key_q, body=body, parse=False)


def step9(s: Scenario, tag: str, b, cfg) -> list[dict]:
    """Step 9: record the checklist that goes, send the welcome pack, log. b(field) maps a STEP9 body."""
    record, send = f"Step 9: Record the checklist ({tag})", f"Step 9: Send the welcome pack ({tag})"

    def on_fail(step: str) -> list[dict]:
        return [s.exception(f"Step 9: Exception queue: welcome pack not sent ({tag}{', send' if step == send else ''})",
                            b("welcome_failed_body")), s.ignore()]

    first = s.http(record, "PUT", cfg("tasks_url") + "/checklists/" + b("person_q"), body=b("record_body"), parse=False, onerror=on_fail(record))
    first["filter"] = s.when("a checklist goes", b("goes"), "yes")
    return [first,
            s.http(send, "POST", cfg("messaging_url") + "/messages", body=b("welcome_body"), parse=False, onerror=on_fail(send)),
            done_unless_failed(s, f"Mark key done: welcome pack sent ({tag})", b("person_q"), b("done9_body")),
            s.decision_log(f"Step 9: Decision log ({tag})", b("log9_body"))]


def hire() -> Scenario:
    s = Scenario(R, "R9.1 Run onboarding: hire confirmed or changed", "webhook", test_key="r9-1-hire")
    # Your hire list calls this when a hire is saved as confirmed, edited, or set to withdrawn:
    # the list item {id, person_id, name, email, role, manager, start_date, status, notes: [{day, task, owner}]}.
    cfg, res, data, config = start(s, T)
    msg = cfg("messaging_url") + "/messages"
    key_q = "{{encodeURL(1.person_id)}}"
    stopped = s.continue_unless_stopped()["conditions"][0][0]
    status = lambda op: ("{{1.status}}", "withdrawn", op)  # noqa: E731

    def rule(name: str, js: str, sources: dict, **kw) -> dict:
        code, inputs = n8n_rule(js, sources, **kw)
        return with_body(s.code(name, code, inputs), T, HIRE_FIELDS)

    # ---- Step 1: withdrawn asks Aisha to start R9.4 ---------------------------------------
    inv = "Step 1: Read the hire's inventory"
    read_inv = s.http(inv, "GET", cfg("inventory_url") + "/items", query={"_wrap": "1", "person_id": "{{1.person_id}}"})
    read_inv["filter"] = both("withdrawn (stop flag not set)", (stopped["a"], stopped["b"], stopped["o"]), status("text:equal"))
    count = "{{length(" + f"{s.ref(inv)}.data.items" + ")}}"
    hr = cfg("hr_owner")

    def text(t: str) -> str:
        """Fixed text for a hand-written JSON body, with Make mappings left in place."""
        return json.dumps(t)[1:-1]

    withdrawn = [
        read_inv,
        s.exception("Step 1: Exception queue: withdrawn hire",
                    '{"recipe": "' + R + '", "item": "{{1.person_id}}", "reason": "withdrawn hire", "detail": "'
                    + text(f'Withdrawn with {count} inventory item(s). Confirm, then enter the leaver in R9.4 as "immediate"')
                    + '", "owner": "' + hr + '"}'),
        s.http("Step 1: Ask Aisha to start R9.4", "POST", msg, parse=False,
               body='{"to": "' + hr + '", "subject": "Withdrawn hire {{1.person_id}}: start R9.4", "text": "'
               + text(f"Hire {{{{1.person_id}}}} was withdrawn with {count} inventory item(s). "
                      'Confirm it, then add the leaver to the R9.4 list as "immediate".') + '"}'),
        s.decision_log("Step 1: Decision log",
                       '{"recipe": "' + R + '", "item": "{{1.person_id}}", "decision": "withdrawn: asked HR to start R9.4", '
                       '"rules": {"inventory_items": ' + count + "}}"),
    ]


    # ---- Step 2: complete, or back to Aisha ---------------------------------------------------
    tpl_read = s.http("Read the role template", "GET", cfg("templates_url") + "/templates",
                      query={"_wrap": "1", "role": "{{1.role}}", "status": "approved"})
    tpl_read["filter"] = both("not withdrawn (stop flag not set)", (stopped["a"], stopped["b"], stopped["o"]), status("text:notequal"))
    tp = "out.template"
    complete = rule(COMPLETE, N8N.COMPLETE_JS, {"Config": config, "Read the role template": data("Read the role template")}, bodies={
        "complete_flag": "out.complete ? 'yes' : 'no'",
        "returned_body": exc(f"item: {H}.person_id, reason: 'returned to HR', detail: 'Missing: ' + out.missing.join(', ') + '; nothing created', "
                             f"owner: {CFG}.hr_owner"),
        "tell_body": (f"JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Hire ' + {H}.person_id + ' returned: nothing created', "
                      "text: 'Missing: ' + out.missing.join(', ') })"),
        # Step 4's account bodies, for a complete hire only.
        "account_body": (f"({tp} ? JSON.stringify({{ id: {H}.person_id, name: {H}.name, group: {CFG}.user_group, "
                         f"template_version: {tp}.version }}) : null)"),
        "account_inventory_body": (f"({tp} ? JSON.stringify({{ id: {H}.person_id + ':account', person_id: {H}.person_id, kind: 'sso account', "
                                   f"system: 'directory', account: {H}.person_id, via: 'connection', template_version: {tp}.version, "
                                   f"granted: {NOW} }}) : null)"),
        "account_key_failed": "JSON.stringify({ status: 'failed', result: 'account creation failed' })",
        "account_failed_body": exc(f"item: {H}.person_id, reason: 'account creation failed', "
                                   f"detail: 'Account or group not created, never retried; check, then raise an IT ticket', owner: {CFG}.it_owner"),
        "failed_body": exc(f"item: {H}.person_id, reason: 'write failed', detail: 'A task or checklist write failed, never retried; check the hire', "
                           f"owner: {CFG}.hr_owner"),
    }, input_node="Read the role template")
    cp = lambda f: res(COMPLETE, f)  # noqa: E731
    step2 = {"Config": config, COMPLETE: "{{" + f"{s.ref(COMPLETE)}.result" + "}}"}
    incomplete = [s.exception("Step 2: Exception queue: return to Aisha", cp("returned_body")),
                  s.http("Step 2: Tell Aisha", "POST", msg, body=cp("tell_body"), parse=False)]

    def account_failed(step: str) -> list[dict]:
        """An account, group or inventory write failed: mark the key failed, ask IT; never retried."""
        return [s.finish_key(f"{step}: mark key failed", key_q, cp("account_key_failed")),
                s.exception(f"{step}: exception queue", cp("account_failed_body")), s.ignore()]

    failed = lambda step: s.write_failed(step, key_q, cp("failed_body"))  # noqa: E731

    # ---- Step 3: duplicate key, the person ID; a moved start moves the tasks ----------------------
    tasks = "Step 3: Read the hire's tasks"
    read_tasks = s.http(tasks, "GET", cfg("tasks_url") + "/tasks", query={"_wrap": "1", "person_id": "{{1.person_id}}"})
    mv = "Step 3: Rule: start moved?"
    moved = rule(mv, N8N.MOVED_JS, {tasks: data(tasks)}, many=True, bodies={
        "id_q": "encodeURIComponent(out.id)",
        "move_body": "JSON.stringify({ start_date: out.start_date, due: out.due })",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {H}.person_id, decision: 'start moved: task moved to ' + out.due, "
                     "rules: { task: out.id, was: out.was } })"),
    })
    each_mv = s.iterator("Each task to move", "{{" + f"{s.ref(mv)}.result.items" + "}}")
    fm = lambda f: "{{" + f"{s.ref('Each task to move')}.{f}" + "}}"  # noqa: E731
    copy_route = [read_tasks, moved, each_mv,
                  s.http("Step 3: Move the task", "PATCH", cfg("tasks_url") + "/tasks/" + fm("id_q"), body=fm("move_body"), parse=False,
                         onerror=failed("Step 3: Move the task")),
                  s.decision_log("Step 3: Decision log", fm("log_body"))]

    # ---- Step 4: only the template's accounts and groups, each to the inventory -----------------
    account = s.http("Step 4: Create the account", "POST", cfg("directory_url") + "/users", body=cp("account_body"), parse=False,
                     onerror=account_failed("Step 4: Create the account"))  # a write: never retried
    account_inv = s.http("Step 4: Write the account to the inventory", "POST", cfg("inventory_url") + "/items",
                         body=cp("account_inventory_body"), parse=False, onerror=account_failed("Step 4: Write the account to the inventory"))
    gr = "Step 4: Groups from the template"
    groups = rule(gr, N8N.GROUPS_JS, step2, many=True, bodies={
        "member_body": f"JSON.stringify({{ id: {H}.person_id + ':' + out.group, user: {H}.person_id, group: out.group }})",
        "group_inventory_body": (f"JSON.stringify({{ id: {H}.person_id + ':group:' + out.group, person_id: {H}.person_id, kind: 'group', "
                                 f"system: 'directory', account: out.group, via: 'connection', template_version: {TPL}.version, granted: {NOW} }})"),
    })
    each_gr = s.iterator("Each group", "{{" + f"{s.ref(gr)}.result.items" + "}}")
    fg = lambda f: "{{" + f"{s.ref('Each group')}.{f}" + "}}"  # noqa: E731
    group_route = [groups, each_gr,
                   s.http("Step 4: Add to the group", "POST", cfg("directory_url") + "/group_members", body=fg("member_body"), parse=False,
                          onerror=account_failed("Step 4: Add to the group")),
                   s.http("Step 4: Write the group to the inventory", "POST", cfg("inventory_url") + "/items", body=fg("group_inventory_body"),
                          parse=False, onerror=account_failed("Step 4: Write the group to the inventory"))]

    # ---- Step 5: equipment and training tasks -------------------------------------------------------
    tk = "Step 5: Tasks from the template"
    task_rule = rule(tk, N8N.TASKS_JS, step2, many=True, bodies={"task_body": "JSON.stringify(out)"})
    each_tk = s.iterator("Each task", "{{" + f"{s.ref(tk)}.result.items" + "}}")
    task_route = [task_rule, each_tk,
                  s.http("Step 5: Raise the task", "POST", cfg("tasks_url") + "/tasks", body="{{" + f"{s.ref('Each task')}.task_body" + "}}",
                         parse=False, onerror=failed("Step 5: Raise the task"))]

    # ---- Steps 6 and 7: the AI drafts the checklist; a rule decides ------------------------------------
    rows = "rs => (rs || []).map(r => r.day + '; ' + r.task + '; ' + r.owner).join('\\n')"
    vars_js = (f"{{ role: {H}.role, template_version: {TPL}.version, "
               f"template_tasks: ({rows})({TPL}.checklist), manager_notes: ({rows})({H}.notes) || '(none)' }}")
    ai = s.ai_step("Step 6", ROOT / "recipes/R9.1/prompts/draft-checklist.md", vars_js, step2, max_tokens=1024, tries=3)
    with_body(ai[0], T, HIRE_FIELDS)
    call = s.ref("Step 6: AI call")
    directory = s.http("Step 7: Read the directory", "GET", cfg("directory_url") + "/users", query={"_wrap": "1"})
    check = rule(CHECK, N8N.CHECK_JS, {**step2, "Step 7: Read the directory": data("Step 7: Read the directory"),
                                       "Step 6: AI call": "{{" + f"{call}.data" + "}}"},
                 ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=N8N.AI_ERROR_JS)

    # ---- Step 8: the manager approves or edits; under 2 working days the template's goes now -----------
    route = rule(ROUTE, N8N.ROUTE_JS, {**step2, CHECK: "{{" + f"{s.ref(CHECK)}.result" + "}}"}, bodies={
        "checklist_body": "JSON.stringify(Object.assign({}, out, { route: undefined, status: 'awaiting manager' }))",
        "ask_body": (f"JSON.stringify({{ to: out.manager, subject: 'Approve or edit the first-week checklist for ' + out.name, text: {ROWS} }})"),
        "manager_done_body": "JSON.stringify({ status: 'done', result: 'checklist with the manager' })",
        "manager_log_body": (f"JSON.stringify({{ recipe: '{R}', item: {H}.person_id, decision: 'checklist to the manager (' + out.source + ')', "
                             "rules: { template_version: out.template_version, source: out.source, rejected: out.reason || 'no' } })"),
        **STEP9,
    })
    rt = lambda f: res(ROUTE, f)  # noqa: E731
    to_manager = [
        s.http("Step 8: Checklist to the manager", "PUT", cfg("tasks_url") + "/checklists/" + rt("person_q"), body=rt("checklist_body"),
               parse=False, onerror=failed("Step 8: Checklist to the manager")),
        s.http("Step 8: Ask the manager to approve or edit", "POST", msg, body=rt("ask_body"), parse=False,
               onerror=failed("Step 8: Ask the manager to approve or edit")),
        done_unless_failed(s, "Mark key done: with the manager", key_q, rt("manager_done_body")),
        s.decision_log("Step 8: Decision log", rt("manager_log_body")),
    ]
    ai_route = ai + [directory, check, route, s.router("To the manager?", [
        (s.when("to the manager", rt("route"), "manager"), to_manager),
        (s.when("start too near: the template's goes now", rt("route"), "now"), step9(s, "start too near", rt, cfg)),
    ])]

    new = [account, account_inv, s.router("Account written: groups, tasks, checklist", [
        (None, group_route), (None, task_route), (None, ai_route)])]
    reserve = s.reserve_key("Step 3: Reserve key", "{{1.person_id}}")
    s.flow.append(s.router("Step 1: Withdrawn?", [
        (None, withdrawn),
        (None, [tpl_read, complete, s.router("Complete?", [
            (s.when("incomplete", cp("complete_flag"), "no"), incomplete),
            (s.when("complete", cp("complete_flag"), "yes"), [reserve, s.router("New key?", [
                (s.when("logged before (a copy)", "{{" + f"{s.ref('Step 3: Reserve key')}.data" + "}}", "false"), copy_route),
                (s.is_new_key("Step 3: Reserve key"), new),
            ])]),
        ])]),
    ]))
    return s


def manager_answers() -> Scenario:
    s = Scenario(R, "R9.1 Run onboarding: manager answers", "webhook", test_key="r9-1-manager-answer")
    # The manager's approval calls this: {person_id, decision: approved | edited, rows (if edited)}.
    cfg, res, data, config = start(s, A)
    rd = "Step 8: Read the checklist"
    read = s.http(rd, "GET", cfg("tasks_url") + "/checklists", query={"_wrap": "1", "person_id": "{{1.person_id}}"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    an = "Step 8: Rule: manager's answer"
    code, inputs = n8n_rule(N8N.ANSWER_JS, {"Config": config, rd: data(rd)}, bodies=STEP9)
    s.flow.append(with_body(s.code(an, code, inputs), A, ANSWER_FIELDS))
    s.flow += step9(s, "manager answered", lambda f: res(an, f), cfg)
    return s


def morning_check() -> Scenario:
    s = Scenario(R, "R9.1 Run onboarding: morning check for silent managers", "schedule", test_key=M, schedule="every day at 07:00")
    cfg, res, data, config = start(s, None)
    rd = "Step 8: Read checklists awaiting the manager"
    read = s.http(rd, "GET", cfg("tasks_url") + "/checklists", query={"_wrap": "1", "status": "awaiting manager"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    sn = "Step 8: Rule: manager silent, start near"
    code, inputs = n8n_rule(N8N.SILENT_JS, {"Config": config, rd: data(rd)}, many=True, bodies=STEP9)
    s.flow.append(s.code(sn, code, inputs))
    s.flow.append(s.iterator("Each checklist that goes", "{{" + f"{s.ref(sn)}.result.items" + "}}"))
    it = s.ref("Each checklist that goes")
    s.flow += step9(s, "manager silent", lambda f: "{{" + f"{it}.{f}" + "}}", cfg)
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R9.1/make/, scenario)."""
    return [("blueprint.json", hire()), ("answer.blueprint.json", manager_answers()), ("morning.blueprint.json", morning_check())]
