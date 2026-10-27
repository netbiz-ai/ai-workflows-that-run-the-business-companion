# AI Workflows That Run the Business: companion repository

The working counterpart to *AI Workflows That Run the Business: Governed Automation Recipes for Companies of 10 to 250 People* by Elvis Tafoh-Ngunjoh (Tafoh Publishing, 2026), Book 2 of the AI-Native Business Series.
It holds the files you would otherwise type from the page: for each of the book's 40 recipes, the tool-neutral build specification, the governance card, the golden set and the text of every bounded AI step.

The book is the reference.
Every recipe here follows the book's anatomy and rule: AI drafts, rules check, people approve, logs remember.

## Status

| Part | Status |
|---|---|
| Build specifications, governance cards, golden sets, prompts (all 40 recipes) | Available |
| Platform cards, patterns, governance templates, golden-set method, monitoring, recipe library | Available |
| n8n builds (all 40 recipes), each run against its golden set | Available |
| Make builds | The 15 recipes with no AI step and R4.1 available, each run against its golden set; the other 24 recipes with an AI step not yet available |
| Power Automate and Zapier builds | Not yet available |

Each recipe's `build-spec.md`, each prompt file and the index below say when its golden set last passed.
`CHANGELOG.md` records every change, dated.

## Using an n8n build

1. Create the three tables in a Postgres database your n8n can reach: `patterns/duplicate-check/schema.sql` (the key log, decision log and exception queue).
2. Import `recipes/<ID>/n8n/workflow.json` into n8n (2.42.7 or later) and connect two credentials: your Postgres database and, for a recipe with an AI step, your Anthropic API key.
3. Open the **Config** node and replace every `<your ...>` value: your systems' addresses, your limits, lists and people. Nothing else in the workflow hard-codes them.
4. Each system call is an HTTP Request node named for the system and action; point it at your system's API, or replace it with your system's own n8n node, keeping its name and its error output.
5. Create the stop list `stop_flag_url` points at, returning `{"stopped": false}`; set it to `true` to stop the workflow (book Chapter 3).
6. Run the recipe's golden set with your own data before go-live, and publish only when the governance card is filled.

The builds were tested against stand-in systems (`tools/mock-systems/`), not against any vendor's live service; `tools/README.md` shows how to rerun a golden set yourself.

## Using a Make build

1. Create the three tables (`patterns/duplicate-check/schema.sql`, which includes the `reserve_key` function) and put a table API in front of them that Make can reach over HTTPS, such as PostgREST. Make runs in Make's cloud, so it cannot open a connection to a database inside your network.
2. In Make, create a scenario for each blueprint in `recipes/<ID>/make/` and import it (**...** menu, **Import Blueprint**). `blueprint.json` starts on the recipe's event; a second file such as `backstop.blueprint.json` is the recipe's scheduled step, and the build note at the top of its Config step says when it runs.
3. On the webhook step, create a webhook and point your system at its address; for a scheduled scenario, set the schedule.
4. Open the **Config** step and replace every `<your ...>` value, including `table_api_url` and `stop_flag_url`. Nothing else in the scenario hard-codes them.
5. Each system call is an HTTP step named for the system and action. The blueprint carries no authentication: add your API's (a keychain or an Authorization header on each step), or replace the step with your system's own Make app, keeping its name and its error route.
6. For a recipe with an AI step, create an HTTP **API key** connection in Make for your Anthropic API key (parameter name `x-api-key`, in the header; allowed origin `https://api.anthropic.com`) and choose it on each **AI call** step. Make keeps the key encrypted; the blueprint carries none.
7. Turn on **Allow storing of incomplete executions** if Make has not kept it from the blueprint: the reads' Retry handlers need it.
8. Create the stop list `stop_flag_url` points at, returning `{"stopped": false}`; set it to `true` to stop the scenario (book Chapter 3).
9. Run the recipe's golden set with your own data before go-live, and publish only when the governance card is filled.

Make switches a webhook scenario off after one error (book Chapter 16), so watch the scenario's history in the first weeks.

## Before you import anything

- Read the recipe's governance card and fill in your own before the build (`governance/governance-card.md`).
- Build in a development copy, never in production (book Chapter 3).
- Connect your own service accounts; nothing here carries working credentials.
- Run the golden set with your own data before go-live (`golden-sets/README.md`).

## Layout

| Path | What it holds |
|---|---|
| `recipes/R4.1/` to `recipes/R15.3/` | One folder per recipe: `build-spec.md`, `governance-card.md`, `golden-set.csv`, `prompts/` |
| `platforms/` | Dated platform cards behind the book's Appendix B |
| `patterns/` | Shared building blocks: `duplicate-check/`, `webhook-auth/`, `error-handling/` |
| `governance/` | Blank governance card and runbook templates (Appendix C) |
| `golden-sets/README.md` | How golden sets are written and run (Appendix D, Chapter 16) |
| `monitoring/` | Run monitoring and budget alerts (Chapter 17) |
| `library/recipe-library.csv` | The blank recipe library (Chapter 18, Appendix A) |
| `CHANGELOG.md` | Every dated change that affects a recipe (generated) |
| `tools/` | The build and golden-set tools behind the n8n and Make builds |

## Recipes

| Recipe | Chapter | Band | Northstar platform | AI step | n8n build |
|---|---|---|---|---|---|
| [R4.1](recipes/R4.1/build-spec.md) Classify and route every incoming message to the right queue | 4 | Starter | Power Automate | Yes | [Tested 2026-10-19](recipes/R4.1/n8n/test-report.md) |
| [R4.2](recipes/R4.2/build-spec.md) Escalate complaints, safety issues and legal threats to a person at once | 4 | Starter | Power Automate | Yes | [Tested 2026-10-19](recipes/R4.2/n8n/test-report.md) |
| [R4.3](recipes/R4.3/build-spec.md) Draft a reply from approved sources for a person to edit and send | 4 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R4.3/n8n/test-report.md) |
| [R4.4](recipes/R4.4/build-spec.md) Summarize a long thread for a handoff or escalation | 4 | Starter | Power Automate | Yes | [Tested 2026-10-19](recipes/R4.4/n8n/test-report.md) |
| [R5.1](recipes/R5.1/build-spec.md) Capture inquiries from web, email and phone notes into one lead record | 5 | Starter | Power Automate | Yes | [Tested 2026-10-19](recipes/R5.1/n8n/test-report.md) |
| [R5.2](recipes/R5.2/build-spec.md) Prepare a research and qualification brief for the salesperson | 5 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R5.2/n8n/test-report.md) |
| [R5.3](recipes/R5.3/build-spec.md) Draft a quote from the current price table only | 5 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R5.3/n8n/test-report.md) |
| [R5.4](recipes/R5.4/build-spec.md) Route quote approval by value and discount | 5 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R5.4/n8n/test-report.md) |
| [R6.1](recipes/R6.1/build-spec.md) Log emails and meeting notes to the right account and deal | 6 | Starter | Power Automate | Yes | [Tested 2026-10-19](recipes/R6.1/n8n/test-report.md) |
| [R6.2](recipes/R6.2/build-spec.md) Remind the owner and draft a follow-up when a quote goes quiet | 6 | Starter | Power Automate | Yes | [Tested 2026-10-19](recipes/R6.2/n8n/test-report.md) |
| [R6.3](recipes/R6.3/build-spec.md) Find likely duplicate accounts and queue them for a person to merge | 6 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R6.3/n8n/test-report.md) |
| [R7.1](recipes/R7.1/build-spec.md) Extract supplier invoice fields into a structured record | 7 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R7.1/n8n/test-report.md) |
| [R7.2](recipes/R7.2/build-spec.md) Match the invoice to the purchase order and delivery receipt | 7 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R7.2/n8n/test-report.md) |
| [R7.3](recipes/R7.3/build-spec.md) Stop and verify any change to a supplier's bank details | 7 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R7.3/n8n/test-report.md) |
| [R7.4](recipes/R7.4/build-spec.md) Run the exception queue with reasons, owners and ageing | 7 | Starter | Power Automate | Yes | [Tested 2026-10-19](recipes/R7.4/n8n/test-report.md) |
| [R8.1](recipes/R8.1/build-spec.md) Send staged overdue reminders that stop on payment or dispute | 8 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R8.1/n8n/test-report.md) |
| [R8.2](recipes/R8.2/build-spec.md) Prepare and send monthly statements for trade accounts | 8 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R8.2/n8n/test-report.md) |
| [R8.3](recipes/R8.3/build-spec.md) Take in a dispute and brief the account owner | 8 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R8.3/n8n/test-report.md) |
| [R9.1](recipes/R9.1/build-spec.md) Run onboarding: accounts, equipment, training tasks and first-week checklist | 9 | Starter | Power Automate | Yes | [Tested 2026-10-19](recipes/R9.1/n8n/test-report.md) |
| [R9.2](recipes/R9.2/build-spec.md) Answer policy questions from approved sources and hand off to HR | 9 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R9.2/n8n/test-report.md) |
| [R9.3](recipes/R9.3/build-spec.md) Take leave requests, check the balance and route to the manager | 9 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R9.3/n8n/test-report.md) |
| [R9.4](recipes/R9.4/build-spec.md) Remove a leaver's access the same day | 9 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R9.4/n8n/test-report.md) |
| [R10.1](recipes/R10.1/build-spec.md) Turn a sale into a complete work order, with restricted fields protected | 10 | Starter | Power Automate | Yes | [Tested 2026-10-19](recipes/R10.1/n8n/test-report.md) |
| [R10.2](recipes/R10.2/build-spec.md) Send delivery confirmations and handle reschedule replies | 10 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R10.2/n8n/test-report.md) |
| [R10.3](recipes/R10.3/build-spec.md) Prepare tomorrow's dispatch briefing, read-only | 10 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R10.3/n8n/test-report.md) |
| [R11.1](recipes/R11.1/build-spec.md) Collect supplier quotes into one normalized comparison | 11 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R11.1/n8n/test-report.md) |
| [R11.2](recipes/R11.2/build-spec.md) Block expired quotes and out-of-policy orders before they are placed | 11 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R11.2/n8n/test-report.md) |
| [R11.3](recipes/R11.3/build-spec.md) Route purchase approval by amount and remaining budget | 11 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R11.3/n8n/test-report.md) |
| [R12.1](recipes/R12.1/build-spec.md) Pull the weekly figures from source systems into one dated table | 12 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R12.1/n8n/test-report.md) |
| [R12.2](recipes/R12.2/build-spec.md) Draft the weekly briefing narrative with a link behind every figure | 12 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R12.2/n8n/test-report.md) |
| [R12.3](recipes/R12.3/build-spec.md) Alert the owner when a measure crosses its threshold | 12 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R12.3/n8n/test-report.md) |
| [R13.1](recipes/R13.1/build-spec.md) Answer staff questions from approved sources, with citations and a refusal path | 13 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R13.1/n8n/test-report.md) |
| [R13.2](recipes/R13.2/build-spec.md) Flag stale documents to their owners and pull expired ones from answers | 13 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R13.2/n8n/test-report.md) |
| [R13.3](recipes/R13.3/build-spec.md) Turn a resolved ticket into a draft knowledge article for the owner to approve | 13 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R13.3/n8n/test-report.md) |
| [R14.1](recipes/R14.1/build-spec.md) Turn a transcript into a draft action list for the chair to verify | 14 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R14.1/n8n/test-report.md) |
| [R14.2](recipes/R14.2/build-spec.md) Create tasks with owners and due dates after verification | 14 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R14.2/n8n/test-report.md) |
| [R14.3](recipes/R14.3/build-spec.md) Chase overdue actions and carry them into the next agenda | 14 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R14.3/n8n/test-report.md) |
| [R15.1](recipes/R15.1/build-spec.md) Draft campaign copy from approved product facts and check every claim | 15 | Growth | n8n Cloud | Yes | [Tested 2026-10-19](recipes/R15.1/n8n/test-report.md) |
| [R15.2](recipes/R15.2/build-spec.md) Check delivery and installation capacity before a promotion launches | 15 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R15.2/n8n/test-report.md) |
| [R15.3](recipes/R15.3/build-spec.md) Keep consent and unsubscribes in sync across every list | 15 | Starter | Power Automate | No | [Tested 2026-10-19](recipes/R15.3/n8n/test-report.md) |

Northstar Home & Appliance is the book's fictional running case; every figure about it is modeled.
Platform facts are dated; recheck the vendor's own pages before you rely on one.
The content is operational guidance, not legal, tax or accounting advice.

## License

MIT; see `LICENSE`. The book itself is not covered by this license.
