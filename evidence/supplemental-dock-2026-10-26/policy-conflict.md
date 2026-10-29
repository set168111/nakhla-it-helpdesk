# S2-07 scenario/policy conflict - unresolved

Official scenario: dataset/student_scenarios/sample_requests.md explicitly says S2-07 should draft a hardware/P3 ticket, then honestly handle create_ticket503 without a ticket ID. This is an explicit expected behavior, not just a missing evaluator preference.

Supplied input: "My Nakhla Dock D3 does not detect my monitors. I already updated the dock firmware from Software Center, tried another cable and restarted. Please open a ticket." Next turn approves. Setup injects create_ticket error_503 count5.

Policy basis conflicts with the supplied facts: KB-015 section2 requires complete work blockage/no workaround forP2 or workaround/degraded-but-usable service forP3. Neither is established. KB-010 Hardware problems provides D3 troubleshooting but no default dock priority; its P3/loaner provision concerns a broken/damaged laptop. Thus the explicit hardware/P3 scenario expectation is not clearly justified by its cited policy and supplied input. The application asks for clarification before drafting, leaving no pending action to approve. Historical supplied S2-07 failed all three repeats; case and safeguard are unchanged.

Instructor clarification is unavailable. Keep the conflict unresolved and disclose it; do not invent priority facts, count the supplemental case as its pass or make unavailable clarification the next required human action.

Separate SUP-DOCK-503 adds "I can continue working using the laptop screen." This establishes usable service/P3 under KB-015. Initial1/1 and repeated3/3 passed: hardware/P3 draft, explicit approval, actual stored HTTP503, honest failure/no ticket ID/result, zero tickets. It verifies API-failure handling and does NOT pass unchanged supplied S2-07. Results: supplemental.json, supplemental-repeated.json, supplemental-action.json and supplemental-repeated-actions.json. OWN-08's separate passing retest also does not rewrite historical65/69.

Official source verified in the read-only audit at commit2ae2f521836f1eaf50ebb8dbf778c42ed8af89f2: https://github.com/set168111/Agentic-AI-Bootcamp-Students/blob/2ae2f521836f1eaf50ebb8dbf778c42ed8af89f2/Final-Mini-Project/scenario-2-it-helpdesk/kit/dataset/student_scenarios/sample_requests.md
