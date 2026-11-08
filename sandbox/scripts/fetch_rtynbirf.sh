#!/usr/bin/env bash
# fetch_rtynbirf.sh — снимок состояния GitHub владельца (зеркало из песочницы).
# Сеть только у GitHub; результат — в stdout, дату фиксирует вызывающий в STATE.json.
set -uo pipefail
W="${WORK:-/tmp/fetch-work}"
mkdir -p "$W"
cd "$W"

if [ ! -d commons/.git ]; then
  git clone --filter=blob:none --depth 1 https://github.com/rtynbirf/commons commons 2>&1 | tail -2
fi
cd commons
echo "=== HEAD ==="
git rev-parse HEAD
git fetch origin '+refs/pull/*/head:refs/remotes/prs/*' 2>&1 | tail -3
echo "=== remote branches ==="
git branch -r
echo "=== main log ==="
git log --oneline -8
echo "=== PR heads ==="
for pr in $(git for-each-ref --format='%(refname:short)' refs/remotes/prs/ 2>/dev/null); do
  echo "--- $pr"
  git log -1 --format='%h %an %ad %s' --date=short "$pr" 2>/dev/null
  echo "touched paths:"
  git diff --stat main..."$pr" 2>/dev/null | tail -5
done
echo "=== tags (sorted) ==="
git ls-remote --tags origin | awk '{print $2}' | sed 's|refs/tags/||;s|\^{}||' | sort -V | uniq | tail -8

cd "$W"
echo "=== other repos HEAD pins ==="
for r in polymath-os singulyar singulyar-llm cell65-host rumu voice-atlas-llm global-video-platforms-registry; do
  printf '%s : ' "$r"
  git ls-remote "https://github.com/rtynbirf/$r.git" HEAD 2>/dev/null | head -1 | awk '{print $1}'
done
