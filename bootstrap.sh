#!/usr/bin/env bash
# bootstrap.sh — семя роя: поднять клетки по пинам генома (Закон 5).
# Офлайн-first: клетки тянутся один раз, дальше checkout по пину работает офлайн.
#   ./bootstrap.sh            — online: clone/fetch при необходимости
#   ./bootstrap.sh --offline  — только существующие клоны, недостающее — поимённый отказ
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CELLS_DIR="${CELLS_DIR:-$ROOT/cells}"
MODE="online"
[ "${1:-}" = "--offline" ] && MODE="offline"

cd "$ROOT"
# Клетки из генома читает python3 — геном источник истины, шелл его не парсит.
CELLS=$(python3 - <<'PY'
import json
from pathlib import Path
genome = json.loads(Path("swarm.json").read_text(encoding="utf-8"))
for cell in genome["cells"]:
    if cell.get("bridge"):
        continue  # дом поднимается сам (scripts/first_pulse.py дома); рой не тянет дом по пину
    print(f"{cell['name']}\t{cell['repo']}\t{cell['pin']}")
PY
)

mkdir -p "$CELLS_DIR"
fail=0
while IFS=$'\t' read -r name repo pin; do
  [ -z "$name" ] && continue
  dir="$CELLS_DIR/$name"
  if [ -d "$dir/.git" ]; then
    if [ "$MODE" = "online" ]; then
      git -C "$dir" fetch origin --tags --quiet || { echo "  $name: fetch не удался"; fail=1; continue; }
    fi
  else
    if [ "$MODE" = "offline" ]; then
      echo "  $name: клон отсутствует, офлайн-режим — ОТКАЗ поимённо"
      fail=1
      continue
    fi
    git clone --quiet "$repo" "$dir" || { echo "  $name: clone не удался"; fail=1; continue; }
  fi
  if git -C "$dir" rev-parse -q --verify "$pin^{commit}" >/dev/null; then
    git -C "$dir" -c advice.detachedHead=false checkout --quiet "$pin"
    echo "  $name: пин ${pin:0:8} — жив"
  else
    echo "  $name: пина ${pin:0:8} нет в клоне (нужен fetch с upstream)"
    fail=1
  fi
done <<< "$CELLS"

echo
python3 "$ROOT/scripts/verify.py" || fail=1
exit $fail
