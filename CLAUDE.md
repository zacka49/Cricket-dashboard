# Agent Collaboration Protocol

This repo is being edited by two CLI agents (Claude Code and Codex CLI) at once, coordinated through files in `.agents/` rather than a live channel. There is no direct communication between the two agents — the human relays kickoff prompts and handoff notes between sessions.

Before starting work:
- Read `.agents/TASKS.md`, `.agents/DECISIONS.md`, and `.agents/HANDOFFS.md`.
- Claim one task in `.agents/TASKS.md` by setting `owner`, `claimed_at`, and `status: in_progress`. Only claim a task whose `depends_on` tasks are already `status: done`.
- Do not edit any file outside the `files` list of the task you claimed. If you think you need to, stop and note it in `.agents/HANDOFFS.md` instead of just doing it.
- `.agents/DECISIONS.md` has the full old-name -> new-name rename table already worked out. Use it directly instead of re-deriving names by grepping the repo — this saves tokens on both sides.

When finishing a task:
- Update its row in `.agents/TASKS.md` to `status: done`.
- Append a short entry to `.agents/HANDOFFS.md`: From / Task / Files changed / Verification run / Result / Notes for the next task.
- List the files you changed (or commit them) so the human can see the diff.

Current task queue owners: Claude owns T1-T6 and T8 (sequential, interdependent files). Codex owns T7 (the four docs — README.md, docs/ARCHITECTURE.md, docs/ROADMAP.md, docs/BULLETPROOFING_CHECKLIST.md), which has zero file overlap with T1-T6 and can start immediately.
