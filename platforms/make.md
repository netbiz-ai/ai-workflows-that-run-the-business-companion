# Make

Checked 2026-10-12.
Make publishes no version numbers; build notes are stamped with the cloud service and plan.

## Billing and plans

| Item | As of October 2026 |
|---|---|
| Billing unit | Credits, which replaced operations on 2025-08-27 |
| Plans at 10,000 credits a month | Core $10.59, Pro $18.82, Teams $34.12 billed monthly; or $9, $16 and $29 a month billed annually; Free 1,000 credits |
| Module costs | Most module actions 1 credit; Router and error-handler modules none; Make Code 2 credits per second of run time; some AI Content Extractor modules 2 or 10 credits |
| Empty polls | A check that finds no new data still uses 1 credit; a 15-minute schedule can burn more than 600 credits a week with no output |

## AI usage

- Make's AI Provider, available on all plans, bills credits per token, input and output separately, since 2026-08-25, plus 1 credit per operation.
- Small and Medium tiers (GPT-5 nano) give 18,080 input or 2,260 output tokens a credit; the Large tier (GPT-5 mini) 3,616 input or 452 output.
- Named-model rates include Claude Haiku 4.5 at 904 input or 181 output tokens a credit; Make states its rates are subject to change.
- With your own API key, only operations are billed, and the provider bills the tokens.
- Maia, Make's assistant, bills credits per reply by complexity, with no published tokens-per-credit rate.

## History, versions and moving a build

| Item | As of October 2026 |
|---|---|
| Execution logs | Free 7 days; Core, Pro and Teams 30 days; Enterprise 60 days; full-text log search from Pro |
| Versions | Kept 60 days; "Save as version" with descriptions since 2026-10-07; no Git and no native environments |
| Export | Blueprints are JSON under 2 MB; connections are not included |
| Audit | Audit logs and company single sign-on are Enterprise only |

## Errors and switch-offs

- Error handlers were renamed on 2026-05-26: Break is now Retry, and Ignore is now Skip; Resume, Commit and Rollback are unchanged.
- A scenario started by a webhook is disabled after one error; other scenarios after three consecutive errors.

## Data regions and AI

- Make holds ISO 27001 and SOC 2 Type II.
- An EU data zone does not keep all AI processing in the EU: Maia, web search and OpenAI models go to the US.

## MCP exposure

- Make offers an MCP server, with MCP toolboxes since February 2026; allowlist the scenarios a client may call.

## What to watch

- AI Agents (a new app) and Grid are in Beta; the Human in the Loop app is Enterprise only, in closed beta.
- Not yet confirmed: Grid's plan tier, credit rates for the models added on 2026-10-09, and any announcements from Make Waves after 2026-10-19.

## Source

*AI Workflows That Run the Business*, Appendix B.
