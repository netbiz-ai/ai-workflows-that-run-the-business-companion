# Budget alerts at 80% and 100%

A budget turns the recipe's monthly cost line into a limit someone watches, in two lines: the platform's unit and AI usage.
Plan limits apply to the whole account or instance, not to one workflow.
This is a tool-neutral specification; the outside monitor in [`run-monitor.md`](run-monitor.md) carries it out.

## How it works

1. Each workflow logs the units each run used.
2. The outside monitor totals month-to-date usage each morning, or hourly where units could run out in a day.
3. At 80% of the monthly budget, it tells the owner.
4. At 100%, it tells the cost approver, and the pre-written 100% rule fires.
5. Where a model provider offers a spending cap, set it just above the workflow's AI budget.

**At 80%: someone looks.**
The owner checks for a real rise in volume, or a loop, empty polling or re-runs.
*Estimate:* ten minutes with the decision log usually tells which.

**At 100%: the pre-written rule fires.**
Write it in advance; the owner carries it out with the kill switch unless the monitor can.
Choose one rule per workflow:

- **keep running and tell the cost approver**, for workflows that protect money or customers, such as R7.3's bank-detail check or R4.2's escalations;
- **pause and fall back to the manual process**, where a person can do the work for a few days, such as R6.2;
- **switch to a cheaper model or a smaller batch**, only if that variant already passed the golden set.

Until you confirm on the vendor's plan page what an n8n Cloud or Make plan does at its limit, its time-saving workflows pause and fall back at 100%.

## What each platform counts, and what happens at the limit

As of October 2026, checked 2026-10-12, as each vendor documents it; see the [platform cards](../platforms/README.md) for current facts.

| Platform | What it counts | At or over the plan's limit |
|---|---|---|
| n8n Cloud | Production executions per instance, reset at the start of each month; editor test runs are free | Not confirmed in the book's sources; confirm on the plan page |
| Make | Credits: most module actions 1; an empty polling check 1; AI provider tokens priced separately for input and output | Not confirmed in the book's sources; confirm on the plan page |
| Zapier | Tasks from action steps; triggers and polling checks are free; AI by Zapier 1, 3 or 5 tasks a step by model tier | Free pauses; paid plans bill overage at 1.25x (annual) or 2.5x (monthly) and pause at 3x the subscription |
| Power Automate | Licenses, not runs; AI steps in Copilot Credits | No per-run charge; the budget risk is a license change |

On a license-billed platform, the budget risk is a change that adds a premium connector or action; that change goes to the cost approver before anyone builds it (book Chapter 17, change control).

## Worksheet: your budget and change rule

Fill in one column per workflow, then ask the cost approver to sign it; if they cannot tell what a workflow costs and what happens at 100%, rewrite it.

| Field | Workflow 1 | Workflow 2 |
|---|---|---|
| Workflow, owner, cost approver | | |
| Monthly budget: units and money | | |
| At 80%, who is told | | |
| At 100%, the workflow will | | |
| Expected rhythm, for the outside monitor | | |
| Changes the owner approves | | |
| Changes that also need a cost approval | | |
| Exit route | | |

The book's filled example is Northstar's R9.3 leave-request workflow, billed by license, not by run (Northstar is fictional and its figures are modeled):

| Field | Example: R9.3 at Northstar (modeled) |
|---|---|
| Workflow, owner, cost approver | R9.3 leave requests; Aisha; Helen |
| Monthly budget: units and money | Standard connectors, $0 new spend; no AI |
| At 80%, who is told | Not applicable; license-based |
| At 100%, the workflow will | Not applicable; license-based |
| Expected rhythm, for the outside monitor | Irregular; one marked test request a week, logged and skipped |
| Changes the owner approves | Rules, form fields, golden set |
| Changes that also need a cost approval | Any premium connector or action |
| Exit route | Rebuild on n8n from its tool-neutral build steps |

## A worked example: the booking form that polled all week

Illustrative; not Northstar.

A 40-person plumbing firm runs a Make scenario that checks its job-booking form every 15 minutes.
The office manager gave it a budget of 3,000 credits a month, from a cost line that assumed an instant trigger, out of the 10,000 in Make's Core plan as of October 2026.
*Estimate:* that is about $3.18 of the plan's $10.59 a month (3,000 / 10,000 x $10.59, billed monthly).
*Estimate:* the empty checks use about 670 credits a week (4 an hour x 24 x 7) and the bookings about 200 more, so the 80% alert, at 2,400 credits, fires in week three.
That alert is how the office manager finds the waste: about 2,900 credits a month (670 x 4.33) spent before a single booking is handled.
At 100% the scenario pauses, and the office takes bookings from the form's inbox by hand.
An instant trigger (book Chapter 2) removes most of the waste.

## Source

*AI Workflows That Run the Business*, Chapter 17 ("Budgets for AI workflow automation", Table 17.2, Case Example 17.1, Worksheet 17.1).
