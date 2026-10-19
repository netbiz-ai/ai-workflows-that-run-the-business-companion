# Platform cards

One card per platform from the book's Appendix B, each headed with the date its facts were checked.
Each card summarizes one platform as it stood on that date, from the vendor pages listed in the book's References.
Prices, plan gates, limits and feature names change often, and several changed during 2026.
Treat every row as "as of" its check date, recheck the vendor's own page before any price or plan decision, and rerun the golden set after any change a card warns about.

The cards follow the same order: what you pay for and what counts against it; history, versions and moving a build; errors and switch-offs; data regions and AI; MCP (Model Context Protocol) exposure; and what to watch.

| Card | Checked |
|---|---|
| [n8n](n8n.md) | 2026-10-12 |
| [Make](make.md) | 2026-10-12 |
| [Zapier](zapier.md) | 2026-10-12 |
| [Microsoft Power Automate with Copilot Studio](power-automate.md) | 2026-10-12 |
| [Google Workspace Studio](google-workspace-studio.md) | 2026-10-12 |
| [Activepieces](activepieces.md) | 2026-10-12 |
| [Integration platforms near 150 to 250 people](integration-platforms.md) | No facts checked; a quote checklist |
| [AI model prices behind the cost lines](ai-models.md) | 2026-10-12 |

When a card is rechecked, update its check date and every row that changed, and record any change that affects a recipe in `CHANGELOG.md`.

## Platform changes in 2026 that the book relies on

| Date | Change | Where it matters |
|---|---|---|
| 2026-05-26 | Make renames Break to Retry and Ignore to Skip | Every Make error handler (book Chapter 16) |
| 2026-08-25 | Make prices AI Provider tokens separately for input and output | Make cost lines with AI |
| 2026-08-31 | Power Automate mobile app removed | Test where approvers will answer before go-live (book Chapter 11) |
| By 2026-09-14 | Relay.app shuts down and deletes accounts | Exit planning (book Chapters 1 and 17) |
| 2026-10-01 | n8n publishes 14 security advisories | Patch windows (book Chapter 17) |
| 2026-11-01 | New and renewed Power Automate Premium licenses carry no AI Builder credits; Workspace Studio AI limits enforced | Power Automate and Workspace Studio cost lines |
| 2026-11-30 | OpenAI Agent Builder shuts down | Exit planning (book Chapters 1 and 17) |
| February 2027 | Unlicensed users blocked from Managed Environments | Power Automate environments (book Chapter 3) |

## Source

*AI Workflows That Run the Business*, Appendix B.
