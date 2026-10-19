"""R13.2 Flag stale documents to their owners and pull expired ones from answers: rules only, no AI step.

Source: book Chapter 13, recipe R13.2, build steps 1 to 11 (recipes/R13.2/build-spec.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import Workflow  # noqa: E402

W = "Step 1: Each week"
V = "Step 9: Major version published"
VEV = f"$('{V}').item.json.body"
ACT = "$('Split the actions').item.json"

RULES_JS = r"""
// Steps 2, 4 to 7 and 10 of the book's R13.2, in order. One action per source and need;
// the duplicate key (step 3) is source, week and action, so one source can need two actions.
const cfg = $('Config').first().json;
const rows = $('Step 2: Read the register').first().json.items || [];
const users = Object.fromEntries(($('Read the directory').first().json.items || []).map(u => [String(u.id).toLowerCase(), u]));
const files = Object.fromEntries(($('Step 10: Read sharing').first().json.items || []).map(f => [String(f.id), f]));
const indexed = Object.fromEntries(($('Step 10: Read the index').first().json.items || []).map(s => [String(s.id), s]));

const DAY = 86400000;
const iso = d => d.toISOString().slice(0, 10);
const day = s => new Date(String(s).slice(0, 10) + 'T00:00:00Z');
const today = day(new Date().toISOString());
// ISO week, such as 2026-W43: the "week" in the duplicate key.
const t = new Date(today); t.setUTCDate(t.getUTCDate() + 3 - ((t.getUTCDay() + 6) % 7));
const w1 = new Date(Date.UTC(t.getUTCFullYear(), 0, 4));
const week = `${t.getUTCFullYear()}-W${String(1 + Math.round(((t - w1) / DAY - 3 + ((w1.getUTCDay() + 6) % 7)) / 7)).padStart(2, '0')}`;
const dueBy = new Date(today.getTime() + cfg.due_within_days * DAY);
const major = v => parseInt(String(v), 10);
const sameSet = (a, b) => { const x = [...new Set((a || []).map(String))].sort(), y = [...new Set((b || []).map(String))].sort(); return x.join('|') === y.join('|'); };

const actions = [];
let checked = 0;
for (const r of rows) {
  if (cfg.inactive_statuses.includes(r.status)) continue;  // already withdrawn or retired: the owner decides (step 8)
  checked++;
  const base = { source: String(r.id), title: r.title, owner: r.owner || null, file_id: r.file_id || null };
  const add = (action, extra) => actions.push(Object.assign({}, base, { action, key: `${r.id}:${week}:${action}` }, extra));

  // Step 4: no owner or review date means withdrawn, with the register admin alerted.
  if (!r.owner || !r.review_date) { add('withdraw_missing', { reason: !r.owner ? 'no owner' : 'no review date' }); continue; }

  const pull = r.expiry_date ? day(r.expiry_date) : new Date(day(r.review_date).getTime() + cfg.expiry_after_review_days * DAY);
  const expired = pull < today;
  // Step 5: a departed owner goes to the register admin to reassign; one on vacation, to the delegate.
  const u = users[String(r.owner).toLowerCase()];
  const departed = !u || u.active === false;
  const recipient = departed ? cfg.register_admin : (u.on_leave ? (r.delegate || cfg.register_admin) : r.owner);
  if (departed) add('reassign', { reason: u ? 'owner has left' : 'owner not in the directory' });

  if (expired) {
    // Step 7: past expiry: withdraw, archive, tell the owner (or who stands in) and the register admin.
    add('withdraw_expired', { recipient, pull_date: iso(pull), reason: 'past expiry' });
    continue;
  }
  // Step 6: due within the window, or past review: remind the owner with the pull date.
  if (!departed && day(r.review_date) <= dueBy) {
    add('remind', { recipient, review_date: iso(day(r.review_date)), pull_date: iso(pull),
                    reason: day(r.review_date) < today ? 'past review' : 'review due' });
  }
  // Step 10: stored audience against live sharing, and register version against the index.
  if (r.status === 'current') {
    const f = files[String(r.file_id)], ix = indexed[String(r.id)];
    const problems = [];
    if (!f || !sameSet(r.audience, f.shared_with)) problems.push('audience differs from sharing');
    if (!ix || major(ix.version) !== major(r.version)) problems.push(`register version ${r.version}, index ${ix ? ix.version : 'missing'}`);
    if (problems.length) add('mismatch', { reason: problems.join('; ') });
  }
}
return [{ json: { week, checked, actions } }];
"""


def build() -> Workflow:
    w = Workflow("R13.2", "R13.2 Flag stale documents and pull expired ones from answers")
    # Step 1: weekly, early on the first working day (Monday, 06:00 in the workflow's time zone).
    w.node(W, "n8n-nodes-base.scheduleTrigger", 1.2,
           {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [1], "triggerAtHour": 6}]}},
           pos=[0, 0], notes="Weekly, Monday 06:00. Move it if Monday is not your first working day.")
    w.webhook(V, "r13-2-version-published",
              "Your document home calls this when a registered source publishes a version. Body: {source_id, version, major}.",
              pos=[0, 760])
    w.config("Config", {
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
    }, pos=[260, 380])
    w.connect(W, "Config")
    w.connect(V, "Config")
    w.if_("Weekly run?", f"={{{{ $('{W}').isExecuted }}}}", pos=[520, 380])
    w.connect("Config", "Weekly run?")

    # ---- weekly check ---------------------------------------------------------
    cfgu = "$('Config').first().json"
    w.http("Step 2: Read the register", "GET", f"={{{{ {cfgu}.register_url }}}}/sources", query={"_wrap": "1"},
           write=False, error_output=False, pos=[780, 0])
    w.http("Read the directory", "GET", f"={{{{ {cfgu}.directory_url }}}}/users", query={"_wrap": "1"},
           write=False, error_output=False, pos=[1040, 0], notes="Read-only: who is active, and who is on leave.")
    w.http("Step 10: Read sharing", "GET", f"={{{{ {cfgu}.documents_url }}}}/files", query={"_wrap": "1"},
           write=False, error_output=False, pos=[1300, 0])
    w.http("Step 10: Read the index", "GET", f"={{{{ {cfgu}.index_url }}}}/sources", query={"_wrap": "1"},
           write=False, error_output=False, pos=[1560, 0])
    w.code("Rules: steps 2, 4 to 7 and 10", RULES_JS, mode="runOnceForAllItems", pos=[1820, 0],
           notes="Rules decide; there is no AI step in R13.2.")
    w.connect("Weekly run?", "Step 2: Read the register", output=0)
    w.chain("Step 2: Read the register", "Read the directory", "Step 10: Read sharing", "Step 10: Read the index",
            "Rules: steps 2, 4 to 7 and 10")
    rules = "$('Rules: steps 2, 4 to 7 and 10').item.json"
    w.decision_log("Step 11: Log the weekly check", f"'week ' + {rules}.week", "'weekly check'",
                   f"JSON.stringify({{ sources_checked: {rules}.checked, actions: {rules}.actions.map(a => a.source + ': ' + a.action) }})",
                   pos=[2080, 0])
    w.code("Split the actions", f"return {rules}.actions.map(a => ({{ json: a }}));", mode="runOnceForAllItems", pos=[2340, 0])
    w.reserve_key("Step 3: Reserve key", f"{ACT}.key", pos=[2600, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[2860, 0])
    w.noop("Duplicate: stop", pos=[3120, -200], notes="This source, week and action was handled before.")
    w.chain("Rules: steps 2, 4 to 7 and 10", "Step 11: Log the weekly check", "Split the actions", "Step 3: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)
    w.switch("Action", f"={{{{ {ACT}.action }}}}", ["withdraw_missing", "reassign", "remind", "withdraw_expired", "mismatch"],
             pos=[3120, 0])
    w.connect("New key?", "Action", output=0)

    msgs = f"={{{{ {cfgu}.messaging_url }}}}/messages"
    src = f"={{{{ {cfgu}.register_url }}}}/sources/{{{{ {ACT}.source }}}}"
    admin = f"{cfgu}.register_admin"
    form = f"{cfgu}.owner_form_url"
    withdrawn = f"={{{{ JSON.stringify({{ status: 'withdrawn', withdrawn_reason: {ACT}.reason }}) }}}}"

    # Step 4
    w.http("Step 4: Set withdrawn", "PATCH", src, body=withdrawn, write=True, pos=[3380, -480],
           notes="Withdrawn: R13.1 never answers from it.")
    w.http("Step 4: Alert the register admin", "POST", msgs,
           body=f"={{{{ JSON.stringify({{ to: {admin}, subject: 'Source withdrawn: ' + ({ACT}.title || {ACT}.source), "
                f"text: {ACT}.title + ' has ' + {ACT}.reason + ', so it is withdrawn and answers nothing until it has an owner and dates.' }}) }}}}",
           write=True, pos=[3640, -480])
    w.chain("Step 4: Set withdrawn", "Step 4: Alert the register admin")
    # Step 5
    w.exception("Step 5: Exception queue: reassign the owner", f"{ACT}.source", "owner left",
                f"{ACT}.title + ': ' + {ACT}.reason + ' (' + {ACT}.owner + ')'", admin, pos=[3380, -240])
    w.http("Step 5: Tell the register admin to reassign", "POST", msgs,
           body=f"={{{{ JSON.stringify({{ to: {admin}, subject: 'Reassign the owner: ' + {ACT}.title, "
                f"text: {ACT}.title + ': ' + {ACT}.reason + ' (' + {ACT}.owner + '). Name a new owner in the register.' }}) }}}}",
           write=True, pos=[3640, -240])
    w.chain("Step 5: Exception queue: reassign the owner", "Step 5: Tell the register admin to reassign")
    # Step 6
    w.http("Step 6: Remind the owner, with the pull date", "POST", msgs,
           body=f"={{{{ JSON.stringify({{ to: {ACT}.recipient, subject: 'Review due: ' + {ACT}.title, "
                f"text: {ACT}.title + ' is due for review on ' + {ACT}.review_date + '. It is withdrawn from answers on ' + {ACT}.pull_date + "
                f"' unless you renew, replace or retire it: ' + {form} }}) }}}}",
           write=True, pos=[3380, 0])
    # Step 7
    w.http("Step 7: Set withdrawn", "PATCH", src, body=withdrawn, write=True, pos=[3380, 240])
    w.http("Step 7: Archive the file", "PATCH", f"={{{{ {cfgu}.documents_url }}}}/files/{{{{ {ACT}.file_id }}}}",
           body=f"={{{{ JSON.stringify({{ folder: {cfgu}.archive_folder }}) }}}}", write=True, pos=[3640, 240],
           notes="Moves the file where no bought assistant's search can reach it.")
    w.http("Step 7: Tell the owner and the register admin", "POST", msgs,
           body=f"={{{{ JSON.stringify({{ to: {ACT}.recipient, cc: {admin}, subject: 'Withdrawn: ' + {ACT}.title, "
                f"text: {ACT}.title + ' passed its expiry date (' + {ACT}.pull_date + ') and is withdrawn and archived. "
                f"Renew, replace or retire it: ' + {form} }}) }}}}",
           write=True, pos=[3900, 240])
    w.chain("Step 7: Set withdrawn", "Step 7: Archive the file", "Step 7: Tell the owner and the register admin")
    # Step 10
    w.exception("Step 10: Exception queue: mismatch", f"{ACT}.source", "register mismatch",
                f"{ACT}.title + ': ' + {ACT}.reason", admin, pos=[3380, 480])
    w.http("Step 10: Tell the register admin", "POST", msgs,
           body=f"={{{{ JSON.stringify({{ to: {admin}, subject: 'Register mismatch: ' + {ACT}.title, text: {ACT}.title + ': ' + {ACT}.reason }}) }}}}",
           write=True, pos=[3640, 480])
    w.chain("Step 10: Exception queue: mismatch", "Step 10: Tell the register admin")
    for i, n in enumerate(["Step 4: Set withdrawn", "Step 5: Exception queue: reassign the owner",
                           "Step 6: Remind the owner, with the pull date", "Step 7: Set withdrawn",
                           "Step 10: Exception queue: mismatch"]):
        w.connect("Action", n, output=i)

    w.node("Step 8: The owner renews, replaces or retires it", "n8n-nodes-base.stickyNote", 1,
           {"content": "## Step 8: The owner renews, replaces or retires it\nA person step, through the owner form linked in "
                       "every reminder and withdrawal. Only the owner's decision brings a withdrawn source back; only the "
                       "register admin edits owners and dates. A published version starts step 9.",
            "height": 200, "width": 360, "color": 5}, pos=[4160, -520])

    w.finish_key("Mark key done", f"{ACT}.key", "done", f"{ACT}.action", pos=[4160, 0])
    w.decision_log("Step 11: Decision log", f"{ACT}.source", f"{ACT}.action",
                   f"JSON.stringify({{ reason: {ACT}.reason, week_key: {ACT}.key, recipient: {ACT}.recipient || null, pull_date: {ACT}.pull_date || null }})",
                   pos=[4420, 0])
    for n in ["Step 4: Alert the register admin", "Step 5: Tell the register admin to reassign",
              "Step 6: Remind the owner, with the pull date", "Step 7: Tell the owner and the register admin",
              "Step 10: Tell the register admin"]:
        w.connect(n, "Mark key done")
    w.connect("Mark key done", "Step 11: Decision log")

    w.finish_key("Mark key failed", f"{ACT}.key", "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')",
                 pos=[4160, 720])
    w.exception("Exception queue: write failed", f"{ACT}.source", "write failed",
                f"'Step ' + {ACT}.action + ' failed part way; check the source, never retried'", admin, pos=[4420, 720])
    for n in ["Step 4: Set withdrawn", "Step 4: Alert the register admin", "Step 5: Tell the register admin to reassign",
              "Step 6: Remind the owner, with the pull date", "Step 7: Set withdrawn", "Step 7: Archive the file",
              "Step 7: Tell the owner and the register admin", "Step 10: Tell the register admin"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- step 9: a published version ------------------------------------------
    vkey = f"{VEV}.source_id + ':' + {VEV}.version + ':rebuild'"
    w.if_("Step 9: Major version?", f"={{{{ {VEV}.major === true }}}}", pos=[780, 760])
    w.connect("Weekly run?", "Step 9: Major version?", output=1)
    w.noop("Minor version: no rebuild", pos=[1040, 960], notes="Only a major version rebuilds the passages; step 10 compares major versions.")
    w.connect("Step 9: Major version?", "Minor version: no rebuild", output=1)
    w.reserve_key("Step 9: Reserve key", vkey, pos=[1040, 760])
    w.if_("Step 9: New key?", "={{ $json.is_new }}", pos=[1300, 760])
    w.noop("Step 9: Duplicate: stop", pos=[1560, 960], notes="This version was rebuilt before.")
    w.connect("Step 9: Major version?", "Step 9: Reserve key", output=0)
    w.connect("Step 9: Reserve key", "Step 9: New key?")
    w.connect("Step 9: New key?", "Step 9: Duplicate: stop", output=1)
    w.http("Step 9: Index: rebuild the source's passages", "POST", f"={{{{ {cfgu}.index_url }}}}/rebuilds",
           body=f"={{{{ JSON.stringify({{ source_id: {VEV}.source_id, version: {VEV}.version, remove_older_versions: true }}) }}}}",
           write=True, pos=[1560, 760], notes="The index cuts the new version at headings and removes the old version's passages.")
    w.connect("Step 9: New key?", "Step 9: Index: rebuild the source's passages", output=0)
    w.finish_key("Step 9: Mark key done", vkey, "done", "'rebuild requested'", pos=[1820, 760])
    w.decision_log("Step 9: Decision log", f"{VEV}.source_id", "'rebuild passages'",
                   f"JSON.stringify({{ version: {VEV}.version, major: true }})", pos=[2080, 760])
    w.chain("Step 9: Index: rebuild the source's passages", "Step 9: Mark key done", "Step 9: Decision log")
    w.finish_key("Step 9: Mark key failed", vkey, "failed", "'rebuild request failed'", pos=[1820, 960])
    w.exception("Step 9: Exception queue: rebuild failed", f"{VEV}.source_id", "write failed",
                "'Index rebuild request failed; rerun it (step 10 also flags the version)'", admin, pos=[2080, 960])
    w.connect("Step 9: Index: rebuild the source's passages", "Step 9: Mark key failed", output=1)
    w.connect("Step 9: Mark key failed", "Step 9: Exception queue: rebuild failed")

    # Several actions can come out of one weekly run: run each Postgres query once per item.
    for n in w.nodes:
        if n["type"] == "n8n-nodes-base.postgres":
            n["parameters"]["options"]["queryBatching"] = "independently"
    return w
