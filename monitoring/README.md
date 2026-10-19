# Monitoring and budgets

Run monitoring notices a workflow that has failed, piled up work or stopped; a budget turns each recipe's monthly cost line into a limit someone watches.
This folder is tool-neutral; platform facts are dated and live on the cards in [`platforms/`](../platforms/README.md).

| File | What it is |
|---|---|
| [`run-monitor.md`](run-monitor.md) | The outside monitor: one scheduled workflow that catches a silent workflow |
| [`budget-alert.md`](budget-alert.md) | A monthly budget per workflow, with alerts at 80% and 100%, and a worksheet |

## The three questions

A switched-off workflow or an expired trigger login sends no error, and the exception queue looks empty.
Monitoring asks three questions.

1. **Did it run?** Silence beyond the workflow's rhythm is an alert, not good news.
   R4.1, message routing, runs many times an hour; R12.1, the weekly figures, runs on Thursday evening.
2. **Did it work?** Failed runs, items in the exception queue, and the oldest one's age.
3. **Is it still behaving like itself?** Volume, cost per run and the share refused or escalated, against last month, reviewed each Monday from the monitor's weekly digest.

## Signals, alert levels and who is told

The 80% and 100% budget levels are the book's defaults; set every other threshold from a month of normal running.
The cost approver, whoever signs off spending, is named in the governance card's Approver field; name a deputy for every alert so a vacation does not silence it.

| Signal | Why it matters | Alert when | Who is told |
|---|---|---|---|
| No run in the expected window | The workflow, its trigger or its login has stopped | Newest log line older than the rhythm allows | Builder, then owner |
| Platform switched it off | The platform's own failure rule fired | When the platform notifies; otherwise at the end of the rhythm window | Builder and owner |
| Failed runs | Something is broken, often a login or a changed field | Any failure on a write step; a run of failures elsewhere | Builder |
| Exception queue age | Work is quietly piling up | Oldest item older than you set, such as two working days | Owner |
| Refusal or escalation share | The AI step or its sources have changed | Clearly above last month's level | Owner and builder |
| Cost per run | A model, prompt or pricing change has raised it | Above the monthly cost line's assumption | Builder |
| Units used this month | The plan or budget will run out | 80% of the monthly budget, then 100% | Owner, then cost approver |

The platform switch-off rules are in [`patterns/error-handling/`](../patterns/error-handling/README.md) and on each platform card.

## When AI costs change without a change

AI usage moves for three reasons you do not control; each has a signal that catches it.

| What moves | Example, as of October 2026 | What catches it |
|---|---|---|
| The platform's rates or defaults | A new AI by Zapier step on a paid plan defaults to the Premium tier: 5 tasks a run, plus 5 for each tool call | Cost per run |
| The model's price | Announced as of October 2026: from 2027-01-01, Gemini 3.8 Flash input and output prices double | The change calendar |
| The model itself | A newer model writes longer answers, or reasons before it answers | Cost per run, and the monthly golden-set rerun |

Two habits catch a model change:

1. Choose a named model, not "Auto", where the platform lets you, so any switch is your change.
2. Rerun every AI workflow's golden set monthly against its pass line, and whenever a vendor announces a new default or retirement ([`golden-sets/`](../golden-sets/README.md)).

Keep announced vendor changes on one change calendar and act a month before each; the dated 2026 changes the book relies on are in [`platforms/README.md`](../platforms/README.md).

## If you build for several companies

Keep one budget and cost approver per client, keep each client's accounts, keys and bills in the client's name, and never share a monitor or alert account between them.

## Checklist

- [ ] Set a monthly budget for each workflow, in the platform's unit and in money.
- [ ] Turn on alerts at 80% and 100%, and decide who carries out each workflow's 100% action.
- [ ] Build an outside monitor on another platform or account, and have it confirm weekly it is alive.
- [ ] Recheck AI costs for any flow that draws Copilot Credits.

## Source

*AI Workflows That Run the Business*, Chapter 17 (Tables 17.1 and 17.3, Chapter checklist).
