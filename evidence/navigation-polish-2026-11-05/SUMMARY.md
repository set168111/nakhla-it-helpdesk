## Navigation and Updates polish - 5 November 2026

Active working app/UI: public video/presentation/health/Updates links are grouped;
admin links have a bordered separate-login label. Admin navigation opens safe
new tabs, while sign-in/sign-out actions remain in their tab. Protected account
guidance distinguishes employee and demo-admin passwords, with a fixed Employee
sign-in link. The red instructor note references the developer's private WhatsApp
handoff without a password or personal contact details.

[Updates since the live demo](../../docs/updates-since-demo.md) is served by the single fixed
`/demo/updates` route, without exposing any directory. It lists source/evidence-
checked improvements and current limitations (per-ticket cost unavailable, snippet
clarification sometimes unhelpful, historical65/69 unchanged). No comprehensive
security certification or new full-suite acceptance is claimed.

37 focused offline tests and 65 isolated existing-browser checks passed, including
320/360px layout, safe new tabs, same-tab auth, protected access, usage and table
regressions. Tests used synthetic credentials/stub responses and no provider call.
Both images were built offline and all layers/config scanned; running source,
health/auth/media/isolation and retained records/pending actions/tickets were verified.
The simulator was not recreated. No real login/approval/ticket creation was tested.

No new commit, push, tag or release is part of this polish. Case19's earlier
user-verified pass and incomplete/deferred Case20 are unchanged.
