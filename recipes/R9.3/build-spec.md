# R9.3 Take leave requests, check the balance and route to the manager

Book chapter 9 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapter 16

Takes every leave request in one place, checks balance and policy, and puts it before the manager.
It never decides a request, changes a balance, or judges whether leave is protected.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | `n8n/workflow.json` | Not yet available |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A signed-in form: leave type and dates, no free-text reason.
- A daily balance export from the HR platform to SharePoint.
- Notice rules and work patterns approved by Aisha; the employee list, with managers and stand-ins.

## Build steps

1. Trigger on a request or cancellation.
2. Rules: for an unlisted requester, send nothing and tell Aisha; sick or family leave goes to Aisha alone.
3. Duplicate key, employee, type and dates: if open, stop.
4. Look up today's balance; if stale, mark "balance not checked".
5. Rules: valid dates, notice met, balance less open requests covers the days, no overlap; each failure is a warning.
6. Send it, with warnings and who else is off, to the manager; remind at 2 working days, and at 4 go to the stand-in and tell Aisha.
7. If approved, Aisha re-checks the balance as she records it.
8. Notify the employee and log; Aisha reverses a cancellation.

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Balance export missing | Step 4 | Aisha checks at recording |
| Employee notice fails | Send error | Aisha tells them |
| Recorded leave differs | Aisha's re-check | She corrects it |

## Variations

Smaller: approvals only; the manager checks the balance.
Larger: several sites, routed to each site's manager or stand-in.
Different system: your HR platform's leave module.

## Source

*AI Workflows That Run the Business*, Chapter 9, recipe R9.3. Pattern diagram: Figure 9.3 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
This is operational guidance, not legal or HR advice; employment rules vary by place.
