# The outside monitor

A workflow cannot report its own silence.
Build one scheduled monitor that reads each workflow's decision log and alerts the owner when the newest line is older than its rhythm allows.
This is a tool-neutral specification; build it on any platform, following the two rules below.

## Rules

- **Run it on a different platform, or at least a different account**, from the workflows it watches.
  At Northstar, the book's fictional company, n8n workflows are watched from Power Automate, and Power Automate flows from n8n.
- **Have it prove it is alive** with a weekly "all workflows checked" note to a person.
- **Count the monitor in your budget.**
  A scheduled trigger may count every time it fires, whatever the outcome; on n8n a Schedule Trigger counts as an execution every time it fires (n8n documentation, checked 2026-10-12).

## The monitor list

One row per watched workflow, kept beside the recipe library.

| Workflow | Decision log location | Expected rhythm | Weekly test item? | Builder | Owner | Deputy |
|---|---|---|---|---|---|---|
| `<recipe ID and name>` | `<where its decision log is>` | `<the longest normal gap between log lines>` | `<yes, for a workflow with no rhythm; otherwise no>` | | | |

For a workflow with no rhythm, such as a leave-request workflow, the monitor sends a marked test item weekly, which the workflow logs and skips; no log line means a dead trigger.
The workflow under watch needs a rule that recognizes the marked test item, logs it and skips it.

## What it checks on each run

1. For each workflow on the list, read the newest line of its decision log.
   If it is older than the expected rhythm allows, alert the builder, then the owner.
2. For a workflow with a weekly test item, send the marked item on its day, and check on the next run that the workflow logged it.
   No log line means a dead trigger: alert the builder, then the owner.
3. Check for failed runs and for the platform's own switch-off notice, and alert as the signals table in [`README.md`](README.md) sets out.
4. Read each exception queue's oldest item, and alert the owner when it is older than the limit you set, such as two working days.
5. Total month-to-date usage from the units each run logged, each morning, or hourly where units could run out in a day, and apply the budget alerts in [`budget-alert.md`](budget-alert.md).
6. Once a week, send a person the weekly digest: volume, cost per run and the share refused or escalated for each workflow against last month, ending "all workflows checked".

A missed weekly note means the monitor itself has stopped.

## Source

*AI Workflows That Run the Business*, Chapter 17, "Run monitoring: catch a silent workflow before a customer does".
