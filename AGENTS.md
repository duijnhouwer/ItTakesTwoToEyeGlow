# Workspace Instructions

## Discuss before implementing

- The user is new to this type of data and user interface. Treat their proposed implementation as a starting hypothesis, not automatically as the final specification.
- Before substantial implementation, building, or refactoring, provide constructive pushback where warranted and ask focused clarifying questions about the intended outcome, constraints, and assumptions.
- When the user suggests an approach, explain its meaningful trade-offs and identify better alternatives when they exist, especially established industry-standard or broadly accepted methods.
- When multiple reasonable approaches exist, present the viable options, their pros and cons, and a recommendation before breaking ground.
- Surface likely risks, hidden complexity, data-quality concerns, and downstream consequences early. Be candid but collaborative; explain the reasoning behind disagreements.
- Do not interpret this guideline as requiring questions before every action. Routine read-only investigation, clearly reversible housekeeping, and small unambiguous changes may proceed directly. Pause for discussion when a choice could materially affect architecture, data interpretation, user experience, cost, or future maintenance.

## Dataset protection

- Treat `/home/jacob/Documents/EyeGlowEgoBody/assets/egobody-data` as strictly read-only.
- Do not create, modify, move, rename, or delete anything inside that directory.
- Read and analyze files there only. Write derived artifacts, caches, logs, and generated outputs elsewhere, such as `/home/jacob/Documents/EyeGlowEgoBody/code-repo`.
- If a requested operation appears to require changing the dataset, stop and ask the user before proceeding.
