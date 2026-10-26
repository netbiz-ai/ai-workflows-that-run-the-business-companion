"""R14.2 Create tasks with owners and due dates after verification, as a Make scenario: rules only, no AI step.

Source: book Chapter 14, recipe R14.2, build steps 1 to 9 and Table 14.1 (recipes/R14.2/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r14_2.py), run through n8n_rule.
One scenario: the list changing to "verified" (webhook). The rules use plain Date in UTC, which
Make's Code app has, so no shim is needed.

Where the Make build differs from the n8n canvas, and why:
- Branches never meet again after a router, so the owner-outside route (step 3 first) and the
  staff route each carry steps 6 to 8, and step 7's retry repeats the write-back.
- Step 9 retries task creation once (book): the first try reads its own status and a router sends
  a failure to the second try, whose error route tells the chair. The search for the item ID keeps
  the n8n build's error route to the chair and, as a read with a hand-off, does not retry.
- Step 8's one message per owner needs every created task of the list together, which Make can
  gather only on one route: after the items are done, a last route reads the list again and the
  n8n build's grouping runs over the items whose write-back carries this run's stamp.
- Two "verified" presses arrive close together; the scenario processes them one at a time
  (sequential processing), so steps 5 and 6 see the first run's task IDs, as in n8n.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R14.2"
N8N = n8n_build(R)
T, RULES = N8N.T, "Steps 2 to 5: Rules"
CONFIG = {
    "register_url": "https://<your meeting register API>",
    "actions_url": "https://<your action list API>",
    "directory_url": "https://<your staff directory API>",
    "tasks_url": "https://<your task system API>",
    "minutes_url": "https://<your minutes API>",
    "messaging_url": "https://<your messaging API>",
    "register_owner": "<your register owner>",
    "exception_owner": "<your workflow editor>",
}
FIELDS = ("series_id", "occurrence_id", "verified_by")
TASK_ID = "__TASK_ID__"  # replaced in the mapping by the task system's ID, the only value not known to the rules

# The webhook's fields, as n8n's Webhook node gives them ($('Step 1: List verified').first().json.body).
WEBHOOK = (f"DATA[{T!r}] = [{{ json: {{ body: {{ "
           + ", ".join(f"{f}: input.ev_{f}" for f in FIELDS) + " } } }];\n"
           "// One stamp for the run: every task-ID write-back carries it, so step 8 finds this run's new tasks.\n"
           "const STAMP = new Date().toISOString();\n")
CFG = "$('Config').first().json"
EV = f"$('{T}').first().json.body"
LOG = f"{{ recipe: '{R}', item: out.item_id, approved_by: out.verified_by"
BODIES = {
    "stamp": "STAMP",
    "item_q": "encodeURIComponent(out.item_id || '')",
    # Step 2: a list verified by anyone but the series' chair or backup creates nothing.
    "refuse_exception": f"JSON.stringify({{ recipe: '{R}', item: {EV}.occurrence_id, reason: 'verifier not chair or backup', "
                        f"detail: out.reason + ': ' + {EV}.verified_by, owner: {CFG}.register_owner }})",
    "refuse_message": f"JSON.stringify({{ to: [{CFG}.register_owner], subject: 'Action list not verified by its chair or backup', "
                      f"text: 'No tasks created for meeting ' + {EV}.occurrence_id + ': ' + out.reason + ' (' + {EV}.verified_by + ').' }})",
    "return_body": "JSON.stringify({ status: 'returned', return_reason: (out.reasons || []).join('; ') })",
    "log_returned": f"JSON.stringify(Object.assign({LOG}, decision: 'returned to chair' }}, {{ rules: {{ reasons: out.reasons }} }}))",
    "minutes_body": "JSON.stringify(out.minutes || {})",
    "task_body": "JSON.stringify({ title: out.title, owner: out.task_owner, owner_email: out.task_email, due_date: out.due_date, "
                 "verified_due_date: out.due_date, series: out.series, series_id: out.series_id, source_link: out.source_link, "
                 "item_id: out.item_id, quoted_line: out.quoted_line, verified_by: out.verified_by, status: 'open' })",
    "created_body": f"JSON.stringify({{ task_id: '{TASK_ID}', verified_due_date: out.due_date, verified_at: STAMP }})",
    "found_body": f"JSON.stringify({{ task_id: '{TASK_ID}' }})",
    "log_created": f"JSON.stringify(Object.assign({LOG}, decision: 'task created' }}, {{ rules: {{ task_id: '{TASK_ID}', route: out.route }} }}))",
    "log_found": f"JSON.stringify(Object.assign({LOG}, decision: 'existing task linked' }}, {{ rules: {{ task_id: '{TASK_ID}', route: out.route }} }}))",
    "task_error": f"JSON.stringify({{ recipe: '{R}', item: out.item_id, reason: 'task system error', "
                  "detail: 'Task system failed after one retry', owner: out.chair })",
    "task_error_message": "JSON.stringify({ to: [out.chair], subject: 'Task not created: ' + out.series, "
                          "text: 'The task system failed after one retry for: ' + out.title + '. Owen reruns the list; items with a task ID are skipped.' })",
    "write_failed": f"JSON.stringify({{ recipe: '{R}', item: {EV}.occurrence_id, reason: 'write failed', "
                    f"detail: 'A write or message failed; never retried. Check the list, then rerun it: steps 5 and 6 guard.', owner: {CFG}.exception_owner }})",
}

# Steps 4 and 8 group items with n8n's itemMatching(i): the i-th item of the node, as the adapter lists them.
MATCHING = "const __outer = $;\n{\nconst $ = (node) => Object.assign(__outer(node), { itemMatching: (i) => __outer(node).all()[i] });\n"

# Step 8 after the items are done: the tasks this run created are the list items whose write-back carries
# this run's stamp; give the n8n grouping the same inputs it reads in n8n, one per created task, in order.
CREATED = r"""
// The n8n build's inputs for this step: each created task and its rules item, in the list's order.
const __rules = DATA['Steps 2 to 5: Rules'].map(i => i.json);
const __created = (DATA['Step 8: Read the list again'][0].json.items || [])
  .filter(it => it.task_id && it.verified_at === (__rules[0] || {}).stamp)
  .map(it => ({ item: it, rule: __rules.find(r => r.item_id === it.id) })).filter(c => c.rule);
DATA['Step 7: Create the task'] = __created.map(c => ({ json: { id: c.item.task_id } }));
DATA['Steps 2 to 5: Rules'] = __created.map(c => ({ json: c.rule }));
"""


class SequentialScenario(Scenario):
    """A scenario whose webhook runs are processed one at a time, in order of arrival."""

    def blueprint(self) -> dict:
        bp = super().blueprint()
        bp["metadata"]["scenario"]["sequential"] = True
        return bp


def rule(js: str, sources: dict, **kw):
    """n8n_rule, plus the webhook's fields: a Make mapping cannot pass the whole webhook bundle."""
    code, inputs = n8n_rule(js, sources, **kw)
    inputs.update({f"ev_{f}": "{{1." + f + "}}" for f in FIELDS})
    return code, inputs


def build_scenario() -> Scenario:
    s = SequentialScenario(R, "R14.2 Create tasks with owners and due dates after verification", "webhook", test_key="r14-2-list-verified")
    s.flow.append(s.webhook(T))  # your action list calls this when a list changes to "verified": {series_id, occurrence_id, verified_by}
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    reads = [("Read the register", cfg("register_url") + "/series", {"_wrap": "1", "id": "{{1.series_id}}"}),
             ("Read the verified list", cfg("actions_url") + "/items", {"_wrap": "1", "occurrence_id": "{{1.occurrence_id}}"}),
             ("Read staff accounts", cfg("directory_url") + "/staff", {"_wrap": "1"})]
    for i, (name, url, q) in enumerate(reads):
        m = s.http(name, "GET", url, query=q)
        if i == 0:
            m["filter"] = s.continue_unless_stopped()
        s.flow.append(m)
    code, inputs = rule(N8N.RULES_JS, {"Config": "{{" + f"{c}.result" + "}}", **{n: data(n) for n, *_ in reads}},
                        many=True, prelude=WEBHOOK, bodies=BODIES)
    s.flow.append(s.code(RULES, code, inputs))  # rules decide; there is no AI step in R14.2
    ru = s.ref(RULES)
    items = "{{" + f"{ru}.result.items" + "}}"

    each = s.iterator("Each item", items)
    it = s.ref("Each item")
    out = lambda f: "{{" + f"{it}.{f}" + "}}"  # noqa: E731
    msg = cfg("messaging_url") + "/messages"
    item_url = cfg("actions_url") + "/items/" + out("item_q")

    def write_failed(step: str) -> list[dict]:
        # Writes are never retried: the exception row, then this item stops.
        return [s.exception(f"{step}: exception queue", out("write_failed")), s.ignore()]

    def write(name: str, method: str, url: str, body: str) -> dict:
        return s.http(name, method, url, body=body, parse=False, onerror=write_failed(name))

    def task_error(tag: str) -> list[dict]:
        # Step 9: a task-system error after the retry goes to the chair; steps 5 and 6 make a rerun safe.
        return [s.exception(f"Step 9: Exception queue: task system error ({tag})", out("task_error")),
                write(f"Step 9: Tell the chair ({tag})", "POST", msg, out("task_error_message")),
                s.ignore()]

    def with_task_id(body: str, src: str) -> str:
        return "{{replace(" + f"{it}.{body}" + '; "' + TASK_ID + '"; ' + src + ")}}"

    def created(tag: str, attempt: str) -> list[dict]:
        task_id = f"{s.ref(attempt)}.data.id"
        return [write(f"Step 8: Write task ID back ({tag})", "PATCH", item_url, with_task_id("created_body", task_id)),
                s.decision_log(f"Decision log: task created ({tag})", with_task_id("log_created", task_id))]

    def steps_6_to_7(tag: str) -> list[dict]:
        """Step 6 searches for the item ID; step 7 creates the task, retried once (step 9)."""
        search = f"Step 6: Search tasks for the item ID ({tag})"
        flow = [s.http(search, "GET", cfg("tasks_url") + "/tasks", query={"_wrap": "1", "item_id": out("item_id")},
                       onerror=task_error(f"search, {tag}"))]
        found_id = f"{s.ref(search)}.data.items[1].id"
        first, second = f"Step 7: Create the task ({tag})", f"Step 7: Create the task, second try ({tag})"
        try1 = s.http(first, "POST", cfg("tasks_url") + "/tasks", body=out("task_body"))
        try1["mapper"]["stopOnHttpError"] = False  # its status decides: created, or the one retry
        status = "{{" + f"{s.ref(first)}.statusCode" + "}}"
        try2 = s.http(second, "POST", cfg("tasks_url") + "/tasks", body=out("task_body"), onerror=task_error(f"create, {tag}"))
        count = "{{length(" + f"{s.ref(search)}.data.items" + ")}}"
        flow.append(s.router(f"Task found? ({tag})", [
            # A task already carries this item ID: write its ID back and create nothing.
            (s.when("task found", count, "0", "number:greater"),
             [write(f"Step 6: Write the found task ID back ({tag})", "PATCH", item_url, with_task_id("found_body", found_id)),
              s.decision_log(f"Decision log: task found ({tag})", with_task_id("log_found", found_id))]),
            (s.when("no task", count, "0", "number:equal"), [try1, s.router(f"Created? ({tag})", [
                (s.when("created", status, "300", "number:less"), created(tag, first)),
                (s.when("task system error", status, "300", "number:greaterorequal"), [try2] + created(f"{tag}, second try", second)),
            ])]),
        ]))
        return flow

    route = lambda r: s.when(f"route is {r}", out("route"), r)  # noqa: E731
    returned = s.aggregator("Step 4: Returned items", "Each item", {f: out(f) for f in ("action", "reasons", "chair", "series")})
    ag = s.ref("Step 4: Returned items")
    code, inputs = n8n_rule(MATCHING + N8N.RETURNS_JS.strip() + "\n}", {RULES: "{{" + f"{ag}.array" + "}}"}, items=(RULES,),
                            bodies={"message": "JSON.stringify({ to: [out.chair], subject: out.count + ' action item(s) returned: ' + out.series, "
                                               "text: 'Fix and verify again:\\n' + out.text })"})
    chair_msg = s.code("Step 4: One message to the chair", code, inputs)
    chair_msg["filter"] = s.when("items returned", "{{length(" + f"{ag}.array" + ")}}", "0", "number:greater")
    per_item = s.router("Route", [
        (route("refuse"), [s.exception("Step 2: Exception queue: verifier not registered", out("refuse_exception")),
                           write("Step 2: Alert the register owner", "POST", msg, out("refuse_message"))]),
        # Step 4: Table 14.1; a failure returns the item to the chair with the reason, in one message.
        (route("return"), [write("Step 4: Return the item to the chair", "PATCH", item_url, out("return_body")),
                           s.decision_log("Decision log: returned", out("log_returned")),
                           returned, chair_msg,
                           s.http("Step 4: Tell the chair", "POST", msg, body="{{" + f"{s.ref('Step 4: One message to the chair')}.result.message" + "}}",
                                  parse=False, onerror=write_failed("Step 4: Tell the chair"))]),
        # Step 3: an owner outside the company goes into the minutes; the chair gets the follow-up task.
        (route("outside"), [write("Step 3: Write to the minutes", "PUT", cfg("minutes_url") + "/entries/" + out("item_q"), out("minutes_body"))]
         + steps_6_to_7("outside owner")),
        (route("task"), steps_6_to_7("staff owner")),
    ])

    # Step 8: one message to each owner, listing all of their new tasks.
    again = s.http("Step 8: Read the list again", "GET", cfg("actions_url") + "/items", query={"_wrap": "1", "occurrence_id": "{{1.occurrence_id}}"})
    again["filter"] = {"name": "the list was verified by its chair or backup", "conditions": [[
        {"a": "{{length(" + f"{ru}.result.items" + ")}}", "b": "0", "o": "number:greater"},
        {"a": "{{" + f"{ru}.result.items[1].route" + "}}", "b": "refuse", "o": "text:notequal"}]]}
    # $input is the created tasks, as in n8n, where this step follows step 8's write-back.
    js = MATCHING + "const $input = { all: () => $('Step 7: Create the task').all() };\n" + N8N.OWNERS_JS.strip() + "\n}"
    code, inputs = n8n_rule(js, {RULES: items, "Step 8: Read the list again": data("Step 8: Read the list again")},
                            items=(RULES,), input_node="Step 8: Read the list again", many=True, prelude=CREATED, bodies={
        "message": "JSON.stringify({ to: [out.to], subject: out.count + ' new task(s) from ' + out.series, text: out.text })"})
    owners = s.code("Step 8: One message per owner", code, inputs)
    each_owner = s.iterator("Each owner", "{{" + f"{s.ref('Step 8: One message per owner')}.result.items" + "}}")
    tell = s.http("Step 8: Tell each owner", "POST", msg, body="{{" + f"{s.ref('Each owner')}.message" + "}}", parse=False,
                  onerror=[s.exception("Exception queue: write failed (owner message)",
                                       "{{" + f"{ru}.result.items[1].write_failed" + "}}"), s.ignore()])
    # The router's routes run in order: every item is done before step 8 reads the list again.
    s.flow.append(s.router("Items, then owners", [(None, [each, per_item]), (None, [again, owners, each_owner, tell])]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R14.2/make/, scenario)."""
    return [("blueprint.json", build_scenario())]
