# Microsoft Power Automate with Copilot Studio

Checked 2026-10-12.
Microsoft publishes no version numbers for cloud flows; build notes are stamped with the cloud service and the connector tier.

## Licensing

| Item | As of October 2026 |
|---|---|
| Included in Microsoft 365 | Cloud flows with standard connectors, and Approvals |
| Premium | $15 a user a month: premium connectors, the HTTP action and AI steps |
| Process | $150 a flow a month: one solution-aware flow or a flow group of up to 25; needed for premium flows many people start, unattended RPA, or a service-principal owner without a designated licensed user |
| Service accounts | A shared account that owns standard-connector flows needs no extra license; one Premium license on a widely shared account is multiplexing and breaks the license terms; Microsoft recommends an Entra service principal owner |

## Connector tiers used in the book

- Standard: Office 365 Outlook (including "When a new email arrives (V3)"), SharePoint, Approvals, Microsoft Teams and Freshdesk.
- Premium: Dataverse, Zendesk, the built-in HTTP action and HTTP Webhook.
- Not listed: QuickBooks Online and BambooHR have no connector; Xero is available only through third-party premium connectors.
- Not yet confirmed: the tier of the "When a HTTP request is received" trigger.

## AI usage: Copilot Credits

- Copilot Studio sells 25,000 Copilot Credits for $200 a month, or $0.01 a credit pay-as-you-go.
- An AI prompt costs 0.1 credit per 1,000 tokens on the basic model, 1.5 on standard models and 10 on premium models; input includes a hidden Microsoft system prompt of about 1,200 tokens.
- GPT-4.1 mini is the default, basic model; Anthropic models are experimental.
- Content processing (custom documents, invoices, receipts, IDs) costs 8 credits a page or image; OCR 0.1 a page.
- AI Builder actions make a flow premium; testing a prompt in prompt builder is free; unused credits do not roll over.

## History, environments and moving a build

| Item | As of October 2026 |
|---|---|
| Run history | 30 days from run start; solution flows can also keep run records in Dataverse (default 28 days) |
| Audit | Microsoft Purview logs flow creation, edits, deletion and sharing, not runs |
| Environments | Managed Environments need premium licenses, with unlicensed users blocked from February 2027; pipelines need Managed Environment targets from October 2026 |
| Export | A non-solution flow exports as a package .zip; solutions carry flows between environments; what the package leaves out is not stated |

## Errors and switch-offs

- Use Configure run after and Try, Catch and Finally scopes.
- The default retry for an action is not confirmed; check each write action's retry setting on your tenant and turn it off (book Chapters 2 and 16).
- A flow is turned off after 14 days of errors.

## Data regions and AI

- Flows and their data live in the region of the flow's Power Platform environment; changing region needs a support case.
- Generative AI may process prompts outside that region when "Move data across regions" is on: Europe then uses Azure OpenAI in the EU Data Boundary; the UK stays in region or the EU; Canada, Brazil, Japan, Korea, South Africa and the UAE go to the US; Bing search always runs in the US.
- EU "flex routing" at peak load is on by default for eligible tenants created after 2026-03-25.

## MCP exposure

- Copilot Studio agents can use MCP servers as tools, through Power Platform connectors, so data policies govern that access.
- Microsoft's MCP catalog lists no server that exposes Power Automate flows.

## What changed, and what to watch

- From 2026-11-01, new and renewed Premium licenses carry no AI Builder credits, and AI steps draw on Copilot Credits; no AI Builder credit packs have been sold since 2025-11-01 (book Chapter 17).
- The Power Automate mobile app was removed on 2026-08-31.
- Not yet confirmed: HIPAA coverage, and the license gate for MCP tools in Copilot Studio beyond its normal credits.

## Source

*AI Workflows That Run the Business*, Appendix B; the retry line is from Chapters 2 and 16.
