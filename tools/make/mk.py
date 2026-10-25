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
Module versions match what Make ran on 2026-10-25 (http:MakeRequest v4,
code:ExecuteCode v1, builtin:BasicRouter v1, gateway:CustomWebHook v1).
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

HOOK_PLACEHOLDER = None  # the reader creates their own webhook on import


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
              "return " + json.dumps(values, indent=2) + ";")
        return self.code("Config", js, x=x, y=y)

    def http(self, name: str, method: str, url: str, *, body: str | None = None, parse: bool = True,
             onerror: list[dict] | None = None, query: dict | None = None, x=0, y=0) -> dict:
        """A system call. A GET with no error route of its own is a read and gets the Retry handler."""
        if onerror is None and method.upper() == "GET":
            onerror = [self.retry()]
        mapper = {"url": url, "method": method.lower(), "timeout": "40", "parseResponse": parse,
                  "stopOnHttpError": True, "allowRedirects": True, "shareCookies": False,
                  "requestCompressedContent": True}
        if query:
            mapper["queryParameters"] = [{"name": k, "value": v} for k, v in query.items()]
        if body is not None:
            mapper.update(contentType="json", inputMethod="jsonString", jsonStringBodyContent=body)
        m = {"id": self._id(name), "module": "http:MakeRequest", "version": 4, "parameters": {},
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

    def reserve_key(self, name: str, key_expr: str, x=0, y=0) -> dict:
        """POST the key to reserve_key; the step's data is true for a new key, false for a copy."""
        body = '{"p_recipe": "' + self.recipe + '", "p_key": "' + key_expr + '"}'
        return self.http(name, "POST", self.table("/rpc/reserve_key"), body=body, x=x, y=y)

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

    def continue_unless_stopped(self) -> dict:
        s = str(self.ref("Stop flag: read"))
        return self.when("stop flag not set", "{{" + s + ".data.stopped}}", "true", "text:notequal")

    # ---- output ----------------------------------------------------------------
    @staticmethod
    def _layout(flow: list[dict], x: int, y: int) -> int:
        """Place modules left to right, router routes below each other and error routes under
        their module, so the scenario opens tidy in Make's editor. Returns the next free row."""
        bottom = y
        for m in flow:
            m.setdefault("metadata", {}).setdefault("designer", {}).update(x=x, y=y)
            if m.get("onerror"):
                bottom = max(bottom, Scenario._layout(m["onerror"], x, y + 300))
            if m.get("routes"):
                row = y
                for r in m["routes"]:
                    row = Scenario._layout(r["flow"], x + 300, row) + 300
                bottom = max(bottom, row - 300)
            x += 300
        return bottom

    def blueprint(self) -> dict:
        self._layout(self.flow, 0, 0)
        return {"name": self.name, "flow": self.flow,
                "metadata": {"instant": self.trigger == "webhook", "version": 1, "designer": {"orphans": []},
                             "scenario": {"dlq": True, "slots": None, "dataloss": False, "maxErrors": 3,
                                          "autoCommit": True, "roundtrips": 1, "sequential": False,
                                          "confidential": False, "freshVariables": False, "autoCommitTriggerLast": True}}}


def n8n_rule(js: str, sources: dict[str, str], *, bodies: dict[str, str] | None = None, many: bool = False) -> tuple[str, dict[str, str]]:
    """Wrap an n8n Code-node rule (runOnceForAllItems, returning [{json: ...}]) for a Make Code step.
    sources maps each n8n node name the rule reads with $('...') to the Make expression for that
    node's data (a whole collection, such as {{4.data}}). bodies maps an output name to a JavaScript
    expression over `out` (the rule's result) and `$`, evaluated after the rule: the request bodies
    later steps map whole. many: the rule returns several items; the step returns {items: [...]}
    for an iterator, and bodies are computed per item into each element. Returns (code, inputs)."""
    inputs, table = {}, {}
    for i, (node, expr) in enumerate(sources.items()):
        key = f"in{i}_" + re.sub(r"[^A-Za-z0-9_]", "", node)[:24]
        inputs[key] = expr
        table[node] = key
    body_js = ", ".join(f"{json.dumps(k)}: {v}" for k, v in (bodies or {}).items())
    code = (
        "// Adapter: the rule below is the same JavaScript as the recipe's n8n build.\n"
        "// $('Step name') answers from this step's inputs, which Make passes as JSON text.\n"
        f"const SOURCES = {json.dumps(table)};\n"
        "const DATA = {};\n"
        "for (const [node, key] of Object.entries(SOURCES)) {\n"
        "  const raw = input[key];\n"
        "  try { DATA[node] = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch (e) { DATA[node] = raw; }\n"
        "}\n"
        "const $ = (node) => ({ first: () => ({ json: DATA[node] }), all: () => [{ json: DATA[node] }], item: { json: DATA[node] } });\n"
        "const __rule = () => {\n" + js.strip() + "\n};\n"
        f"const BODIES = (out) => ({{{body_js}}});\n"
        + ("return { items: __rule().map(i => Object.assign({}, i.json, BODIES(i.json))) };\n" if many else
           "const out = (__rule()[0] || { json: {} }).json;\nreturn Object.assign({}, out, BODIES(out));\n")
    )
    return code, inputs


def n8n_build(rid: str):
    """The recipe's n8n build module (tools/builds/rNN_M.py), for its rule JavaScript."""
    path = Path(__file__).resolve().parents[1] / "builds" / f"r{rid[1:].replace('.', '_')}.py"
    spec = importlib.util.spec_from_file_location(f"n8n_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
