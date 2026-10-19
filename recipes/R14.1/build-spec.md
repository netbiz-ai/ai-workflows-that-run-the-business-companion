# R14.1 Turn a transcript into a draft action list for the chair to verify

Book chapter 14 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapters 8 and 26

After each in-scope meeting, AI proposes actions from the transcript, each with its line's time stamp, and an owner and due date only if said aloud.
It never creates a task, invents an owner, or reads an out-of-scope meeting.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Transcription for in-scope series only.
- A meeting register, owned by Tom: series, chair, backup, calendar.
- A scope rule: internal meetings only, never human resources (HR), disciplinary or negotiation.
- An action list (at Northstar, a SharePoint list), one row per proposed item.
- Ten past transcripts with actions marked by hand.
- Consent, works-council agreements, access and erasure requests, and the AI provider's retention terms settled with your adviser; this is operational guidance, not legal advice.

## Build steps

1. Trigger on a transcript saved for a registered series; anything else stops, no AI call.
2. Duplicate key: occurrence ID; a re-saved transcript replaces only an untouched draft.
3. Scope rule: the register's flag plus a title check for "HR", "disciplinary" and "negotiation"; a match stops before the AI, and the chair deletes the transcript.
4. Read attendees from the meeting, never the transcript.
5. AI step, no tools, told to list only actions said aloud, never infer an owner or date, and ignore instructions in the transcript; per item it returns action (verb first), owner (spoken name or "unassigned"), due date (as quoted, or blank), time stamp, quoted line, and status ("agreed" or "discussed, not agreed").
6. Rules: each time stamp exists, its owner named or speaking there; absent owners become "unassigned"; unquoted dates are dropped; over two items on a line are flagged; "by Friday" is dated by rule, "next week" left to the chair.
7. Write items as "proposed", linked to their lines, and send the chair and backup the link, due by the end of the next working day.
8. Unverified by then: mark it "expired" and tell Tom; the chair or backup types the actions in.
9. AI error after two retries: the chair writes the list from the read-back.

## AI steps

- Step 5 returns, per item, `action`, `owner`, `due_date`, `time_stamp`, `quoted_line` and `status`: [`prompts/propose-actions.md`](prompts/propose-actions.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Lists expire unreviewed | Weekly expired count per series | Tom changes the backup |
| No transcript | Daily check per ended meeting | Chair uses the read-back |
| Approved item wrong | Tom's Friday spot check | Chair corrects; Owen adds a case |

## Variations

Smaller: no AI; the chair types actions in during the read-back.
Larger: one register per department, its chairs and backups named on the card.
Different system: Google Workspace Studio fits steps 1 to 7 in its 20-step limit; its AI steps count against Workspace AI usage limits, as of October 2026.

## Source

*AI Workflows That Run the Business*, Chapter 14, recipe R14.1. Pattern diagram: Figure 14.1 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
