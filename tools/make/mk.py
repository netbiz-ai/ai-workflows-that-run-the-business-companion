"""Build Make scenario blueprints for the companion's recipes.

Each recipe's Make build (tools/builds_make/rNN_M.py) describes its scenarios with
these helpers; tools/make/golden_make.py imports a test copy into Make, runs the
golden set and writes recipes/<ID>/make/.

How the book's patterns map onto Make (see AGENTS.md, "Make builds"):
- One trigger per scenario: a recipe whose n8n build has a webhook and a morning
  schedule becomes two scenarios (blueprint.json and <name>.blueprint.json).
- Config is a Code step whose code is the reader's settings, so lists and objects
  keep their shape; every other step reads them from {{<config>.result.<field>}}.
- Rules are Code steps running the same JavaScript as the n8n build, through a
  small adapter that answers n8n's $('Node name') calls from the step's inputs.
  A mapped collection reaches a Code input as an object, so reads pass whole.
- Make mappings cannot serialise a collection or escape text for JSON, so every
  request body that carries data is built with JSON.stringify in a Code step and
  mapped whole ({{<rules>.result.<body>}}); hand-written bodies hold only IDs.
- System reads use HTTP with the response parsed, and the Retry handler (named
  Break in blueprints): three more tries a minute apart, resuming the stored
  incomplete run at the read, so nothing before it runs twice. That needs
  "Allow storing of incomplete executions" (dlq), which every scenario turns on.
  Writes never retry; their error route marks the key failed, adds an
  exception-queue row and ends the run with the Skip handler (builtin:Ignore).
  Book Chapter 16, Table 16.2; Make renamed Break and Ignore on 2026-05-26.
- Make arrays are 1-indexed in mappings ({{3.data.items[1]}} is the first).
- Branches never merge again after a router, so the closing steps (mark the key
  done, decision log) are repeated on every route.
- The key log, decision log and exception queue are reached over a PostgREST-style
  table API ({{config}}.table_api_url): reserve_key is an RPC that refuses a
  second copy in the same step (patterns/duplicate-check/schema.sql).
- The stop flag (book Chapter 3) follows Config in every scenario.
- An AI step is two steps, as in n8n: a Code step builds the Messages API request from the
  prompt file, and an HTTP step sends it with the reader's Anthropic connection (an HTTP
  "API key" connection sending x-api-key; none is chosen in the blueprint). A failed call is
  tried once more in its error route and Make's Resume handler hands that second try's
  response back, so the rule that follows sees one reply, and a second failure reaches it as
  a non-200 status, which the rule treats as an AI error.
Module versions match what Make ran on 2026-10-25 (http:MakeRequest v4,
code:ExecuteCode v1, builtin:BasicRouter v1, gateway:CustomWebHook v1).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

HOOK_PLACEHOLDER = None  # the reader creates their own webhook on import
AI_CONNECTION_PLACEHOLDER = None  # the reader chooses their Anthropic API key connection on import


def settings_js(values: dict) -> str:
    """The settings object as JavaScript source for a Code step. Make reads any {{...}} in a Code
    step's script as its own mapping and blanks it before the code runs, so a brace followed by a
    brace (merge fields such as {{invoice}} in a template) is written as \\u007b, which JavaScript
    and JSON both read back as the same text."""
    return re.sub(r"\{(?=\{)", r"\\u007b", json.dumps(values, indent=2))


class Scenario:
    def __init__(self, recipe: str, name: str, trigger: str, *, test_key: str, schedule: str | None = None):
        """trigger: 'webhook' or 'schedule'. test_key: the webhook path or schedule node name the
        recipe's tests.json uses for this trigger. schedule: the reader-facing run time, e.g. 'daily 07:00'."""
        self.recipe, self.name, self.trigger, self.test_key, self.schedule = recipe, name, trigger, test_key, schedule
        self._next = 1
        self.flow: list[dict] = []
        self.names: dict[str, int] = {}

    # ---- ids and placement ---------------------------------------------------
    def _id(self, name: str) -> int:
        if name in self.names:
            raise ValueError(f"duplicate module name {name!r}")
        i = self._next
        self._next += 1
        self.names[name] = i
        return i

    def ref(self, name: str) -> int:
        return self.names[name]

    @staticmethod
    def _meta(name: str, x: int, y: int) -> dict:
        return {"designer": {"x": x, "y": y, "name": name}}

    # ---- modules -------------------------------------------------------------
    def webhook(self, name: str, x=0, y=0) -> dict:
        return {"id": self._id(name), "module": "gateway:CustomWebHook", "version": 1,
                "parameters": {"hook": HOOK_PLACEHOLDER, "maxResults": 1}, "mapper": {}, "metadata": self._meta(name, x, y)}

    def code(self, name: str, js: str, inputs: dict[str, str] | None = None, x=0, y=0) -> dict:
        if "{{" in js:
            raise ValueError(f"{name}: Make would read the {{{{...}}}} in this Code step's script as a mapping; "
                             "pass data as inputs, or write the text with settings_js()")
        return {"id": self._id(name), "module": "code:ExecuteCode", "version": 1, "parameters": {},
                "mapper": {"language": "javascript", "inputFormat": "editor", "dependencies": [],
                           "codeEditorJavascript": js,
                           "input": [{"name": k, "value": v} for k, v in (inputs or {}).items()]},
                "metadata": self._meta(name, x, y)}

    def config(self, values: dict, x=0, y=0) -> dict:
        values = {"stop_flag_url": f"https://<your stop list API>/stop_flags/{self.recipe}",
                  "table_api_url": "https://<your table API for the key log, decision log and exception queue>",
                  "workflow_owner": "<your workflow owner>", **values}
        when = (f"// Schedule: set this scenario to run {self.schedule}; Make keeps the schedule outside the blueprint.\n"
                if self.schedule else "")
        js = ("// Config: edit these values for your company; nothing else in the scenario hard-codes them.\n" + when +
              "return " + settings_js(values) + ";")
        return self.code("Config", js, x=x, y=y)

    def http(self, name: str, method: str, url: str, *, body: str | None = None, parse: bool = True,
             onerror: list[dict] | None = None, query: dict | None = None, headers: dict | None = None,
             parameters: dict | None = None, stop_on_error: bool = True, timeout: int = 40, x=0, y=0) -> dict:
        """A system call. A GET with no error route of its own is a read and gets the Retry handler."""
        if onerror is None and method.upper() == "GET":
            onerror = [self.retry()]
        mapper = {"url": url, "method": method.lower(), "timeout": str(timeout), "parseResponse": parse,
                  "stopOnHttpError": stop_on_error, "allowRedirects": True, "shareCookies": False,
                  "requestCompressedContent": True}
        if headers:
            mapper["headers"] = [{"name": k, "value": v} for k, v in headers.items()]
        if query:
            mapper["queryParameters"] = [{"name": k, "value": v} for k, v in query.items()]
        if body is not None:
            mapper.update(contentType="json", inputMethod="jsonString", jsonStringBodyContent=body)
        m = {"id": self._id(name), "module": "http:MakeRequest", "version": 4, "parameters": dict(parameters or {}),
             "mapper": mapper, "metadata": self._meta(name, x, y)}
        if onerror:
            m["onerror"] = onerror
        return m

    def ignore(self, x=0, y=0) -> dict:
        """Make's Skip handler: end this run quietly after the error route's own steps."""
        return {"id": self._id(f"_skip{self._next}"), "module": "builtin:Ignore", "version": 1,
                "metadata": {"designer": {"x": x, "y": y}}}

    def retry(self, x=0, y=0) -> dict:
        """Make's Retry handler: store the run as incomplete and resume it at the failed step,
        up to 3 more times, 1 minute apart; after that it waits in Incomplete executions."""
        return {"id": self._id(f"_retry{self._next}"), "module": "builtin:Break", "version": 1, "parameters": {},
                "mapper": {"count": "3", "retry": True, "interval": "1"}, "metadata": {"designer": {"x": x, "y": y}}}

    def router(self, name: str, routes: list[tuple[dict | None, list[dict]]], x=0, y=0) -> dict:
        """routes: (filter or None, modules). A filter is made with when()."""
        rid = self._id(name)
        out = []
        for flt, flow in routes:
            flow = [dict(m) for m in flow]
            if flt and flow:
                flow[0]["filter"] = flt
            out.append({"flow": flow})
        return {"id": rid, "module": "builtin:BasicRouter", "version": 1, "mapper": None,
                "routes": out, "metadata": self._meta(name, x, y)}

    @staticmethod
    def when(label: str, a: str, b: str, op: str = "text:equal") -> dict:
        return {"name": label, "conditions": [[{"a": a, "b": b, "o": op}]]}

    # ---- the book's shared steps over the table API --------------------------
    def table(self, path: str) -> str:
        return "{{" + str(self.ref("Config")) + ".result.table_api_url}}" + path

    def rpc(self, name: str, function: str, body_expr: str, *, onerror: list[dict] | None = None, x=0, y=0) -> dict:
        """Call one of the key-log functions in patterns/duplicate-check/schema.sql over the table API.
        The step's data is the function's result (true/false, a count, or a list of keys)."""
        return self.http(name, "POST", self.table(f"/rpc/{function}"), body=body_expr, onerror=onerror, x=x, y=y)

    def reserve_key(self, name: str, key_expr: str, *, reopen_done: bool = False, x=0, y=0) -> dict:
        """POST the key to reserve_key; the step's data is true for a new key, false for a copy.
        key_expr is spliced into JSON text, so it may hold only IDs; build anything else in a Code step
        and pass body_expr to rpc() instead. reopen_done: a key whose run is done may be reserved again."""
        body = ('{"p_recipe": "' + self.recipe + '", "p_key": "' + key_expr + '"'
                + (', "p_reopen_done": true' if reopen_done else "") + "}")
        return self.rpc(name, "reserve_key", body, x=x, y=y)

    def release_key(self, name: str, body_expr: str, x=0, y=0) -> dict:
        """Release a key so the item runs again; body_expr maps a Code-built {"p_recipe", "p_key"} body."""
        return self.rpc(name, "release_key", body_expr, x=x, y=y)

    def is_new_key(self, reserve_name: str) -> dict:
        return self.when("new key (not a copy)", "{{" + str(self.ref(reserve_name)) + ".data}}", "true")

    def finish_key(self, name: str, key_q: str, body_expr: str, x=0, y=0, onerror=None) -> dict:
        """key_q: the key, already URL-encoded (a Code step's encodeURIComponent), as a Make expression."""
        url = self.table(f"/key_log?recipe=eq.{self.recipe}&key=eq.") + key_q
        return self.http(name, "PATCH", url, body=body_expr, parse=False, x=x, y=y, onerror=onerror)

    def decision_log(self, name: str, body_expr: str, x=0, y=0) -> dict:
        return self.http(name, "POST", self.table("/decision_log"), body=body_expr, parse=False, x=x, y=y)

    def exception(self, name: str, body_expr: str, x=0, y=0) -> dict:
        return self.http(name, "POST", self.table("/exception_queue"), body=body_expr, parse=False, x=x, y=y)

    def write_failed(self, prefix: str, key_q: str, exc_body: str, x=0, y=0) -> list[dict]:
        """The error route of a write: mark the key failed, add the exception row (exc_body, built in
        a Code step), end the run. A key-log or exception write that itself fails ends the run in error."""
        fail = '{"status": "failed", "result": "write failed"}'
        return [self.finish_key(f"{prefix}: mark key failed", key_q, fail, x=x, y=y),
                self.exception(f"{prefix}: exception queue", exc_body, x=x + 300, y=y),
                self.ignore(x=x + 600, y=y)]

    def stop_flag(self, x=0, y=0) -> list[dict]:
        """Read the stop list; a set flag ends the run quietly, an unreadable list stops it with an exception row."""
        c = str(self.ref("Config"))
        read = self.http("Stop flag: read", "GET", "{{" + c + ".result.stop_flag_url}}", x=x, y=y,
                         onerror=[self.exception("Stop flag: list unreadable",
                                                 '{"recipe": "' + self.recipe + '", "item": "run {{var.scenario.executionId}}", '
                                                 '"reason": "stop list unreadable", "detail": "The stop list could not be read, so the run stopped", '
                                                 '"owner": "{{' + c + '.result.workflow_owner}}"}', x=x, y=y + 300),
                                  self.ignore(x=x + 300, y=y + 300)])
        return [read]

    def iterator(self, name: str, array_expr: str, x=0, y=0) -> dict:
        """One bundle per element; nothing after it runs when the array is empty."""
        return {"id": self._id(name), "module": "builtin:BasicFeeder", "version": 1, "parameters": {},
                "mapper": {"array": array_expr}, "metadata": self._meta(name, x, y)}

    def ai_step(self, step: str, prompt_path, vars_js: str, sources: dict[str, str], *, max_tokens: int = 1024,
                tries: int = 2) -> list[dict]:
        """The book's bounded AI step: [build the request (Code), call the Messages API (HTTP)].
        vars_js is the n8n build's JavaScript object literal filling the prompt's {{placeholders}};
        sources are the steps it reads, as for n8n_rule. The call's output is {statusCode, data}:
        pass {{<call>.data}} to the rule as the AI call's reply and {{<call>.statusCode}} as ai_status."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
        from wf import read_prompt  # the n8n build's prompt reader: same text, same schema line
        system, template = read_prompt(prompt_path)
        max_tokens = max(max_tokens, 4096)  # Claude Haiku 5.5 thinks first, and thinking counts against the cap
        js = (
            "// The prompt text below is copied from the recipe's prompts/ file.\n"
            f"const SYSTEM = {_js_text(system)};\n"
            f"const TEMPLATE = {_js_text(template)};\n"
            f"const vars = {vars_js};\n"
            "const cfg = $('Config').first().json;\n"
            "const fill = t => t.replace(/\\{\\{(\\w+)\\}\\}/g, (m, k) => (k in vars ? String(vars[k]) : m));\n"
            "// One pass, so a filled-in value that looks like a placeholder is sent as written.\n"
            "const user = TEMPLATE.replace(/\\{\\{(\\w+)\\}\\}/g, (m, k) => (k in vars ? String(vars[k]) : ''));\n"
            f"const request = {{ model: cfg.ai_model, max_tokens: {max_tokens}, system: fill(SYSTEM),\n"
            "  messages: [{ role: 'user', content: user }] };\n"
            "if (cfg.ai_inference_geo) request.inference_geo = cfg.ai_inference_geo;\n"
            "return [{ json: { request } }];\n"
        )
        code, inputs = n8n_rule(js, sources, bodies={"request_body": "JSON.stringify(out.request)"})
        build = self.code(f"{step}: Build the AI request", code, inputs)
        b, c = self.ref(f"{step}: Build the AI request"), self.ref("Config")

        def call(name: str, onerror=None, stop=True) -> dict:
            return self.http(name, "POST", "{{" + f"{c}.result.ai_url" + "}}", body="{{" + f"{b}.result.request_body" + "}}",
                             headers={"anthropic-version": "2023-06-01"}, timeout=60, stop_on_error=stop, onerror=onerror,
                             parameters={"authenticationType": "apiKeyConnection", "apiKeyAccount": AI_CONNECTION_PLACEHOLDER,
                                         "tlsType": ""})
        if tries < 2:
            return [build, call(f"{step}: AI call", stop=False)]
        if tries > 2:
            return [build, self.with_tries(call(f"{step}: AI call", stop=False), tries)]
        second = call(f"{step}: AI call, second try", stop=False)
        resume = {"id": self._id(f"_resume{self._next}"), "module": "builtin:Resume", "version": 1, "parameters": {},
                  "mapper": {k: "{{" + f"{second['id']}.{k}" + "}}" for k in ("statusCode", "data", "headers")},
                  "metadata": {"designer": {}}}
        return [build, call(f"{step}: AI call", onerror=[second, resume])]

    def repeater(self, name: str, repeats: str) -> dict:
        """One bundle per pass, i = 1 to repeats; each runs the steps after it before the next starts.
        Make cannot loop back, so a loop is a Repeater with a variable that later passes check."""
        return {"id": self._id(name), "module": "builtin:BasicRepeater", "version": 1, "parameters": {},
                "mapper": {"start": "1", "repeats": repeats, "step": "1"}, "metadata": self._meta(name, 0, 0)}

    def set_var(self, name: str, var: str, value: str) -> dict:
        """Set a variable for the rest of this run (Make's "Set variable", scope: one cycle)."""
        return {"id": self._id(name), "module": "util:SetVariable2", "version": 1, "parameters": {},
                "mapper": {"name": var, "scope": "roundtrip", "value": value}, "metadata": self._meta(name, 0, 0)}

    def get_var(self, name: str, var: str) -> dict:
        return {"id": self._id(name), "module": "util:GetVariable2", "version": 1, "parameters": {},
                "mapper": {"name": var}, "metadata": self._meta(name, 0, 0)}

    def sleep(self, name: str, seconds: str) -> dict:
        """Wait in the run (Make's Sleep, at most 300 seconds)."""
        return {"id": self._id(name), "module": "util:FunctionSleep", "version": 1, "parameters": {},
                "mapper": {"duration": seconds}, "metadata": self._meta(name, 0, 0)}

    def with_tries(self, m: dict, n: int, onerror: list[dict] | None = None) -> dict:
        """Make an HTTP step try up to n times (n <= 4): each failed try hands over to the next in
        its error route, and Make's Resume handler passes that try's response on as the step's own
        output, so the step after it sees the last answer (a non-2xx status if every try failed).
        The step's own error route, if any, is replaced; onerror, if given, becomes the last try's
        error route instead (that try then stops on an HTTP error). Returns m."""
        ordinal = {2: "second", 3: "third", 4: "fourth"}
        calls = [m]
        for k in range(2, n + 1):
            name = f"{m['metadata']['designer']['name']}, {ordinal[k]} try"
            c = copy.deepcopy(calls[-1])
            c.pop("onerror", None)
            c.pop("filter", None)
            c["id"] = self._id(name)
            c["metadata"]["designer"]["name"] = name
            calls.append(c)
        for i, c in enumerate(calls):
            c["mapper"]["stopOnHttpError"] = i < len(calls) - 1 or onerror is not None
        if onerror is not None:
            calls[-1]["onerror"] = onerror
        for i in range(len(calls) - 2, -1, -1):
            nxt = calls[i + 1]
            resume = {"id": self._id(f"_resume{self._next}"), "module": "builtin:Resume", "version": 1, "parameters": {},
                      "mapper": {k: "{{" + f"{nxt['id']}.{k}" + "}}" for k in ("statusCode", "data", "headers")},
                      "metadata": {"designer": {}}}
            calls[i]["onerror"] = [nxt, resume]
        return m

    def aggregator(self, name: str, iterator_name: str, fields: dict[str, str], x=0, y=0) -> dict:
        """Gather the bundles an iterator started back into one: {{<this>.array}} is a list of
        {field: value} objects, one per bundle, which a Code step receives as a real array."""
        return {"id": self._id(name), "module": "builtin:BasicAggregator", "version": 1,
                "parameters": {"feeder": self.ref(iterator_name)}, "mapper": dict(fields), "metadata": self._meta(name, x, y)}

    def continue_unless_stopped(self) -> dict:
        s = str(self.ref("Stop flag: read"))
        return self.when("stop flag not set", "{{" + s + ".data.stopped}}", "true", "text:notequal")

    # ---- output ----------------------------------------------------------------
    @staticmethod
    def _span(flow: list[dict]) -> int:
        """How many columns a route takes: its modules, plus the widest branch after a router."""
        return sum(1 + (max((Scenario._span(r["flow"]) for r in m["routes"]), default=0) if m.get("routes") else 0)
                   for m in flow)

    @staticmethod
    def _layout(flow: list[dict]) -> None:
        """Place modules left to right; each error route and router branch goes on the first row
        below where all its columns are free, so no two modules share a spot in Make's editor."""
        taken: set[tuple[int, int]] = set()

        def free_row(x: int, row: int, flow: list[dict]) -> int:
            cols = range(x, x + 300 * max(Scenario._span(flow), 1), 300)
            while any((c, row) in taken for c in cols):
                row += 300
            return row

        def place(flow: list[dict], x: int, y: int) -> None:
            for m in flow:
                m.setdefault("metadata", {}).setdefault("designer", {}).update(x=x, y=y)
                taken.add((x, y))
                if m.get("onerror"):
                    place(m["onerror"], x, free_row(x, y + 300, m["onerror"]))
                row = y
                for r in m.get("routes", []):
                    row = free_row(x + 300, row, r["flow"])
                    place(r["flow"], x + 300, row)
                    row += 300
                x += 300

        place(flow, 0, 0)

    def blueprint(self) -> dict:
        self._layout(self.flow)
        return {"name": self.name, "flow": self.flow,
                "metadata": {"instant": self.trigger == "webhook", "version": 1, "designer": {"orphans": []},
                             "scenario": {"dlq": True, "slots": None, "dataloss": False, "maxErrors": 3,
                                          "autoCommit": True, "roundtrips": 1, "sequential": False,
                                          "confidential": False, "freshVariables": False, "autoCommitTriggerLast": True}}}


def _js_text(text: str) -> str:
    """A JavaScript string literal for text that may hold {{placeholders}} (see settings_js)."""
    return re.sub(r"\{(?=\{)", r"\\u007b", json.dumps(text))


def n8n_rule(js: str, sources: dict[str, str], *, bodies: dict[str, str] | None = None, many: bool = False,
             items: tuple[str, ...] = (), input_node: str | None = None, executed: tuple[str, ...] = (),
             per_item: bool = False, prelude: str = "", ai_status: str | None = None,
             on_ai_error: str | None = None) -> tuple[str, dict[str, str]]:
    """Wrap an n8n Code-node rule for a Make Code step, keeping the rule's JavaScript unchanged.

    sources: each n8n node name the rule reads with $('...'), mapped to the Make expression for that
      node's data, such as {{4.data}}. A mapped collection reaches the Code step as an object.
    items: source nodes whose expression is a list of items (an aggregator's {{N.array}} of
      {json: ...} objects, or a rule's {{N.result.items}}), so .all() gives every item.
    input_node: the node $input and $json read (default: the last source).
    executed: node names that ran without data the rule needs, such as the scenario's own
      trigger, so $('...').isExecuted is true; any other node not in sources is false.
    per_item: the n8n node ran once for each item (runOnceForEachItem): the rule runs once per
      input item with $json set to it, and the step returns {items: [...]}.
    many: the rule (run once) returns several items; the step returns {items: [...]}.
    bodies: an output name -> a JavaScript expression over `out` (the rule's result for one item)
      and `$`, evaluated after the rule: the request bodies later steps map whole. With many or
      per_item they are computed into each element.
    prelude: JavaScript run before the rule, for what Make's Code app lacks (it has no Luxon, so a
      rule using $now needs a small shim here).
    ai_status, on_ai_error: for the rule after an AI step, the call's {{N.statusCode}} and the n8n
      build's AI-error node code; when the call did not return 200, that code runs instead of the
      rule, with $json.error.message saying why (n8n sends a failed call to that node).
    $execution.id is the Make run's ID. Returns (code, inputs)."""
    inputs, table = {}, {}
    for i, (node, expr) in enumerate(sources.items()):
        key = f"in{i}_" + re.sub(r"[^A-Za-z0-9_]", "", node)[:24]
        inputs[key] = expr
        table[node] = key
    inputs["run_id"] = "{{var.scenario.executionId}}"
    if ai_status:
        inputs["ai_status"] = ai_status
    if bool(ai_status) != bool(on_ai_error):
        raise ValueError("ai_status and on_ai_error go together")
    unknown = set(items) - set(sources) | ({input_node} - set(sources) if input_node else set())
    if unknown:
        raise ValueError(f"not in sources: {sorted(unknown)}")
    first_input = input_node or (list(sources)[-1] if sources else None)
    body_js = ", ".join(f"{json.dumps(k)}: {v}" for k, v in (bodies or {}).items())
    multi = many or per_item
    code = (
        "// Adapter: the rule below is the same JavaScript as the recipe's n8n build.\n"
        "// $('Step name') answers from this step's inputs: each is that step's output in this scenario.\n"
        f"const SOURCES = {json.dumps(table)};\n"
        f"const LISTS = {json.dumps(sorted(items))};\n"
        f"const EXECUTED = {json.dumps(sorted(executed))};\n"
        "const DATA = {};\n"
        "for (const [node, key] of Object.entries(SOURCES)) {\n"
        "  const raw = input[key];\n"
        "  let v = raw;\n"
        "  if (typeof raw === 'string') { try { v = JSON.parse(raw); } catch (e) { v = raw; } }\n"
        "  DATA[node] = LISTS.includes(node) ? (v || []).map(i => (i && i.json !== undefined ? i : { json: i })) : [{ json: v }];\n"
        "}\n"
        "const $ = (node) => {\n"
        "  const ran = node in DATA || EXECUTED.includes(node);\n"
        "  const list = () => { if (!(node in DATA)) throw new Error(`step ${node} has no data in this scenario`); return DATA[node]; };\n"
        "  return { isExecuted: ran, first: () => list()[0], last: () => list()[list().length - 1], all: () => list(),\n"
        "           get item() { return list()[0]; } };\n"
        "};\n"
        f"const INPUT = {json.dumps(first_input)};\n"
        "const $input = { all: () => $(INPUT).all(), first: () => $(INPUT).first(), last: () => $(INPUT).last(), get item() { return $(INPUT).first(); } };\n"
        "const $execution = { id: input.run_id };\n"
        + (prelude.strip() + "\n" if prelude.strip() else "")
        + "const BODIES = (out) => ({" + body_js + "});\n"
        "const one = (r) => (Array.isArray(r) ? r : [r]).filter(Boolean).map(i => (i.json !== undefined ? i.json : i));\n"
    )
    if per_item:
        code += ("const __rule = ($json, $item) => {\n" + js.strip() + "\n};\n"
                 "return { items: $input.all().flatMap(it => one(__rule(it.json, it))).map(o => Object.assign({}, o, BODIES(o))) };\n")
    else:
        guard = ("if (Number(input.ai_status) !== 200) return (($json) => {\n" + on_ai_error.strip() + "\n})"
                 "({ error: { message: 'AI call returned ' + (input.ai_status || 'no answer') } });\n") if ai_status else ""
        code += ("const $json = INPUT && INPUT in DATA ? $input.first().json : {};\n"
                 "const __rule = () => {\n" + guard + js.strip() + "\n};\n"
                 + ("return { items: one(__rule()).map(o => Object.assign({}, o, BODIES(o))) };\n" if multi else
                    "const out = one(__rule())[0] || {};\nreturn Object.assign({}, out, BODIES(out));\n"))
    return code, inputs


def n8n_build(rid: str):
    """The recipe's n8n build module (tools/builds/rNN_M.py), for its rule JavaScript."""
    path = Path(__file__).resolve().parents[1] / "builds" / f"r{rid[1:].replace('.', '_')}.py"
    spec = importlib.util.spec_from_file_location(f"n8n_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
