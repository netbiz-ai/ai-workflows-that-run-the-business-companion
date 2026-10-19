# R8.1 Send staged overdue reminders that stop on payment or dispute

Book chapter 8 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapter 15

Sends each trade customer short, correct reminders around the due date, stopping once an invoice is paid, part-paid, disputed or held.
It never threatens, changes terms, charges a fee, stops credit or writes off.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | `n8n/workflow.json` | Not yet available |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A daily open-invoice export, saved to SharePoint before the run.
- Dispute and hold lists in SharePoint, each entry naming who set it, why and until when.
- An account owner (at Northstar, Ben) who logs any dispute or hold heard outside the AR mailbox before the next run.
- A reminder list of each invoice's next stage and date, written only by the flow.
- AR contacts only in the customer relationship management (CRM) system; templates merging only export and CRM fields; a shared AR mailbox.

## Build steps

Table 8.1 sets the stages and Worksheet 8.1 their days.

| Stage | Falls due | Released by | Then |
|---|---|---|---|
| Courtesy reminder | Before the due date | The workflow | First overdue reminder |
| First overdue reminder | After the due date | The workflow | Second overdue reminder |
| Second overdue reminder | After the first | The workflow | Final notice |
| Final notice | After the second | Aisha's approval; unapproved, it waits a day | Handoff |
| Handoff to Aisha | After the final notice | Nothing is sent | Aisha decides: a call, a credit stop, a write-off |

*Table 8.1: Reminder Stages and Where a Person Takes Over*

1. Trigger each working morning, after the export is due.
2. If today's export is missing or old, send nothing, log "no run", alert Aisha and end cleanly.
   Where R8.3 runs, do the same if it logged no mailbox check today, and hold final notices while an unlinked item over a day old is unreviewed.
3. Add new invoices at their first stage; list those due.
4. Stop any invoice that is part-paid or whose open amount is zero or less; a part payment or negative amount goes to Aisha, who logs a dispute or a "chase" hold.
5. Stop any invoice, or account, with an open dispute or a hold other than "chase".
6. Skip any invoice number plus stage already in the key log.
7. Fill the template from the export and CRM.
8. Rules check that number and amount match the export and no field is blank, or hold it and alert Aisha.
9. Earlier stages send from the AR mailbox; the final notice waits for Aisha's approval, and steps 2, 4 and 5 rerun before it sends.
10. Log the send or stop, its reason, and the next stage and date; after the final notice, open Aisha's handoff.

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Export missing or stale | Step 2 sends nothing | Finance saves it; Owen reruns |
| Send fails | Outlook error (no automatic retry) | Logged unsent; the stage stays due |
| Wrong or missing contact | Step 8 hold, or a bounce | Ben updates the CRM |
| Dispute heard but not logged | Only afterward: Aisha's monthly check of replies to sent reminders | Aisha reviews each miss with Ben |

## Variations

Smaller: a courtesy and one overdue reminder, then Aisha calls.
Larger: a text-message stage for consenting accounts, with its own reviewed template and golden case.
Different system: a helpdesk as the dispute list (Case Example 8.1).

## Source

*AI Workflows That Run the Business*, Chapter 8, recipe R8.1. Pattern diagram: Figure 8.1 in the book.
Worksheet 8.1 (your stop rules and stage days) and Case Example 8.1 are in the book's Chapter 8.
Northstar Home & Appliance is fictional; names in the tables are its people.
