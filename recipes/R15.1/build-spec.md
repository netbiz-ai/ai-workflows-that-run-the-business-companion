# R15.1 Draft campaign copy from approved product facts and check every claim

Book chapter 15 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapter 20

When Ben approves a brief, AI drafts each channel version from the claims list only, and rules and approvers check every claim up to the send.
It never sends, invents a price, reads a customer list, or keeps an unlisted claim.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-28 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/approver-signs.blueprint.json`](make/approver-signs.blueprint.json) and [`make/before-send.blueprint.json`](make/before-send.blueprint.json) and [`make/ben-approves.blueprint.json`](make/ben-approves.blueprint.json) and [`make/each-morning.blueprint.json`](make/each-morning.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-30 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- The claims list, owned by Ben: claim ID, approved wording, type, source of record, owner, last confirmed, expiry.
- Read access to the customer relationship management (CRM) price list, owned by Aisha Karim, Finance and HR Manager.
- A brief: offer, segment, channels, dates, claim IDs, approval status.
- A style sheet, and twelve past versions with every claim marked: ten to tune, two held back.

## Build steps

Table 15.1 names an approver for each claim type whose source the copywriter does not control; "free" offers, warranties and comparisons carry legal substantiation rules, so those approvers should take advice.

**Table 15.1: Claims That Need a Named Approver**

| Claim type | Example | Source of record | Named approver |
|---|---|---|---|
| Price, discount or "free" offer | Free installation on washer and dryer pairs | Price list in the CRM | Aisha |
| Delivery or installation time | Installed within 10 days | Delivery-scheduling system, through R15.2 | Tom |
| Warranty or guarantee | One-year warranty on dishwashers | Warranty terms | Tom |
| Comparison, with a competitor or older model | Quieter than the big-box brands | None by default | Helen; unused unless she approves |
| Environmental or energy claim | Energy-saving washer | Manufacturer data | Helen; unused unless she approves |
| Any other listed claim | A product's dimensions | The claims list | None; Ben reads the final copy |

1. Trigger when Ben marks the brief "approved"; run once per channel version.
2. Rule: every claim exists, is unexpired and was confirmed by its owner since its source or row last changed, and a delivery promise has R15.2's "cleared"; otherwise the brief returns to Ben, with no AI call.
3. Load only those claims, their price rows and the style sheet.
4. AI drafts the version without tools, told: "Use only these claims, in their approved words; tag each claim ([C12]) and price ([P:WD-200]); add no other fact."
5. A second AI call, given only the untagged copy, is told: "Quote every price, time, warranty, comparison, quantity or environmental claim."
6. Rules: each tag keeps the approved wording or price; each listed claim matches a tag; a scan for digits, "$", "free", "warranty", "best" and day words finds nothing untagged.
7. A failure is redrafted once, then goes to Ben; an untagged claim whose type has a named approver goes to that approver (Helen for comparisons).
8. Each named approver signs; a two-type claim, such as "free installation", goes to both.
9. Ben approves; the text is stored with its fingerprint (a hash that changes if any character does), and a changed fingerprint before a send stops it and reruns steps 5 and 6.
10. Each morning, a changed source or price holds the claim's unsent versions.

## AI steps

- Step 4 returns the drafted version with every claim and price tagged: [`prompts/draft-copy.md`](prompts/draft-copy.md).
- Step 5 returns every claim quoted from the untagged copy: [`prompts/list-claims.md`](prompts/list-claims.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).
Go-live: every case passes, and the second AI call finds every hand-marked claim in the held-back versions.

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| AI call fails | No tags to check | Retried twice; then Owen told |
| Approver away | Sign-off open two days | Helen names a stand-in |
| Listing call misses a claim | Ben's final read | Owen adds a case and scan word |

## Variations

Smaller: no AI; Ben writes the copy and the rules check it.
Larger: per-segment versions, each a golden case and a cost line unit.
Different system: a CRM's AI writer can draft if the checks still run.

## Source

*AI Workflows That Run the Business*, Chapter 15, recipe R15.1. Pattern diagram: Figure 15.1 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
