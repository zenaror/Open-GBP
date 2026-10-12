# AI coauthor history maintenance — 2026-10-12, Issue #164

The Operator explicitly authorized a one-time exception to AGENTS.md sections
36/37: remove automatic Claude/Anthropic Co-authored-by trailers and publish only
main with an expected-SHA force-with-lease. This is not general permission to
rewrite history. No hardware run or scientific status changes.

Original main: `77fa9364f1a0f578555c570b919e093f68facfe5`.
Rewritten historical tip: `6aa30cf99c8f1bd3fbdeded7df3ded5a5597659b`.
The accompanying JSON maps all 624 commits; exactly 587 trailer lines were
removed. Every historical tree, author, committer, date, other message byte and
parent topology was checked. No signed commits, tags, gitlinks, PRs or forks
were found. The only configured remote is origin (GitHub); no upstream or
mirror is changed. Issues retain their historical commit references.

## Evidence identities and recovery

Historical source references and embedded build identities retain their ORIGINAL
hashes. No pins, DOLs, fixtures, frozen sources or scientific records are rewritten.
Rebuilding at a mapped commit does not reproduce an image stamped with the
original hash. Recover the original commit objects before replaying historical
build recipes or running tests that read historical commits.

Run `python3 tools/history_recover.py` in a fresh clone. It reconstructs original
commit objects from the published rewritten commits plus the removed-line
positions in `ai-coauthor-2026-10-12.json`, verifying each original hash before
writing. It changes no branch, tag, file, remote or configuration. These local
objects preserve original citations; they are not published refs. Git garbage
collection can remove them; rerun recovery before historical work if needed.

A verified original-main.bundle and audit are also retained privately under
`captures/private/history-2026-10-12/` on the development checkout, outside refs
destined for publication. That ignored backup is never pushed. The public JSON
contains commit mappings and removed AI trailer lines only, no private inputs.

## Existing clones

Preserve local changes and commits first. Fetch origin, compare the old/new map,
and move or recreate local branches deliberately; do not merge the old main into
the rewritten main or push old history back. A fresh clone followed by the recovery
command is the simplest option. No destructive migration command is prescribed
for shared checkouts. Open PRs: none at the inventory; new PRs must use the new base.

The physical session of Issue #161 remains cleared on its ORIGINAL build identity.
Its frozen procedure and binary hashes are unchanged.
