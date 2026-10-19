# Governance card: <recipe ID> <name>

Fill in one card per workflow before it is built, and get the owner's approval before it goes live.
An entry passes review when it gives a name, a number or an action instead of a category: a team cannot be asked why.
Update the card whenever the workflow's data, people, platform or plan changes.
Keep each workflow's card and runbook together, beside its golden set, in the folder your recipe library points to.

Workflow: <recipe ID and name>. Owner: <the business person who answers for its output>. Review date: <the next date the owner reviews it, usually the annual library review>.

| Field | Entry |
|---|---|
| Data class | |
| Approver | |
| Access | |
| Logging | |
| Kill switch | |

## What each field needs

| Field | Write here | Passes review when it |
|---|---|---|
| Data class | The most sensitive data the workflow touches, in your company's own classes; the hosting region; the AI-processing region, written separately | Names the class and both regions, or says "no AI" |
| Approver | The person who approves each consequential output, and the person who approves the monthly spend | Gives a name for each, not a team |
| Access | Each service account and its permissions; who may edit the workflow; which MCP clients may call it, read-only or write | Lists every account and every editor; says "no MCP client" if none |
| Logging | What is kept, where and for how long: run history, decision log, key log; what is never kept | Gives a number of days or months for each log |
| Kill switch | How to stop it; two people who can; where work waiting or in flight lands | Names both people and the landing place, and has been tested |

## Questions to answer before you sign

- If the AI step returns nonsense, which rule stops it before anything changes?
- Which output reaches a customer, moves money, changes an employee record or deletes a record, and who approves it first?
- Could the process owner stop the workflow tonight without calling the builder?
- If the run history expired tomorrow, could the decision log and key log still answer "what happened to item 4417"?
- Does the card still match the plan the workflow runs on, including its log retention?

## Testing the kill switch

Before go-live, on the development copy:

1. Start the copy with one item mid-run.
2. Stop it with the kill switch, exactly as the card describes.
3. Check that waiting items and the interrupted item land where the card says.
4. Restart it, and check that nothing is processed twice; the key log should show the interrupted item handled once.
5. Record whether items that arrived while it was stopped were held; a mailbox keeps them, and a webhook may not.
6. Have the second person on the card confirm, with their own login, that they can reach the production switch.

A copy test proves the procedure, not the access, so step 6 is not optional.

## Filled examples

Every recipe folder holds Northstar's filled card as `recipes/<recipe ID>/governance-card.md`, and the book's Chapter 3, Example 3.1, shows the card for R7.1.
Read two or three of them before writing your first.
Northstar Home & Appliance is fictional; copy the structure, not the entries.

## Source

*AI Workflows That Run the Business*, Appendix C, and Chapter 3.
