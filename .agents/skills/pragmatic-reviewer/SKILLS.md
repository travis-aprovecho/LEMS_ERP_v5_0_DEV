---
name: pragmatic-reviewer
description: Evaluates proposed code additions for quality and over-engineering. Use when planning upgrades or reviewing code changes.
---

# Pragmatic Reviewer Protocol

When evaluating tasks or writing code for this repository, always enforce the following guardrails:

1. **Anti-Complexity Filter:** Actively challenge any architectural changes that introduce new dependencies or frameworks unless absolutely necessary.
2. **Value vs. Weight:** Weigh the engineering complexity against the actual realized value for live projects. If a feature is "nice to have" but adds high maintenance overhead, flag it as over-engineering.
3. **UI/UX Performance:** Ensure user interfaces remain clean, fast, and functional. Avoid clunky components.
4. **Testing:** Before completing a task, check if local scripts or tests can be executed to verify functionality.

## Definition of Done (DoD)
Before marking a task as complete, the agent must:
1. Run local tests or execute scripts via the terminal to verify no syntax errors or regressions were introduced.
2. Ensure any new file dependencies or package imports are explicitly added to the environment configurations.
3. Provide a brief "Impact Summary" explaining what was changed and why it preserves code efficiency.

## Feature Evaluation Framework (The "Is It Worth It?" Test)
If the user or agent proposes a new feature, pass it through this decision tree before writing code:
- Does this solve an actual bottleneck currently experienced in live project testing? If no, defer it to `dev_notes/future_ideas.md`.
- Does this change require adding a massive new third-party dependency? If yes, look for a lightweight native Python alternative first.
- Does it make the core UI slower or more complex to navigate? If yes, reject or simplify the implementation.

## Examples of Pragmatic Guidance

**Example 1: Rejecting Over-Engineering**
*User Request:* "Should we migrate the local storage system to a full PostgreSQL database for better scaling?"
*Agent Response (Adhering to Skill):* "For live project testing, the current local data storage is completely sufficient and fast. Moving to PostgreSQL right now adds infrastructure overhead, connection management complexity, and setup friction without giving us any immediate day-to-day value. Let's stick with the streamlined local system until data volume forces our hand."

**Example 2: Accepting Worthwhile Additions**
*User Request:* "Can we add an auto-backup feature for our configuration files?"
*Agent Response (Adhering to Skill):* "Yes. This adds high value with very low complexity. I can implement a simple, lightweight utility that copies the active config file to a `.backup` directory before every major live run. This protects data integrity during real-world testing without bloating the application."