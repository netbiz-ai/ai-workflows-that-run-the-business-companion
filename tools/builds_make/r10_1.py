"""R10.1 Turn a sale into a complete work order, with restricted fields protected, as Make scenarios.

Source: book Chapter 10, recipe R10.1, build steps 1 to 10 and Table 10.1
(recipes/R10.1/build-spec.md); AI step: recipes/R10.1/prompts/extract-notes.md.
The rules are the n8n build's own JavaScript (tools/builds/r10_1.py), run through n8n_rule;
step 4's masking rule (MASK_JS) is unchanged, and the AI reads only the masked notes and the
mask token, as in n8n.
Three scenarios, because a Make scenario has one trigger: a sale with delivery (webhook), the
salesperson clearing a task (webhook, which updates the work order from step 3 with no key
check, as n8n's "cleared" output does) and step 9's morning check (schedule, every day at 08:00).
The rules use plain Date in UTC, which Make's Code app has, so no shim is needed.

Where the Make build differs from the n8n canvas, and why:
- n8n's Config node passes the webhook body on, so the rules read $('Config').first().json.body.
  A Make webhook's output cannot be mapped whole, so each field is its own input and the
  adapter adds that body to Config before the rule runs.
- n8n reads the logged visit only for a copy, then joins the new-key and changed-order paths at
  step 3. Make's routes never meet again, so the logged visit is read for every sale (one table
  read) and step 3's filter lets a new key, or a done key whose sale changed since, through.
- Steps 3 and 4's two Code nodes (keep only the Table 10.1 fields, mask codes in the notes) run
  in one Code step, keep first, because each Code step costs credits; masking still comes before
  any AI step or log.
- The sales system is chosen from the event's source with Make's switch() over the three
  sales_url_ fields, where n8n indexes Config by name.
- The scenario takes sales one at a time (sequential processing), so a changed order sent
  seconds after the first sees the first run's key marked done, as in n8n.
- Branches never meet again, so each route repeats the closing steps (mark the key done,
  decision log); "Outside every zone?" is a router whose first route adds the exception row,
  and whose second route then closes the run.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R10.1"
N8N = n8n_build(R)
T, CLEARED, M, KEEP, MASK, CHECK, KEY = N8N.T, N8N.CLEARED, N8N.M, N8N.KEEP, N8N.MASK, N8N.CHECK, N8N.KEY
EV = N8N.EV
CFG = "$('Config').first().json"
CONFIG = {
    "sales_url_online": "https://<your online store API>",
    "sales_url_store": "https://<your register API>",
    "sales_url_trade": "https://<your CRM API>",
    "zones_url": "https://<your zone sheet API>",
    "products_url": "https://<your product list API>",
    "scheduling_url": "https://<your scheduling system API>",
    "tasks_url": "https://<your task API>",
    "masking_list": ["code", "gate", "keypad", "PIN", "key safe"],
    "address_words": ["<your floor, unit and street words, such as floor, unit, apartment, street, road>"],
    "mask_token": "<your mask token>",
    "lift_words": ["lift", "elevator"],
    "stairs_words": ["stairs", "stair", "steps", "staircase"],
    "negative_words": ["no", "not", "without", "broken", "isn't", "doesn't", "out of order", "out of service"],
    "late_task_working_days": 2,
    "near_delivery_working_days": 3,
    "ops_team": "<your operations team>",
    "systems_owner": "<your systems owner>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
SALE_FIELDS = ("source", "order_id", "visit_type", "visit_number", "updated_at")
CLEARED_FIELDS = ("source", "order_id", "visit_type", "visit_number")
KEEP_MASK = "Steps 3 and 4: Keep only the Table 10.1 fields, mask codes in the notes"


class SequentialScenario(Scenario):
    """A scenario whose webhook runs are processed one at a time, in order of arrival."""

    def blueprint(self) -> dict:
        bp = super().blueprint()
        bp["metadata"]["scenario"]["sequential"] = True
        return bp


def part(js: str) -> str:
    """One n8n Code node's JavaScript as a function of $json, for a Code step that runs several in turn."""
    return "(($json) => {\n" + js.strip() + "\n})"


def rule(js: str, sources: dict[str, str], fields: tuple[str, ...], **kw) -> tuple[str, dict[str, str]]:
    """n8n_rule, with the webhook's fields added to Config as n8n's Config node passes them on (body)."""
    body = ", ".join(f"{f}: input.t_{f}" for f in fields)
    prelude = ("// The webhook's fields, as n8n's Config node passes them on: $('Config').first().json.body.\n"
               f"DATA['Config'] = [{{ json: Object.assign({{}}, DATA['Config'][0].json, {{ body: {{ {body} }} }}) }}];")
    code, inputs = n8n_rule(js, sources, prelude=prelude, **kw)
    return code, {**{f"t_{f}": "{{1." + f + "}}" for f in fields}, **inputs}


def start(s: Scenario, trigger: str | None) -> tuple:
    if trigger:
        s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    s.flow += s.stop_flag()
    c = s.ref("Config")
    return (lambda f: "{{" + f"{c}.result.{f}" + "}}"), "{{" + f"{c}.result" + "}}"


def work_order(s: Scenario, cfg, conf: str, fields: tuple[str, ...], first_filter: dict) -> None:
    """Steps 3 to 8 and the closing steps, from reading the sale on."""
    key_path = ":".join("{{encodeURL(1." + f + ")}}" for f in CLEARED_FIELDS)  # the key, with its colons
    sales_url = ("{{switch(1.source; \"online\"; " + cfg("sales_url_online")[2:-2] + "; \"store\"; " + cfg("sales_url_store")[2:-2]
                 + "; \"trade\"; " + cfg("sales_url_trade")[2:-2] + ")}}")
    # Step 3: Table 10.1's fields only; the restricted access-code field is never requested.
    sale = s.http("Step 3: Read the sale", "GET", sales_url + "/orders/{{encodeURL(1.order_id)}}",
                  query={"fields": "customer,address,notes,product,installation,paid,trade_terms,delivery_date,salesperson,updated_at"})
    sale["filter"] = first_filter
    s.flow += [sale,
               s.http("Step 3: Read the zone sheet", "GET", cfg("zones_url") + "/zones", query={"_wrap": "1"}),
               s.http("Step 3: Read the product list", "GET", cfg("products_url") + "/products", query={"_wrap": "1"})]
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    reads = {"Config": conf, **{n: data(n) for n in ("Step 3: Read the sale", "Step 3: Read the zone sheet", "Step 3: Read the product list")}}

    # Steps 3 and 4: keep only Table 10.1's fields, then mask codes before any AI step or log.
    js = (f"const __keep = one({part(N8N.KEEP_JS)}($json))[0];\n"
          f"DATA[{json.dumps(KEEP)}] = [{{ json: __keep }}];\n"
          f"const __mask = one({part(N8N.STEP4_JS)}($json))[0];\n"
          "return [{ json: { keep: __keep, mask: __mask } }];")
    code, inputs = n8n_rule(js, reads)
    s.flow.append(s.code(KEEP_MASK, code, inputs))
    km = s.ref(KEEP_MASK)
    sources = {**reads, KEEP: "{{" + f"{km}.result.keep" + "}}", MASK: "{{" + f"{km}.result.mask" + "}}"}

    # Step 5: the AI reads the masked notes only.
    vars_js = f"{{ masked_notes: $('{MASK}').first().json.masked_notes, mask_token: $('Config').first().json.mask_token }}"
    s.flow += s.ai_step("Step 5", ROOT / "recipes/R10.1/prompts/extract-notes.md", vars_js, sources, max_tokens=700, tries=2)
    call = s.ref("Step 5: AI call")

    # Step 6: rules, never the AI, decide; an AI error leaves the note fields unfilled, so the order is held.
    code, inputs = rule(N8N.CHECK_JS, {**sources, "Step 5: AI call": "{{" + f"{call}.data" + "}}"}, fields, bodies={
        "work_order_body": "JSON.stringify(out.work_order)",
        "task_body": "JSON.stringify(out.task)",
        "key_q": f"encodeURIComponent({KEY})",
        "zone_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.order_id, reason: 'address outside every zone', "
                      f"detail: 'Work order ' + {KEY} + ' held: the address is outside every zone', owner: {CFG}.ops_team }})"),
        "done_body": f"JSON.stringify({{ status: 'done', result: String($('{KEEP}').first().json.updated_at) }})",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.order_id, decision: out.status, "
                     f"rules: Object.assign({{ key: {KEY}, work_order: {KEY}, missing: out.gaps }}, out.rules) }})"),
        "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.order_id, reason: 'write failed', "
                        f"detail: 'Work-order write failed for ' + {KEY} + '; check the scheduling system, then release or close the key', "
                        f"owner: {CFG}.systems_owner }})"),
    })
    s.flow.append(s.code(CHECK, code, inputs))
    ck = lambda f: "{{" + f"{s.ref(CHECK)}.result.{f}" + "}}"  # noqa: E731
    key_q = ck("key_q")
    failed = lambda step: s.write_failed(step, key_q, ck("failed_body"))  # noqa: E731
    url = cfg("scheduling_url") + "/work_orders/" + key_path

    def close(tag: str) -> list[dict]:
        return [s.finish_key(f"Mark key done ({tag})", key_q, ck("done_body")),
                s.decision_log(f"Decision log ({tag})", ck("log_body"))]

    # Steps 7 and 8: create or update the work order, with the masked notes and the key; writes never retry.
    ready = [s.http("Step 7: Work order: ready to schedule", "PUT", url, body=ck("work_order_body"), parse=False,
                    onerror=failed("Step 7: Work order: ready to schedule"))] + close("ready to schedule")
    held = [s.http("Step 8: Work order: missing details", "PUT", url, body=ck("work_order_body"), parse=False,
                   onerror=failed("Step 8: Work order: missing details")),
            # The gaps, including any code to move into the restricted field.
            s.http("Step 8: Task the salesperson", "POST", cfg("tasks_url") + "/tasks", body=ck("task_body"), parse=False,
                   onerror=failed("Step 8: Task the salesperson")),
            s.router("Outside every zone?", [
                (s.when("outside every zone", ck("out_of_zone"), "true"),
                 [s.exception("Exception queue: Tom's team calls", ck("zone_body"))]),
                (None, close("missing details")),
            ])]
    s.flow.append(s.router("Complete, no code in notes?", [
        (s.when("complete", ck("ready"), "true"), ready),
        (s.when("missing details", ck("ready"), "true", "text:notequal"), held),
    ]))


def sale_with_delivery() -> Scenario:
    s = SequentialScenario(R, "R10.1 Turn a sale into a complete work order", "webhook", test_key="r10-1-sale")
    cfg, conf = start(s, T)
    # Step 2: one key per visit (source, order, visit type and number).
    reserve = s.reserve_key("Step 2: Reserve key", "{{1.source}}:{{1.order_id}}:{{1.visit_type}}:{{1.visit_number}}")
    reserve["filter"] = s.continue_unless_stopped()
    s.flow.append(reserve)
    key_q = "%3A".join("{{encodeURL(1." + f + ")}}" for f in CLEARED_FIELDS)
    logged = s.http("Step 2: Read the logged visit", "GET", s.table(f"/key_log?recipe=eq.{R}&key=eq.") + key_q)
    s.flow.append(logged)
    lg = s.ref("Step 2: Read the logged visit")
    # A new key goes on; a copy goes on only if its visit is done and the sale changed since (n8n's "Changed since logged?").
    new_or_changed = {"name": "new key, or logged and changed since", "conditions": [
        [{"a": "{{" + f"{s.ref('Step 2: Reserve key')}.data" + "}}", "b": "true", "o": "text:equal"}],
        [{"a": "{{" + f"{lg}.data[1].status" + "}}", "b": "done", "o": "text:equal"},
         {"a": "{{" + f"{lg}.data[1].result" + "}}", "b": "{{1.updated_at}}", "o": "text:notequal"}],
    ]}
    work_order(s, cfg, conf, SALE_FIELDS, new_or_changed)
    return s


def task_cleared() -> Scenario:
    s = Scenario(R, "R10.1 Turn a sale into a complete work order: task cleared", "webhook", test_key="r10-1-task-cleared")
    cfg, conf = start(s, CLEARED)
    work_order(s, cfg, conf, CLEARED_FIELDS, s.continue_unless_stopped())
    return s


def each_morning() -> Scenario:
    s = Scenario(R, "R10.1 Turn a sale into a complete work order: late tasks", "schedule", test_key=M, schedule="every day at 08:00")
    cfg, conf = start(s, None)
    read = s.http("Step 9: Read open tasks", "GET", cfg("tasks_url") + "/tasks", query={"_wrap": "1", "status": "open"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    late = "Step 9: Rule: open two working days, or delivery inside three?"
    code, inputs = n8n_rule(N8N.LATE_JS, {"Config": conf, "Step 9: Read open tasks": "{{" + f"{read['id']}.data" + "}}"}, many=True, bodies={
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: 'late:' + out.task }})",
        "exception_body": f"JSON.stringify({{ recipe: '{R}', item: out.work_order, reason: out.reason, detail: out.detail, owner: {CFG}.ops_team }})",
    })
    s.flow.append(s.code(late, code, inputs))
    s.flow.append(s.iterator("Each late task", "{{" + f"{s.ref(late)}.result.items" + "}}"))
    it = lambda f: "{{" + f"{s.ref('Each late task')}.{f}" + "}}"  # noqa: E731
    s.flow.append(s.rpc("Step 9: Reserve key", "reserve_key", it("reserve_body")))
    tom = s.exception("Exception queue: Tom's team takes the task", it("exception_body"))
    tom["filter"] = s.is_new_key("Step 9: Reserve key")  # sent before: Tom's team has it already
    s.flow.append(tom)
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R10.1/make/, scenario)."""
    return [("blueprint.json", sale_with_delivery()), ("task-cleared.blueprint.json", task_cleared()),
            ("late-tasks.blueprint.json", each_morning())]
