# Six-minute live demo and two-minute Q&A

Status: PREPARED ONLY. Nothing here was executed. Based on [official demo guidance](../reference/common/DEMO-GUIDE.md) and all six [Scenario2 required demonstrations](../reference/SCENARIO.md#required-demo-scenarios). Presenter: set168111, solo, with disclosed Codex/ChatGPT assistance and supplied-kit credit. No teammate, peer pass, instructor approval or solo exemption is implied.

Before a separately authorized demonstration: peer fresh-clone preflight is still outstanding; authorize the API budget; preserve any current simulator evidence before the destructive simulator-only reset; prepare tabs for UI, README diagram/scorecard, Sources and /admin/tickets. Set readable font/notifications off. Keep a real video backup when one has actually been made. Commands are in [demo-commands.txt](demo-commands.txt); they do not touch SQLite/ledger, and none was run to write this script.

| Time | Demonstration/action | What to say/show |
|---|---|---|
|0:00-0:40|Problem, actual UI and architecture.|"I am set168111. This was solo work: I directed/reviewed AI-assisted implementation and manually validated fixes. Support chooses reads/drafts; Reviewer checks grounding. SQLite preserves context and exact actions; code alone commits approved writes through MCP."|
|0:40-1:25|Tariq: vagueVPN then NX-781/old-guide follow-up below.|Show the targeted question, minimum5.4 versus recommended5.4.2, and KB-002 Sources without KB-001. Explain that the4.8 guide is deprecated, rather than inventing a model statement if it does not explicitly use that word. Covers grounded answer, follow-up and document conflict.|
|1:25-2:35|Fadi Finance prompt below. Show security/P2 draft, Sources and no write before approval; approve during authorized demo.|Display the real returned ID and its /admin/tickets record. Do not promise IT-2001 in advance. Say: "The employee has not tried troubleshooting; Finance policy requires direct escalation. That is recorded truthfully. Approval is separate from drafting."|
|2:35-3:00|Omar unknownCRM prompt below, in a new chat.|Show no documented fix/offer to escalate, with no fabricated troubleshooting and no ticket. Covers not-in-KB.|
|3:00-4:10|Arm create_ticket503. Noor dock prompt with explicit usable laptop screen below; show hardware/P3 draft, approve during authorized demo.|Show honest failure/no new ID and unchanged simulator ticket count. An earlier Finance ticket can remain: say "no additional ticket," not "zero total tickets." Identify this as the supplemental case, not supplied S2-07. Covers tool failure; rejection is separately verified and need not add another live call.|
|4:10-5:10|Actual category scorecard and lockout before/after evidence.|"The historical run is65/69:22/23,22/23,21/23. S2-07 failed three repeats; OWN-08 had a connection failure and a separate passing retest. Supplemental503 passed1initial+3repeats without replacing S2-07. The repeated-lockout defect failed two offline regressions before, passed afterward, and then passed one targeted live check. Relevant offline checks were95passed/2skipped; manual passes are user-reported."|
|5:10-6:00|Real-versus-simulated table, limitations, course disclosures.|"OpenRouter chat/embeddings and local retrieval/memory are real. Company data, staff and ticket API are supplied fiction. S2-07 expects hardware/P3 but omits required policy facts; its clarification remains. Provider outages, asserted identity and single-process SQLite remain limits. Peer preflight, registration/DESIGN review/check-ins are unverified; solo work conflicts with the written pair rule unless separately accepted."|

Paste-ready interactions (New chat/change requester between people):

1. tariq.hamdan@nakhla.example: `My VPN will not connect from home.` Then: `The code is NX-781. I have version 5.1 and the old VPN guide says 4.8 or later is supported.`
2. fadi.mansour@nakhla.example: `My Finance FIN-SECURE VPN shows NX-403. I have not tried troubleshooting. Please prepare the required Security Operations escalation.`
3. omar.farah@nakhla.example: `The NakhlaCRM mobile app shows error CRM-1150 every time it syncs my contacts. How do I fix it?`
4. noor.barakat@nakhla.example: `My Nakhla Dock D3 does not detect my monitors. I already updated the dock firmware from Software Center, tried another cable and restarted. I can continue working using the laptop screen. Please open a ticket.`

The timetable uses verified behaviors; this exact assembled demo sequence has not been rehearsed. Do not claim a rehearsal pass. These future live calls are presentation steps, not a request to repeat already passed acceptance tests now. If a dependency fails, describe it honestly and show explicitly labelled preserved evidence; a fallback is not a live pass.

## Two-minute Q&A prompts

- Why two roles? Support makes read/draft decisions; Reviewer independently checks evidence/completeness with one correction. [agent.py](../app/agent.py)
- What prevents unauthorized writes? The model cannot select writes; immutable payload/hash/actionID and explicit approval control MCP creation. [approvals.py](../app/approvals.py), [storage.py](../app/storage.py)
- How does current policy win? Metadata eligibility and source/department precedence run in code after retrieval. [retrieval.py](../app/retrieval.py), [helpdesk_policy.py](../app/helpdesk_policy.py)
- Cost/reliability? Read the actual ledger before the future demo. The historical suite has one unknown billed call, so no exact suite-average cost is claimed. The latest recorded lockout run cost$0.00583914; its ledger is a snapshot, not a guarantee of today's balance. [ledger](../evidence/repeated-lockout-2026-10-26/live-ledger-after.json)

After an authorized demo, clear only its armed faults as appropriate; do not erase evidence or spending. Final video/public URL/tag/submission remain separate authorized human delivery steps. No demo date or instructor approval is invented.
