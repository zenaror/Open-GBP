#!/usr/bin/env bash
# tools/status.sh -- is the project being worked on right now? Read-only, a few lines, safe at any moment.
#
#     tools/status.sh [repo-dir]
#
# GitHub Issue #124 (asked by the Orchestrator for the Operator). The gate runs quietly and nothing is pushed until it
# passes, so origin/main lags local work by the length of a gate BY DESIGN, and silence looks like having stopped. This
# prints what the silence is:
#   HEAD vs origin/main   commits waiting to be pushed: a remote that lags is the gate, not inactivity. origin/main is
#                         the LOCAL copy as last fetched (its age is shown); this tool never fetches.
#   last commit           its age and subject: the actual work rate.
#   running               a gate, build, Dolphin or Ghidra run in flight, with its elapsed time.
#   working tree          how many files are changed and not committed.
#   verdict               one line. When nothing visible is happening it SAYS SO, plainly: the point is to make
#                         idleness visible, never to make it look busy. It cannot see reading, review agents or thinking,
#                         and says that too.
# It writes nothing -- not even the index: `git status` would refresh it, so it runs with --no-optional-locks --
# fetches nothing, and changes no ref. STATUS_PS (a file of `ps -eo etimes=,args=` lines) replaces
# the live process list, for tests.
set -u
REPO="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO" 2>/dev/null || { echo "status: no such directory: $REPO"; exit 2; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "status: not a git repository: $REPO"; exit 2; }
now=$(date +%s)

ago() {
    local s=$1
    if [ "$s" -lt 60 ]; then echo "${s}s"
    elif [ "$s" -lt 3600 ]; then echo "$((s / 60))min"
    else echo "$((s / 3600))h$(((s % 3600) / 60))min"; fi
}

head=$(git rev-parse --short HEAD 2>/dev/null || echo none)
ahead=0
if git rev-parse -q --verify origin/main >/dev/null 2>&1; then
    remote=$(git rev-parse --short origin/main)
    ahead=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
    behind=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
    fh=$(git rev-parse --git-path FETCH_HEAD)
    if [ -f "$fh" ]; then fetched="$(ago $((now - $(stat -c %Y "$fh")))) ago"; else fetched="never here"; fi
    echo "HEAD $head   origin/main $remote (local copy, fetched $fetched)   to push: $ahead   behind: $behind"
else
    echo "HEAD $head   origin/main: not known in this checkout"
fi

last_age=-1
if git rev-parse -q --verify HEAD >/dev/null 2>&1; then
    read -r ct subj < <(git log -1 --format='%ct %s')
    last_age=$((now - ct))
    echo "last commit: $(ago "$last_age") ago   ${subj:0:78}"
fi

if [ -n "${STATUS_PS:-}" ]; then ps_out=$(cat "$STATUS_PS"); else ps_out=$(ps -eo etimes=,args= 2>/dev/null); fi
running=$(printf '%s\n' "$ps_out" | awk -v self="$$" '
    /tools\/status\.sh/ { next }
    /make( --no-print-directory)? test-python|make -C tests\/unit|pytest|docker compose run|analyzeHeadless|dolphin-emu|make stimulus|make build|make swiss/ {
        s = $1; $1 = ""; sub(/^ /, "")
        key = substr($0, 1, 60)
        if (key in seen) next
        seen[key] = 1
        printf "%d\t%s\n", s, substr($0, 1, 70)
    }' | sort -rn | head -n 5)
n_running=0
if [ -n "$running" ]; then
    while IFS=$'\t' read -r s cmd; do
        echo "running: $(ago "$s")   $cmd"
        n_running=$((n_running + 1))
    done <<< "$running"
fi

files=$(git --no-optional-locks status --porcelain 2>/dev/null | wc -l)   # no index refresh: never writes
echo "working tree: $files file(s) changed, not committed"

if [ "$n_running" -gt 0 ]; then
    echo "verdict: ACTIVE -- $n_running run(s) in flight"
elif [ "$ahead" -gt 0 ]; then
    echo "verdict: WAITING TO PUSH -- $ahead commit(s) ahead of origin/main, nothing running: gate or push pending"
elif [ "$files" -gt 0 ]; then
    echo "verdict: EDITING -- $files file(s) changed, nothing running, nothing unpushed"
elif [ "$last_age" -ge 0 ] && [ "$last_age" -lt 1800 ]; then
    echo "verdict: RECENT -- last commit $(ago "$last_age") ago; nothing running, nothing unpushed, tree clean"
else
    echo "verdict: NOTHING VISIBLE IS HAPPENING -- nothing running, nothing unpushed, tree clean, last commit" \
         "$( [ "$last_age" -ge 0 ] && ago "$last_age" || echo "?") ago"
fi
echo "(sees git and processes only; not reading, review agents or thinking)"
