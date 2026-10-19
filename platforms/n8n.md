# n8n

Checked 2026-10-12.
Stable release 2.42.7; beta 2.43.4; the 1.x line is still patched (1.123.84, released 2026-10-08).

## Billing and plans

| Item | As of October 2026 |
|---|---|
| Billing unit | One execution: one full run of a workflow, however many steps it has |
| Cloud plans, billed annually | Starter €20 a month (2,500 executions); Pro €50 (10,000); Enterprise custom; unlimited users |
| Self-hosted | Community Edition free under the Sustainable Use License (internal business use allowed; reselling or white-labeling not); Business €667 a month (40,000 executions), self-hosted only |
| Currency | The pricing page shows USD to some visitors ($20, $50 and $800); the book quotes EUR |

## What counts as an execution

- Only production executions count: runs started by triggers, schedules or polling.
- Runs started from the editor while testing do not count.
- A sub-workflow call counts only the parent execution.
- A polling trigger counts only when it finds new data; a Schedule Trigger counts every time it fires.
- The Cloud limit is the instance's monthly total across all workflows, reset at the start of each month, not on the bill date.

## AI usage on Cloud

- Assistant credits (preview) are included: Starter 1,600 a month, Pro 4,000 or 9,600 by plan size; they refresh monthly with no rollover.
- Gateway credits (2.36.0 and later, Cloud Starter and Pro only) are an optional prepaid balance for using OpenAI, Anthropic, Gemini and other models without your own API key, billed per request at n8n's listed rates; top-ups expire after 12 months.
- Nodes can still use your own API key credential, which is how the book's cost lines are modeled.

## History, versions and moving a build

| Item | As of October 2026 |
|---|---|
| Saved executions on Cloud | Starter 2,500 executions, 2.5 GB or 7 days; Pro 25,000, 25 GB or 30 days; Enterprise 50,000, 50 GB, no day limit; pruned oldest first at whichever limit is hit first |
| Workflow history | Starter 1 day, Pro 5 days, Enterprise 365 days or more |
| Environments | Git environments from the Business plan, which is self-hosted only; on Cloud, multiple environments need Enterprise |
| Secrets and log streaming | External secret stores, log streaming and custom roles are Enterprise only |
| Export | Workflow JSON holds credential names and IDs, not secrets, but an HTTP step built from a pasted cURL command may keep a working authentication header; `.n8np` packages are recommended for moving workflows between instances |
| Backups | n8n backs up Cloud data daily, encrypted, replicated to a separate region in the same country; the retention period is not stated |

## Errors and switch-offs

- Error workflows start from an Error Trigger; steps offer Retry On Fail and an On Error setting to continue or take an error output.
- The Remove Duplicates node can drop items processed in previous executions; in the book it sits behind the key log, never instead of it.
- No n8n rule for switching off a failing workflow is confirmed; check your own instance.

## Data regions and AI

- n8n Cloud is hosted on Azure in Frankfurt; n8n states SOC 2 alignment and publishes a SOC 3 report.
- Where an AI step's model runs is set by the model provider you call, not by n8n's hosting region; state both on the governance card.

## MCP exposure

- n8n has an instance-level MCP server, and from 2.36 new workflows can be exposed to it automatically.
- Check the setting before the first workflow goes live, and allowlist workflows one by one (book Chapter 3).

## What changed, and what to watch

- 2.0 renamed Activate to Publish: saving no longer deploys a workflow; click Publish.
- 2.0 also moved Code nodes to isolated task runners, blocked environment variables in Code nodes, disabled the ExecuteCommand and LocalFileTrigger nodes, dropped MySQL and removed the Start node.
- Human approval for AI tool calls arrived in 2.6.0; a Guardrails node checks for jailbreak attempts, personal data, secret keys, URLs and keywords; Evaluations run sets of test cases.
- Security: CVE-2025-68613 (CVSS 9.9) was added to the US CISA Known Exploited Vulnerabilities catalog in March 2026; CVE-2026-21858 ("Ni8mare") scored CVSS 10; on 2026-10-01 n8n published 14 advisories, including a bypass of the Send-and-Wait approval step.
  A self-hosted instance needs a patch window measured in days (book Chapter 17).
- Not yet confirmed: how long Cloud backups are kept, whether `.n8np` packages carry credential data, and whether Gateway credit rates carry a markup.

## Source

*AI Workflows That Run the Business*, Appendix B; the switch-off line is from Chapter 16.
