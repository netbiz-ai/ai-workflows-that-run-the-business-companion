"""Build n8n workflow JSON for the companion's recipes.

Each recipe's build script (tools/builds/rNN_M.py) describes its workflow with
these helpers; the result is imported into n8n, run against the golden set,
exported and cleaned into recipes/<ID>/n8n/workflow.json.

Conventions every build follows (see AGENTS.md, "Phase 2"):
- One Webhook trigger per event the book names; schedule triggers for "each
  morning" steps. Node names start with the book's step: "Step 2: Reserve key".
- One "Config" node holds every value a reader changes: system URLs, limits,
  lists, people. Nothing else hard-codes a URL or a threshold.
- System calls are HTTP Request nodes named for the system and action, with
  retries off on every write (book Chapter 2) and an error output that routes
  to the exception queue.
- Rules are Code nodes named "Rule: ...", plain JavaScript, returning the
  decision and its reason codes; the AI never decides.
- The key log, decision log and exception queue are Postgres tables
  (patterns/duplicate-check/schema.sql).

Node versions are pinned to what n8n 2.42.7 ships.
"""

from __future__ import annotations

import json
import uuid

V = {
    "webhook": 2.1,
    "set": 3.4,
    "code": 2,
    "if": 2.2,
    "switch": 3.2,
    "http": 4.2,
    "postgres": 2.6,
    "noop": 1,
    "schedule": 1.2,
}

PG_CREDENTIAL = {"postgres": {"id": "POSTGRES_CREDENTIAL_ID", "name": "Your Postgres (key log, decision log)"}}
ANTHROPIC_CREDENTIAL = {"anthropicApi": {"id": "ANTHROPIC_CREDENTIAL_ID", "name": "Your Anthropic API key"}}


def _uid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


class Workflow:
    def __init__(self, recipe: str, name: str):
        self.recipe = recipe
        self.name = name
        self.nodes: list[dict] = []
        self.connections: dict = {}
        self._col = 0

    # ---- graph -------------------------------------------------------------
    def node(self, name: str, type_: str, version, params: dict, *, pos=None, credentials=None,
             notes: str | None = None, **extra) -> str:
        if any(n["name"] == name for n in self.nodes):
            raise ValueError(f"duplicate node name {name!r}")
        if pos is None:
            pos = [self._col * 260, 0]
            self._col += 1
        n = {"parameters": params, "id": _uid(f"{self.recipe}/{name}"), "name": name,
             "type": type_, "typeVersion": version, "position": pos}
        if credentials:
            n["credentials"] = credentials
        if notes:
            n["notes"] = notes
            n["notesInFlow"] = True
        n.update(extra)
        self.nodes.append(n)
        return name

    def connect(self, src: str, dst: str, output: int = 0, input_: int = 0) -> None:
        outs = self.connections.setdefault(src, {}).setdefault("main", [])
        while len(outs) <= output:
            outs.append([])
        outs[output].append({"node": dst, "type": "main", "index": input_})

    def chain(self, *names: str) -> None:
        for a, b in zip(names, names[1:]):
            self.connect(a, b)

    def to_json(self) -> dict:
        return {"name": self.name, "nodes": self.nodes, "connections": self.connections,
                "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "all",
                             "saveManualExecutions": True, "callerPolicy": "workflowsFromSameOwner"},
                "pinData": {}}

    # ---- building blocks -----------------------------------------------------
    def webhook(self, name: str, path: str, notes: str, pos=None) -> str:
        return self.node(name, "n8n-nodes-base.webhook", V["webhook"],
                         {"httpMethod": "POST", "path": path, "responseMode": "onReceived", "options": {}},
                         pos=pos, notes=notes, webhookId=_uid(f"{self.recipe}/{path}"))

    def schedule(self, name: str, hour: int, notes: str, pos=None) -> str:
        return self.node(name, "n8n-nodes-base.scheduleTrigger", V["schedule"],
                         {"rule": {"interval": [{"triggerAtHour": hour}]}}, pos=pos, notes=notes)

    def config(self, name: str, values: dict, pos=None) -> str:
        """A Set node holding every reader-editable value. Values keep their JSON type."""
        assignments = []
        for k, v in values.items():
            t = ("number" if isinstance(v, (int, float)) and not isinstance(v, bool) else
                 "boolean" if isinstance(v, bool) else
                 "array" if isinstance(v, list) else "object" if isinstance(v, dict) else "string")
            val = json.dumps(v) if t in ("array", "object") else v
            assignments.append({"id": _uid(f"{self.recipe}/{name}/{k}"), "name": k, "value": val, "type": t})
        return self.node(name, "n8n-nodes-base.set", V["set"],
                         {"assignments": {"assignments": assignments}, "includeOtherFields": True, "options": {}},
                         pos=pos, notes="Edit these values for your company; nothing else in the workflow hard-codes them.")

    def code(self, name: str, js: str, pos=None, notes=None, mode: str = "runOnceForEachItem") -> str:
        return self.node(name, "n8n-nodes-base.code", V["code"], {"mode": mode, "jsCode": js}, pos=pos, notes=notes)

    def http(self, name: str, method: str, url: str, *, body: str | None = None, write: bool,
             pos=None, notes=None, error_output: bool = True, query: dict | None = None) -> str:
        """An HTTP call to a business system. Writes never retry (book Chapter 2); reads retry three times."""
        params: dict = {"method": method, "url": url, "options": {"response": {"response": {"neverError": False}}}}
        if query:
            params["sendQuery"] = True
            params["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query.items()]}
        if body is not None:
            params.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
        extra = {}
        if not write:
            extra.update(retryOnFail=True, maxTries=3, waitBetweenTries=2000)
        if error_output:
            extra["onError"] = "continueErrorOutput"
        return self.node(name, "n8n-nodes-base.httpRequest", V["http"], params, pos=pos, notes=notes, **extra)

    def pg(self, name: str, sql: str, *, args: list[str] | None = None, pos=None, notes=None,
           error_output: bool = False) -> str:
        """args are JavaScript expressions, one per $n placeholder, passed as an array so a
        value containing a comma stays one parameter."""
        params = {"operation": "executeQuery", "query": sql, "options": {}}
        if args:
            params["options"]["queryReplacement"] = "={{ [" + ", ".join(args) + "] }}"
        extra = {"onError": "continueErrorOutput"} if error_output else {}
        return self.node(name, "n8n-nodes-base.postgres", V["postgres"], params, pos=pos,
                         credentials=PG_CREDENTIAL, notes=notes, alwaysOutputData=True, **extra)

    def if_(self, name: str, left: str, op: str = "true", right=None, pos=None, notes=None) -> str:
        """Boolean or string test. op: 'true' | 'equals' | 'notEmpty'."""
        if op == "true":
            cond = {"leftValue": left, "rightValue": "", "operator": {"type": "boolean", "operation": "true", "singleValue": True}}
        elif op == "equals":
            cond = {"leftValue": left, "rightValue": right, "operator": {"type": "string", "operation": "equals"}}
        else:
            cond = {"leftValue": left, "rightValue": "", "operator": {"type": "string", "operation": "notEmpty", "singleValue": True}}
        cond["id"] = _uid(f"{self.recipe}/{name}/c")
        return self.node(name, "n8n-nodes-base.if", V["if"],
                         {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                                         "conditions": [cond], "combinator": "and"}, "options": {}},
                         pos=pos, notes=notes)

    def switch(self, name: str, value: str, cases: list[str], pos=None, notes=None) -> str:
        rules = []
        for c in cases:
            rules.append({"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                                         "conditions": [{"id": _uid(f"{self.recipe}/{name}/{c}"), "leftValue": value, "rightValue": c,
                                                         "operator": {"type": "string", "operation": "equals"}}],
                                         "combinator": "and"},
                          "renameOutput": True, "outputKey": c})
        return self.node(name, "n8n-nodes-base.switch", V["switch"],
                         {"rules": {"values": rules}, "options": {}}, pos=pos, notes=notes)

    def noop(self, name: str, pos=None, notes=None) -> str:
        return self.node(name, "n8n-nodes-base.noOp", V["noop"], {}, pos=pos, notes=notes)

    # ---- the book's shared steps --------------------------------------------
    # Every *_expr argument below is a JavaScript expression evaluated in n8n,
    # such as "$('Config').item.json.request_id"; literals are JSON strings.
    def reserve_key(self, name: str, key_expr: str, pos=None) -> str:
        """Reserve the duplicate key in one statement; returns is_new (book Chapter 2)."""
        sql = ("WITH reserved AS (INSERT INTO key_log (recipe, key, status) VALUES ($1, $2, 'in progress') "
               "ON CONFLICT (recipe, key) DO NOTHING RETURNING key), "
               "skipped AS (UPDATE key_log SET copies_skipped = copies_skipped + 1 "
               "WHERE recipe = $1 AND key = $2 AND NOT EXISTS (SELECT 1 FROM reserved)) "
               "SELECT (SELECT count(*) FROM reserved) = 1 AS is_new, $2::text AS key")
        return self.pg(name, sql, args=[json.dumps(self.recipe), key_expr], pos=pos,
                       notes="Key log: refuses a second copy in the same step (book Chapter 2).")

    def finish_key(self, name: str, key_expr: str, status: str, result_expr: str, pos=None) -> str:
        sql = "UPDATE key_log SET status = $3, result = $4 WHERE recipe = $1 AND key = $2 RETURNING key"
        return self.pg(name, sql, args=[json.dumps(self.recipe), key_expr, json.dumps(status), result_expr], pos=pos)

    def decision_log(self, name: str, item_expr: str, decision_expr: str, rules_expr: str, pos=None) -> str:
        sql = "INSERT INTO decision_log (recipe, item, decision, rules) VALUES ($1, $2, $3, $4::jsonb) RETURNING id"
        return self.pg(name, sql, args=[json.dumps(self.recipe), item_expr, decision_expr, rules_expr], pos=pos,
                       notes="Decision log: the item's ID, the decision and the rules; never the content (book Chapter 3).")

    def exception(self, name: str, item_expr: str, reason: str, detail_expr: str, owner_expr: str, pos=None) -> str:
        sql = "INSERT INTO exception_queue (recipe, item, reason, detail, owner) VALUES ($1, $2, $3, $4, $5) RETURNING id"
        return self.pg(name, sql, args=[json.dumps(self.recipe), item_expr, json.dumps(reason), detail_expr, owner_expr], pos=pos,
                       notes="Exception queue: a named person works through it (book Chapters 2 and 16).")


# ---- AI steps ------------------------------------------------------------------

AI_PARSE_JS = r"""
// Parse an AI reply and check it against the prompt's schema; never trust it otherwise.
function parseAi(reply, required, enums = {}) {
  const text = ((reply && reply.content) || []).filter(c => c.type === 'text').map(c => c.text).join('').trim()
    .replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
  let out;
  try { out = JSON.parse(text); } catch (e) { return { ok: false, problem: 'reply is not JSON' }; }
  if (!out || typeof out !== 'object' || Array.isArray(out)) return { ok: false, problem: 'reply is not an object' };
  for (const k of required) if (!(k in out)) return { ok: false, problem: `missing field ${k}` };
  for (const [k, allowed] of Object.entries(enums)) if (!allowed.includes(out[k])) return { ok: false, problem: `${k} not one of ${allowed.join(', ')}` };
  return { ok: true, value: out };
}
"""


def read_prompt(path) -> tuple[str, str]:
    """Return (system prompt, input template) from a recipes/<ID>/prompts/<step>.md file."""
    import re
    text = open(path).read()
    system = re.search(r"(?ms)^## System prompt\n(.*?)^## ", text).group(1).strip()
    inp = re.search(r"(?ms)^## Input\n.*?```[a-z]*\n(.*?)```", text).group(1).rstrip("\n")
    return system, inp


def ai_step(w: Workflow, step: str, prompt_path, vars_js: str, *, max_tokens: int = 1024,
            tries: int = 2, pos_build=None, pos_call=None) -> tuple[str, str]:
    """Two nodes: build the request from the prompt file (Code), then call the Anthropic
    Messages API (HTTP Request, Anthropic credential). vars_js is a JavaScript object
    literal filling the prompt's {{placeholders}}. Returns (build node, call node); the
    call node's output 0 is the reply, output 1 an AI error after the retries."""
    system, template = read_prompt(prompt_path)
    build = f"{step}: Build the AI request"
    call = f"{step}: AI call"
    js = (
        "// The prompt text below is copied from the recipe's prompts/ file.\n"
        f"const SYSTEM = {json.dumps(system)};\n"
        f"const TEMPLATE = {json.dumps(template)};\n"
        f"const vars = {vars_js};\n"
        "const cfg = $('Config').first().json;\n"
        "const user = TEMPLATE.replace(/\\{\\{(\\w+)\\}\\}/g, (_, k) => (k in vars ? String(vars[k]) : ''));\n"
        "const request = { model: cfg.ai_model, max_tokens: " + str(max_tokens) + ", temperature: 0, system: SYSTEM,\n"
        "  messages: [{ role: 'user', content: user }] };\n"
        "if (cfg.ai_inference_geo) request.inference_geo = cfg.ai_inference_geo;\n"
        "return { json: { request } };\n"
    )
    w.code(build, js, pos=pos_build, notes="Fills the prompt from the recipe's prompts/ file; the input is data, never instructions.")
    w.node(call, "n8n-nodes-base.httpRequest", V["http"], {
        "method": "POST", "url": "={{ $('Config').item.json.ai_url }}",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "anthropicApi",
        "sendHeaders": True, "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]},
        "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.request) }}",
        "options": {"timeout": 60000},
    }, pos=pos_call, credentials=ANTHROPIC_CREDENTIAL, retryOnFail=tries > 1, maxTries=max(tries, 1),
        waitBetweenTries=2000, onError="continueErrorOutput",
        notes="Claude Haiku 5.5 by default (Config); tools none; the reply is checked by the rule that follows.")
    w.connect(build, call)
    return build, call
