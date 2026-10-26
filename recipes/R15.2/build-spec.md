# R15.2 Check delivery and installation capacity before a promotion launches

Book chapter 15 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapters 17 and 20

Before a promotion promising delivery or installation goes out, it compares the weekly forecast with the crews' free slots and holds the promotion if they fall short; while it runs, it holds the next wave before a week overfills.
It never changes a schedule or forecasts demand.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/morning.blueprint.json`](make/morning.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-25 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Brief fields: windows, the promise (such as "installed within 10 days"), waves, and Ben's weekly forecast.
- A daily export of open slots per week, net of booked jobs, or the scheduling system's API.
- The four-week average of non-promoted bookings.

## Build steps

Table 15.2 sets out the brief's two status fields: Ben's approval and the capacity status.

1. Trigger when a brief is marked "ready", and each working morning while one is live.
2. Rule: the slot export is under 24 hours old; if not, hold and tell Owen.
3. For each week: free slots = open slots minus non-promoted jobs still to come.
4. Rule: each week's forecast fits its free slots; a week with no forecast goes to Tom.
5. Pass: set capacity "cleared", with the figures.
6. Fail: set "held"; tell Tom and Ben the shortfall by week.
7. Tom adds crew time or Ben changes the brief; the check reruns.
8. While live: at 90% of a week's planned share (its free slots at clearance), hold the next wave.

**Table 15.2: Promotion Brief Statuses and Who Sets Them**

| Status (field) | Set by | Means | What may happen next |
|---|---|---|---|
| Ready (approval) | Ben | Brief and weekly forecast complete | R15.2 checks capacity if delivery or installation is promised |
| Cleared (capacity) | R15.2, dated, with figures; Tom, while R15.2 is off | Every week fits | Ben may approve; a wave goes only on a clearance under 24 hours old |
| Held (capacity) | R15.2, with the shortfall by week | A week does not fit, a live week nears its share, or the export is stale | No approval or next wave until Tom adds crew time or Ben changes the brief |
| Manual check (capacity) | Owen or Tom, by stopping R15.2 | R15.2 is not running | Tom signs capacity by hand before any send |
| Approved (approval) | Ben, on "cleared" where a promise is made | The offer is final | R15.1 drafts and checks the claims |

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Export format changed | No week columns; held | Owen fixes the mapping |
| Flow stops | No clearance within 24 hours | Tom signs by hand |
| Sent while held | Send log | Tom and Ben replan waves |

## Variations

Smaller: a weekly spreadsheet with the rule as a formula.
Larger: capacity by crew skill and zone, one forecast column each.
Different system: read people's calendars, as in Case Example 15.1.

## Source

*AI Workflows That Run the Business*, Chapter 15, recipe R15.2. Pattern diagram: Figure 15.2 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
