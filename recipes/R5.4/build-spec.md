# R5.4 Route quote approval by value and discount

Book chapter 5 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapters 8 and 13

Routes every draft quote, locked where the CRM can, to its one allowed approver; it never approves or sends, and has no AI step.
Where the CRM cannot lock quotes, a weekly sent-to-approved match is the declared backstop: it detects, not prevents.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | `n8n/workflow.json` | Not yet available |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- R5.3, or an "awaiting approval" status for hand-built quotes.
- Value and discount thresholds signed by Helen Brandt, Owner and CEO.
- An approver, deputy and response deadline at each level.
- Book 1's Checklist 13.1, the quote approver's check.

## Build steps

Table 5.1 sets who approves each quote; as in Book 1, Ben's own go to Helen.
Set limits where a mistake costs more than a review, and deadlines by how long customers wait (Book 1, Chapter 8).

**Table 5.1: Quote Approval by Value and Discount**

| Quote value, after discount | Largest line discount within standard | Largest line discount over standard | Multi-year or non-standard term |
|---|---|---|---|
| Up to the salesperson's limit | Salesperson | Ben | Ben |
| Salesperson's limit to Ben's limit | Ben | Ben | Ben |
| Over Ben's limit | Helen | Helen | Helen |

1. Trigger when a quote is set "awaiting approval".
2. Stop if the duplicate key, quote ID plus revision, was seen.
3. From the CRM record, not the quote text, recompute value after discount, largest line discount, and multi-year, off-list and non-standard flags.
4. If the stamped price list is no longer current, send the quote back to R5.3.
5. Look up the approver in Table 5.1.
6. Send the request with Book 1's Checklist 13.1; if sending fails, return the quote, locked, and tell Owen.
7. Remind at the deadline, ask the deputy at twice it, and at three times return the quote, locked, and tell Ben.
8. On approval, log approver, time and version, and unlock sending; on rejection, return it with the comment; any later edit routes again.

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Approver away | Deadline passes | Deputy decides |
| Quote sent unapproved | Weekly match | Ben calls the customer |
| Flow turned off | Outside monitor (Chapter 17) | Owen restarts it |

## Variations

Smaller: one threshold and approver, in the CRM's own approval step.
Different system: a design studio keys Table 5.1 on fee and discounted day rate.

## Source

*AI Workflows That Run the Business*, Chapter 5, recipe R5.4. Pattern diagram: Figure 5.4 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
