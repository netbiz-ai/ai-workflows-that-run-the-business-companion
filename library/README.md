# The recipe library

`recipe-library.csv` is the blank recipe library: one complete row per live workflow, so every workflow can be found, explained, costed and switched off by someone other than its builder.
It holds the header row only; add a row for each workflow the day it goes live.
Start it from the book's Appendix A recipe index: copy the rows you will build, then fill in every column for each.

Give the library the controls it asks of each workflow: an owner, usually the cost approver, who with the builder is its only editor; backups; and a change record.
Write the monthly upkeep budget in hours, agreed by the builder and the cost approver, at the top of the library, or beside the file if your tool has no place for it.

## The columns

The example is Northstar's bank-detail check, R7.3; Northstar Home & Appliance is fictional and its figures are modeled.

| Column | What to record | Example: R7.3 at Northstar (modeled) |
|---|---|---|
| Workflow ID and name | Its ID, and the job in business words | R7.3 Stop and verify any change to a supplier's bank details |
| Process | The business process it belongs to | Supplier payments |
| Feeds or is fed by | Workflows and systems that send it work or use its output | Feeds R7.4's exception queue |
| Owner | The business person who answers for its output | Aisha Karim |
| Builder | The person who can change it | Owen Clarke; the outside IT provider's engineer as second |
| Platform and version | Where it runs, and the version or plan it was last tested on | Microsoft Power Automate cloud flows (Microsoft 365 license); documentation checked 2026-10-12; tested before go-live |
| Band | Starter, Growth, or Advanced | Starter |
| Governance card | Where the current card is kept | Northstar's recipe library folder, beside the runbook |
| Golden set | Where it is kept, and the date it last passed | Same folder; last pass before go-live, and after every change |
| Monthly cost line | Units and money, at the stated volume | Standard connectors, $0 new spend as of October 2026; no AI |
| Upkeep | The builder's hours a month for golden-set reruns, change reviews and faults | *Modeled:* about 1 hour a month; no AI step |
| Hours saved | Hours a month, net of review time, labeled capacity or cash | None claimed; it closes a fraud route |
| Review date | The next date the owner reviews it | Annual library review |
| Status | Live, paused or retired, with the date | Live |

## Rules for the entries

- **Owner** is a business person who is not the builder.
  Where the builder must own a workflow for now, a named business approver signs off its output and review, and the entry names them.
- **Upkeep**, the part of your month already spoken for, comes from the decision and change logs, not memory.
  *Estimate:* a stable workflow with a good runbook needs an hour or two a month; one with an AI step or a fragile connection needs more.
- **Hours saved** is the run count from the decision log times a timed sample of the manual task, less review time, confirmed by the owner.
  Label it capacity unless a saving is realized, such as a hire not made.
  A workflow that saves no hours but prevents a loss says so.
- **Status** "retired" also records the date, the reason and what replaced it.
- Add up the upkeep of everything live and compare it with the agreed upkeep budget; a new workflow whose upkeep pushes the total past it waits until something is retired or simplified.

## Using the file

Open `recipe-library.csv` in any spreadsheet tool, or import its header row into a SharePoint list or table; keep the column names exactly as they are.
Fields that contain commas go in CSV double quotes.
Review every row at the annual library review (book Chapter 18), ending with keep, change, pause or retire for each workflow, and record who decided.

## Source

*AI Workflows That Run the Business*, Chapter 18 (Table 18.1, Worksheet 18.1) and Appendix A ("From the index to your recipe library").
