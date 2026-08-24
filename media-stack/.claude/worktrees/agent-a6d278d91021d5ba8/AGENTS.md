# AGENTS.md

Guidance for AI coding agents working in this repo. Read `CLAUDE.md` first for architecture
orientation, common commands, and facts that span multiple files.

## No downstream sibling - this stack is private

**This repo has no public downstream mirror as of 2026-07-21.** `StackMaster` (the standalone
CLI + control panel, itself a merge of two earlier public repos `Stackalicious` and
`StackScripts`, both deleted 2026-07-19) was deleted outright from GitHub at the user's
explicit request, for the same reason: privatization. Do not create a new public mirror, and
do not trust any doc predating this one (including older versions of this file) that names
`StackMaster`/`Stackalicious`/`StackScripts` as a live sync target - none of them exist
anymore, deliberately.

## `stack-*` commands are host-local only

Every `stack-*` command lives entirely in this host's own `~/.config/fish/functions/` (a fish
function calling Control Panel's HTTP API at `/api/...`, backed by a route in
`control-panel/app.py` in this repo). There is no other copy anywhere, in any shell, on any
other repo. A new `stack-*` command is done when it works on this host - nothing further to
mirror, port, or sync.

If a future need for a portable/redistributable version resurfaces, that is a new decision to
make explicitly with the user first (per the 2026-07-21 privatization request), not something
to default back into by adding files to a new external repo unprompted.

## Coding Tasks

When spawning Claude Code sessions for coding work, tell the session to use gstack skills.

Examples:

- Security audit: "Load gstack. Run /cso"
- Code review: "Load gstack. Run /review"
- QA test a URL: "Load gstack. Run /qa https://..."
- Build a feature end-to-end: "Load gstack. Run /autoplan, implement the plan, then run /ship"
- Plan before building: "Load gstack. Run /office-hours then /autoplan. Save the plan, don't implement."
