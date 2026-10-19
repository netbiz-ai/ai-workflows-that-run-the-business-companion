# R6.3 Find likely duplicate accounts and queue them for a person to merge

Book chapter 6 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapters 13 and 21

Each week, queues likely duplicate account pairs, each with a one-sentence reason, for a person to merge or reject.
It never merges, deletes or edits an account, or re-raises a rejected pair unless a Table 6.3 signal changes.
Store accounts stay out; a person links one to a firm's trade account, keeping both records, never merged.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | `n8n/workflow.json` | Not yet available |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A scheduled export of accounts and contacts with Table 6.3's signals, open quotes, credit terms and system links.
- A list of webmail and shared domains to exclude.
- A suppression list and merge queue, with a form to record "merge" or "reject".
- A named merger and the CRM's own merge function.

## Build steps

Rather than compare all 80,000 pairs among 400 accounts, group those sharing any Table 6.3 signal and compare within groups.

Table 6.3 in the book: Duplicate Signals and What Each Triggers.

| Signal | Normalized as | On its own | Watch for |
|---|---|---|---|
| Tax ID, where held | Digits only | Queues the pair | Branches of one business that keep separate accounts |
| Phone | Digits, with the country code | Queues the pair | A management firm's number on each client's account |
| Billing address | Standard form | Needs a second signal | Shared offices and sister companies |
| Company email domain | Lowercase, after the @; webmail dropped | Needs a second signal | A shared or webmail domain missing from your list |
| Name | Lowercase, without "Inc", "LLC", "Ltd" or punctuation | Needs a second signal | Sister companies with similar names |

1. Trigger on a weekly schedule, outside trading hours.
2. Export accounts and contacts; if the export fails, changes format or shrinks sharply, stop and tell Owen.
3. Normalize each signal as Table 6.3 shows.
4. Group accounts; queue a pair sharing one strong or two weaker signals.
5. Drop suppressed pairs unless a signal field has changed since; a new activity does not count.
6. Check the key log for the two account IDs, sorted; a waiting pair is not queued again.
7. The AI explains the match from the matched fields only; if it names any other field, the pair queues with signals alone.
8. Mark "Ben confirms first" for an open quote, "Aisha confirms first" for credit terms.
9. Queue the pair with both records exported, so the merger can choose the survivor.
10. Log each decision; a rejection goes on the suppression list.

## AI steps

- Step 7 returns `reason`: [`prompts/explain-match.md`](prompts/explain-match.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Wrong merge | Salesperson finds missing history | Owen rebuilds the record from the export, or uses the CRM's merge undo |
| AI or export error | Error after three retries (no write is retried) | AI: signals alone. Export: run stops, Owen told |
| Queue unread | Pairs older than two weeks | Ben and Owen clear it |
| Export short or changed | Step 2's check | Owen fixes the mapping, reruns |

## Variations

Smaller: no AI; the queue shows the signals alone.
Larger: compare contacts too, with a contact who moved firms in the golden set.
Different system: an accounting practice matches clients on tax IDs.

## Source

*AI Workflows That Run the Business*, Chapter 6, recipe R6.3. Pattern diagram: Figure 6.3 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
