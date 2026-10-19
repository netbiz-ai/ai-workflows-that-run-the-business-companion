# Pattern: webhook authentication

Use it on every recipe a webhook starts.
It is tool-neutral; some platforms offer these checks as settings, and elsewhere each is an early step in the workflow.

A webhook address is a door: anyone who learns it can knock, and by default the workflow behind it does whatever the knock asks.
Addresses leak, into exported workflow files, forum screenshots and old contractors' notes, so check every request first.

## The checks, in order

1. **The secret comes first: it is the only check that proves who is calling.**
   The sender includes a shared secret with every request or, better, signs each request with it, proving the content was not changed.
   It goes in a header over https, never in the address, the part that leaks; where a platform's address is itself the credential, treat the whole address as secret.
   A signature does not stop a captured request being resent: where the sender signs a timestamp, reject old requests, and let the [duplicate-safe write](../duplicate-check/README.md) make resends harmless.
2. **Then narrow the field.**
   Where the vendor publishes its sending addresses, follow its maintained list, not a copy; where there is none, skip this rather than guess.
3. **Check the shape.**
   Set the largest payload the job genuinely needs, and check every expected field before any step uses it; a step expecting an order ID should get nothing else.
4. **Log the rejection, not the content**, because the payload may carry personal data.
   Log each rejection's time, source and reason, never its payload.
5. **End a rejected run cleanly** with a logged reason, not with an error.

Keep the secret in the platform's credential store, one secret per webhook, and rotate it when someone with access leaves (book Chapter 3).

A webhook that never arrives looks like a quiet day, so pair an instant trigger with a nightly check of the source's new records against the workflow's (see [`monitoring/`](../../monitoring/README.md)).

## Checklist: securing a webhook

- [ ] Require a secret, or better a signature, in a header over https, and reject a request without one before any other step.
- [ ] Allow only the vendor's published sending addresses, where it keeps a list.
- [ ] Set the largest payload the job genuinely needs.
- [ ] Check every expected field before any step uses it.
- [ ] End a rejected run cleanly with a logged reason, not with an error.
- [ ] Log each rejection's time, source and reason, never its payload.
- [ ] Keep one secret per webhook, in the platform's credential store.
- [ ] Send every write through the duplicate-safe write.

## Platform note, as of October 2026

Checked 2026-10-12; see the [Make card](../../platforms/make.md).
On the Make platform a scenario started by a webhook is disabled after one error.
So a rejection must never be an error: route a failed check to a step that logs the reason and ends the run.

## Source

*AI Workflows That Run the Business*, Chapter 2, Checklist 2.1.
