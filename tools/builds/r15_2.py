"""R15.2 Check delivery and installation capacity before a promotion launches: rules only, no AI step.

Source: book Chapter 15, recipe R15.2, build steps 1 to 8 and Table 15.2 (recipes/R15.2/build-spec.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import V, Workflow  # noqa: E402

T = "Step 1: Brief marked ready"
M = "Step 1: Each working morning"
RULES = "Rules: steps 2 to 6 and 8"
R = f"$('{RULES}').item.json"

MORNING_JS = r"""
// Step 1 (each working morning) and step 7: live briefs get step 2 and step 8;
// a held brief not yet live is checked again, so Tom's added crew time clears it.
const briefs = $('Read every brief').first().json.items || [];
const out = [];
for (const b of briefs) {
  if (b.live && b.capacity === 'cleared') out.push({ json: { brief: b, mode: 'live' } });
  else if (!b.live && b.approval === 'ready' && b.capacity === 'held') out.push({ json: { brief: b, mode: 'check' } });
}
return out;
"""

READY_JS = r"""
// Step 1: the brief Ben marked "ready".
return [{ json: { brief: $('Read the brief').first().json, mode: 'check' } }];
"""

RULES_JS = r"""
// Steps 2 to 6 and step 8 of the book's R15.2, one result per brief.
const cfg = $('Config').first().json;
const morning = $('Step 1: Each working morning').isExecuted;
const items = morning ? $('Rule: briefs to check this morning').all() : $('Brief to check').all();
const exp = $('Step 2: Read the slot export').first().json;
const avg = Number($('Step 3: Read the non-promoted average').first().json.weekly_average || 0);
const nowIso = new Date().toISOString();
const today = nowIso.slice(0, 10);

// Step 2: the slot export is under the age limit; a changed format (no week columns) also holds.
const ageHours = (Date.now() - Date.parse(exp.exported_at)) / 3600000;
const stale = !exp.exported_at || !(ageHours < cfg.export_max_age_hours);
const rows = Array.isArray(exp.weeks) ? exp.weeks.filter(r => r && r.week != null && r.open_slots != null) : [];
const slots = Object.fromEntries(rows.map(r => [String(r.week), r]));

return items.map((it, i) => {
  const b = it.json.brief;
  const mode = it.json.mode;
  const key = mode === 'live' ? `${b.id}:live:${today}` : `${b.id}:${b.version}:${exp.exported_at}`;
  const base = { brief_id: b.id, mode, key };
  const hold = (reasons, notify, exception, extra = {}) => ({ json: Object.assign({}, base, {
    outcome: 'held', reasons, notify, exception,
    body: Object.assign({ capacity: 'held', capacity_checked_at: nowIso, capacity_reasons: reasons }, extra) }), pairedItem: i });

  if (stale || !rows.length) {
    const reason = stale ? 'slot export stale' : 'export format changed';
    const detail = stale ? `Slot export from ${exp.exported_at || 'unknown'} is not under ${cfg.export_max_age_hours} hours old` : 'Slot export has no week columns';
    return hold([reason], { to: [cfg.systems_owner], subject: `Promotion ${b.id} held: ${reason}`, text: detail },
                { reason, detail, owner: cfg.systems_owner });
  }

  // Step 8: while live, a week at its share of the free slots counted at clearance holds the next wave.
  if (mode === 'live') {
    const planned = ((b.capacity_figures || {}).weeks || []);
    const watch = planned.map(w => {
      const booked = Number((slots[String(w.week)] || {}).promoted_booked || 0);
      const share = Number(w.free) > 0 ? Math.round(booked / Number(w.free) * 100) : 100;
      return { week: w.week, planned_share: Number(w.free), booked, share_pct: share };
    });
    const near = watch.filter(w => w.share_pct >= cfg.watch_share_pct);
    if (near.length) {
      const text = near.map(w => `week ${w.week}: ${w.booked} of ${w.planned_share} (${w.share_pct}%)`).join('; ');
      return hold(near.map(w => `week ${w.week} at ${w.share_pct}% of its planned share`),
                  { to: [cfg.capacity_owner, cfg.promotion_owner], subject: `Promotion ${b.id}: next wave held`, text },
                  null, { live_watch: watch });
    }
    // Still fits: the clearance is dated again, so a wave can go on a clearance under 24 hours old.
    return { json: Object.assign({}, base, { outcome: 'cleared', reasons: [], notify: null, exception: null,
      body: { capacity: 'cleared', capacity_checked_at: nowIso, live_watch: watch } }), pairedItem: i };
  }

  // Table 15.2: R15.2 checks capacity only if delivery or installation is promised.
  if (!b.promise) {
    return { json: Object.assign({}, base, { outcome: 'no promise', reasons: [], notify: null, exception: null, body: null }), pairedItem: i };
  }

  // Step 3: free slots = open slots minus the non-promoted jobs still to come (the four-week average).
  const weeks = (b.weeks || []).map(w => {
    const s = slots[String(w.week)];
    const open = s ? Number(s.open_slots) : null;
    const free = s ? open - avg : null;
    const forecast = w.forecast == null || w.forecast === '' ? null : Number(w.forecast);
    return { week: w.week, open, non_promoted: avg, free, forecast,
             shortfall: forecast != null && free != null && forecast > free ? forecast - free : 0 };
  });
  const figures = { checked_at: nowIso, export: exp.exported_at, weeks };
  const noSlots = weeks.filter(w => w.open == null);
  if (!weeks.length || noSlots.length) {
    const detail = weeks.length ? `No slot figures for week ${noSlots.map(w => w.week).join(', ')}` : 'The brief has no weeks';
    return hold(['export format changed'], { to: [cfg.systems_owner], subject: `Promotion ${b.id} held: export format changed`, text: detail },
                { reason: 'export format changed', detail, owner: cfg.systems_owner }, { capacity_figures: figures });
  }

  // Step 4: each week's forecast fits its free slots; a week with no forecast goes to Tom.
  const missing = weeks.filter(w => w.forecast == null);
  const short = weeks.filter(w => w.shortfall > 0);
  if (missing.length || short.length) {
    const reasons = [...missing.map(w => `no forecast for week ${w.week}`),
                     ...short.map(w => `week ${w.week} short by ${w.shortfall}`)];
    // Step 6: held; Tom and Ben get the shortfall by week.
    const to = short.length ? [cfg.capacity_owner, cfg.promotion_owner] : [cfg.capacity_owner];
    return hold(reasons, { to, subject: `Promotion ${b.id} held`, text: reasons.join('; ') },
                missing.length ? { reason: 'week with no forecast', detail: reasons.join('; '), owner: cfg.capacity_owner } : null,
                { capacity_figures: figures });
  }

  // Step 5: cleared, dated, with the figures; each week's free slots are its planned share for step 8.
  return { json: Object.assign({}, base, { outcome: 'cleared', reasons: [], notify: null, exception: null,
    body: { capacity: 'cleared', capacity_checked_at: nowIso, capacity_reasons: [], capacity_figures: figures } }), pairedItem: i };
});
"""


def build() -> Workflow:
    w = Workflow("R15.2", "R15.2 Check delivery and installation capacity before a promotion launches")
    w.webhook(T, "r15-2-brief-ready", "Your brief list calls this when Ben marks a brief \"ready\". Body: {brief_id}.", pos=[0, 0])
    w.node(M, "n8n-nodes-base.scheduleTrigger", V["schedule"],
           {"rule": {"interval": [{"field": "cronExpression", "expression": "0 7 * * 1-5"}]}}, pos=[0, 400],
           notes="Each working morning (07:00, Monday to Friday; edit for your week): live briefs, and held briefs again (step 7).")
    w.config("Config", {
        "briefs_url": "https://<your promotion brief list API>",
        "scheduling_url": "https://<your delivery-scheduling export API>",
        "messaging_url": "https://<your messaging API>",
        "export_max_age_hours": 24,
        "watch_share_pct": 90,
        "capacity_owner": "<your operations manager>",
        "promotion_owner": "<your promotion owner>",
        "systems_owner": "<your systems owner>",
    }, pos=[260, 200])
    w.connect(T, "Config")
    w.connect(M, "Config")
    w.if_("Morning run?", f"={{{{ $('{M}').isExecuted }}}}", pos=[520, 200])
    w.connect("Config", "Morning run?")

    cfg = "$('Config').item.json"
    w.http("Read the brief", "GET", f"={{{{ {cfg}.briefs_url }}}}/briefs/{{{{ $('{T}').item.json.body.brief_id }}}}",
           write=False, error_output=False, pos=[780, 0])
    w.code("Brief to check", READY_JS, mode="runOnceForAllItems", pos=[1040, 0])
    w.connect("Morning run?", "Read the brief", output=1)
    w.connect("Read the brief", "Brief to check")

    w.http("Read every brief", "GET", f"={{{{ {cfg}.briefs_url }}}}/briefs", query={"_wrap": "1"},
           write=False, error_output=False, pos=[780, 400])
    w.code("Rule: briefs to check this morning", MORNING_JS, mode="runOnceForAllItems", pos=[1040, 400])
    w.connect("Morning run?", "Read every brief", output=0)
    w.connect("Read every brief", "Rule: briefs to check this morning")

    cfg1 = "$('Config').first().json"
    w.http("Step 2: Read the slot export", "GET", f"={{{{ {cfg1}.scheduling_url }}}}/exports/latest",
           write=False, error_output=False, pos=[1300, 200])
    w.http("Step 3: Read the non-promoted average", "GET", f"={{{{ {cfg1}.scheduling_url }}}}/averages/non-promoted",
           write=False, error_output=False, pos=[1560, 200],
           notes="The four-week average of non-promoted bookings.")
    for n in w.nodes:
        if n["name"] in ("Step 2: Read the slot export", "Step 3: Read the non-promoted average"):
            n["executeOnce"] = True  # one read per run, however many briefs the morning checks
    w.code(RULES, RULES_JS, mode="runOnceForAllItems", pos=[1820, 200],
           notes="Rules decide; R15.2 has no AI step. It never changes a schedule or forecasts demand.")
    w.connect("Brief to check", "Step 2: Read the slot export")
    w.connect("Rule: briefs to check this morning", "Step 2: Read the slot export")
    w.chain("Step 2: Read the slot export", "Step 3: Read the non-promoted average", RULES)

    w.reserve_key("Reserve key", "$json.key", pos=[2080, 200])
    w.if_("New key?", "={{ $json.is_new }}", pos=[2340, 200])
    w.noop("Duplicate: stop", pos=[2600, 0], notes="This brief version was checked against this export before.")
    w.chain(RULES, "Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    w.if_("Promise to check?", f"={{{{ {R}.body !== null }}}}", pos=[2600, 200])
    w.connect("New key?", "Promise to check?", output=0)
    w.http("Steps 5, 6 and 8: Set capacity status", "PATCH", f"={{{{ {cfg1}.briefs_url }}}}/briefs/{{{{ {R}.brief_id }}}}",
           body=f"={{{{ JSON.stringify({R}.body) }}}}", write=True, pos=[2860, 200],
           notes="Writes the capacity field only: \"cleared\" with the figures, or \"held\" with the shortfall by week. A write: never retried.")
    w.connect("Promise to check?", "Steps 5, 6 and 8: Set capacity status", output=0)

    w.if_("Tell someone?", f"={{{{ {R}.notify !== null }}}}", pos=[3120, 200])
    w.http("Steps 2, 6 and 8: Tell Tom, Ben or Owen", "POST", f"={{{{ {cfg1}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({R}.notify) }}}}", write=True, pos=[3380, 100])
    w.if_("To the exception queue?", f"={{{{ {R}.exception !== null }}}}", pos=[3640, 200])
    w.exception("Exception queue: held for a person", f"{R}.brief_id", "capacity held",
                f"{R}.exception.reason + ': ' + {R}.exception.detail", f"{R}.exception.owner", pos=[3900, 100])
    w.connect("Steps 5, 6 and 8: Set capacity status", "Tell someone?")
    w.connect("Tell someone?", "Steps 2, 6 and 8: Tell Tom, Ben or Owen", output=0)
    w.connect("Tell someone?", "To the exception queue?", output=1)
    w.connect("Steps 2, 6 and 8: Tell Tom, Ben or Owen", "To the exception queue?")
    w.connect("To the exception queue?", "Exception queue: held for a person", output=0)

    w.finish_key("Mark key done", f"{R}.key", "done", f"{R}.outcome", pos=[4160, 200])
    w.decision_log("Decision log", f"{R}.brief_id", f"{R}.mode + ': ' + {R}.outcome",
                   f"JSON.stringify({{ reasons: {R}.reasons, figures: ({R}.body || {{}}).capacity_figures || ({R}.body || {{}}).live_watch || null }})",
                   pos=[4420, 200])
    w.connect("To the exception queue?", "Mark key done", output=1)
    w.connect("Exception queue: held for a person", "Mark key done")
    w.connect("Promise to check?", "Mark key done", output=1)
    w.connect("Mark key done", "Decision log")

    w.finish_key("Mark key failed", f"{R}.key", "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[3120, 520])
    w.exception("Exception queue: write failed", f"{R}.brief_id", "write failed",
                "'Capacity status or message write failed; check the brief, never retried'", f"{cfg1}.systems_owner", pos=[3380, 520])
    w.connect("Steps 5, 6 and 8: Set capacity status", "Mark key failed", output=1)
    w.connect("Steps 2, 6 and 8: Tell Tom, Ben or Owen", "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")
    return w
