# Zapier

Checked 2026-10-12.
Zapier publishes no version numbers; build notes are stamped with the cloud service and plan.

## Billing and plans

| Item | As of October 2026 |
|---|---|
| Billing unit | Tasks: each action step that runs uses tasks; triggers and polling checks never do |
| Plans | Free 100 tasks, pausing at the limit; Professional $19.99 a month billed annually or $29.99 monthly for 750 tasks; Team $69 billed annually or $103.50 monthly for 2,000 tasks, 25 users, single sign-on and audit logs; Enterprise custom, with an annual task limit |
| Overage | Pay-per-task at 1.25x on annual plans and 2.5x on monthly plans; Zaps pause at 3x the subscription's tasks |
| Free steps | Filter, Paths, Formatter and Delay use no tasks; an MCP call uses 2 |

## AI by Zapier

- An AI step uses 1, 3 or 5 tasks by model tier (Standard, Advanced or Premium), plus the same again for each tool call, so a Premium step with two tool calls uses 15 tasks.
- New steps on paid plans default to Premium; set Standard where the recipe allows it.
- Your own API key bills at 1x; billing is per task, not per token.
- The Auto setting defaults to Claude 4.5 Haiku on the Advanced tier and Claude 4.6 Sonnet on Premium.
  Choose a named model rather than Auto where you can, so any switch is your change (book Chapter 17).

## History, versions and moving a build

| Item | As of October 2026 |
|---|---|
| Zap history | 29 to 69 days by default on all plans; Enterprise admins can set 7 to 30 days |
| Versions | Drafts on all plans; version history none on Free, 1 month on Professional, 6 months on Team, 1 year on Enterprise; roll back by drafting from a past version |
| Environments | No development and production environments are described; use a copy (book Chapter 3) |
| Export | JSON export and import on Team and Enterprise only; templates shareable on all plans |
| Audit | Audit log on Team (past 6 months) and Enterprise (past 12 months) only |

## Errors and switch-offs

- Custom error handlers route a failed step.
- Autoreplay (Professional, Team and Enterprise) replays an errored step up to five times, at 5 minutes, 30 minutes, 1 hour, 3 hours and 6 hours, the last about 10 hours 35 minutes after the error; manual replay is on all plans.
- Autoreplay is set per Zap or account-wide, never per step, so turn it off on any Zap whose step writes to a system of record (book Chapters 2 and 16).
- A Zap is turned off when 95% of its runs fail over 7 days.

## Data regions and AI

- Zapier data sits in AWS us-east-1, and Zapier is not HIPAA compliant.
- AI subprocessors are listed in the US, with Meta also in several other countries; Zapier states no training on customer content and zero data retention with OpenAI, and no EU AI-processing option.
- The subprocessor list does not say which provider or region serves a given AI by Zapier step.

## MCP exposure

- "API by Zapier" is not governed by Zapier's app access controls; review that route separately from your MCP allowlist.

## What to watch

- Zapier Agents are migrating into AI by Zapier steps in Zaps, with no shutdown date yet.
- Human in the loop (Request Approval, Collect Data) is available from Professional.

## Source

*AI Workflows That Run the Business*, Appendix B; the Autoreplay scope line is from Chapters 2 and 16, and the named-model line from Chapter 17.
