# Recovery runbook: <recipe ID> <name>

The governance card says how to stop a workflow; the runbook says how to find what failed, finish the work safely and prove the workflow healthy.
Write it for the second person, who did not build the workflow, and test it by having them read it cold.
"Check the usual place" is not a runbook.
Keep it beside the workflow's governance card and golden set.

## 1. People

- Owner:
- Builder:
- Second person, who can follow this runbook without the builder:
- Who may turn the workflow back on:

If any line is empty, record the gap on the governance card.

## 2. Stop it

Copy the stop steps from the card's kill switch, word for word, with where to find the switch and which login reaches it.

## 3. Find the failed work

- The key log: where it is, and how to filter it for keys marked "in progress" or "failed".
- The exception queue: where it is, and who works it.
- The platform's run history: where it is, and how many days it keeps (each platform's window is on its card in `platforms/`).

Look in the key log and exception queue first: run history expires, often before anyone asks.

## 4. Decide what is safe to replay

- Which items may be replayed, and from which step.
- Which items must never be replayed without checking the system of record first, such as any write that timed out and may still have succeeded.
- How to check each item against the key log before replaying it (see `patterns/error-handling/` for what to do with each key state).

## 5. Do the work by hand

Name who does the work while the workflow is off, and how, in a sentence a stand-in could follow.
Switching a workflow off does not switch the work off.

## 6. The platform's switch-off rule

Write down when this platform turns a failing workflow off by itself (book Chapter 16 and the card in `platforms/`), and what the monitor will show when it does.

## 7. Recovered means

- The golden set passes on the fixed version.
- The exception queue is worked, or handed over with a name and a date.
- A person checks the first live items after the restart.

## 8. After the incident

- Two sentences: what failed, and what fixed it.
- The golden-set case that would have caught it, added and passing.
- Any change to the card, approved by the owner.

## The stack decision record

One row per workflow keeps the stack decision from the book's Chapter 1 next to the card.

| Field | Write here |
|---|---|
| Workflow | Recipe ID and name |
| Tier and band | Suite automation, one general platform, or an integration platform; Starter, Growth or Advanced |
| Platform and owner | Where it runs, and who owns the account |
| Monthly cost | The modeled cost in the platform's own unit and in money, at a stated volume, with an "as of" date |
| Self-hosting | No, or yes with the named person who patches it and the patch window |
| Exit route | What exports, what does not, and the checked date |
| Review date | When the decision is looked at again |

An optional line records build and upkeep hours, which are capacity, not cash.

## Source

*AI Workflows That Run the Business*, Appendix C, and Chapter 16, Checklist 16.1.
