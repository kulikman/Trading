# Skill: /memory

## Trigger
`/memory update` — save current session state
`/memory show`   — display current project context

---

## /memory update

Save current session state to memory files.

### Steps

1. Ask (or infer from context):
   - What feature was worked on?
   - What was completed?
   - What's next?
   - Any open questions or blockers?

2. Update `.claude/memory/project-state.md`:
   - Set "Last Updated" to today's date
   - Fill in Current Feature, Status, What Was Done, Next Steps
   - Add entry to Session History

3. Update `.claude/memory/decisions.md` if any architectural decisions were made

4. Update `.claude/memory/patterns.md` if any new patterns were discovered or anti-patterns hit

### Output
Confirm: "Memory updated. Next session will resume from: [current state summary]"

---

## /memory show

Display current project context in a readable summary.

### Steps

1. Read `.claude/memory/project-state.md`
2. Read `.claude/memory/decisions.md` (last 3 entries)
3. Read `.claude/memory/patterns.md` (established patterns list)

### Output Format
```
## Project Context

**Feature in Progress:** [name]
**Status:** [status]
**Next Steps:**
  1. [step]
  2. [step]

**Recent Decisions:**
  - [decision]

**Established Patterns:**
  - [pattern name]

**Open Questions:**
  - [question]
```
