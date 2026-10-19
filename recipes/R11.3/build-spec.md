# R11.3 Route purchase approval by amount and remaining budget

Book chapter 11 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapters 15 and 18

Sends each checked request to the right approver, records the decision, and releases it only if its quote is still valid and its supplier clear.
It never approves an order itself, changes a budget, or sends an order to a supplier.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | `n8n/workflow.json` | Not yet available |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Aisha's budget list: budget, spent from the latest accounting export, and committed (approved, not invoiced).
- Table 11.2, signed by Aisha and Helen; only they change its values (Chapter 17).
- Stand-ins: Helen for Tom; Tom for Helen, and for Helen's own requests.

## Build steps

Table 11.2 lists every check in running order.

Table 11.2: Purchase Approval Routing and Block Rules

| Check, in order | Recipe | If the answer is no | Who acts next |
|---|---|---|---|
| Is the supplier active with no hold? | R11.2 | Blocked: supplier inactive or on hold | The requester |
| Is the total over $500? | R11.2 | No PO needed; no more checks | The requester |
| Is a checked quote row referenced, or a waiver given? | R11.2 | Blocked: no checked quote | The requester |
| Is the quote valid for five more working days, matched, freight stated or included? | R11.2 | Blocked: quote expiring or not matched | The requester |
| Is the item allowed for the budget line? | R11.2 | Blocked: item outside policy | The requester |
| Is the price within 30% of the last price paid? | R11.2 | Held | Tom confirms the price |
| Is the budget export seven days old or less? | R11.3 | Held | Aisha refreshes the export |
| Is the request within remaining budget, and the total $10,000 or less? | R11.3 | Sent to Helen; Aisha copied if over budget | Helen; Tom if the answer is yes |
| Is the approver neither the requester nor the payment approver? | R11.3 | Skipped to the next approver | The next approver |
| When the approval arrives, is the quote still valid and the supplier clear? | R11.3 | Blocked: quote expired during approval, expires within release margin, or supplier on hold | The requester |

A waiver skips the fourth row and the quote half of the last.

1. Trigger when a request's status becomes "checked; to approval".
2. Duplicate key: request ID and version; if an approval is open or decided, stop.
3. Remaining budget is budget less spent and committed; an export over seven days old waits for Aisha.
4. Rule: over remaining budget on this request alone (Aisha copied), or over $10,000 on R11.2's split total, goes to Helen; the rest to Tom.
5. Rule: skip any approver or stand-in who is the requester or payment approver; Helen's own go to Tom.
6. Start one approval showing amount, valid-until date, comparison link and budget after.
7. No answer in two working days: remind, and warn the requester if the quote expires first.
8. No answer in three: send it to the stand-in.
9. Approved: rerun R11.2's supplier rule and step 6 with a two-working-day margin; else block, with its reason code.
10. Passing: set "approved" and lock it (an edit needs a new request); write the commitment; tell the buyer to raise the PO.
11. Rejected: record the comment; write no commitment.
12. With each export, reduce commitments by bills; a bill over its commitment by more than Aisha's set tolerance goes to Aisha.

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

Reads retry three times, then Owen is alerted; a failed write is never retried (as in R11.1).

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Approver and stand-in away | No answer after the stand-in | Helen decides |
| Commitment never cleared | Monthly reconciliation | Aisha clears it |
| Approval lost after an error | Request stuck a day | Owen checks the list, then reruns it |

## Variations

Smaller: one approver, the owner above the threshold; budget updated weekly by hand; if the owner orders, approves and pays, the outside bookkeeper reviews orders monthly.
Different system: an accounting platform's approval chain can replace steps 4 to 8 if it reads remaining budget; keep step 9.

## Source

*AI Workflows That Run the Business*, Chapter 11, recipe R11.3. Pattern diagram: Figure 11.3 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
