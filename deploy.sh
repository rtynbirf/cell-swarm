#!/usr/bin/env bash
# deploy.sh — ВСЕ оставшиеся действия, требующие руки/авторизации, одной командой.
# У агента песочницы авторизации к GitHub нет и не должно быть (секреты не агентов);
# это единственный такт, который остаётся за Человеком или за агентом с токеном.
#
#   ./deploy.sh              — пуш ядра + мембранных веток клеток (+ PR, если есть gh)
#   ./deploy.sh --core-only  — только ядро роя
#
# Зависимости: git обязателен; gh (GitHub CLI, авторизованный: gh auth login) — опционален.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OWNER="rtynbirf"
CORE_REPO="$OWNER/cell-swarm"

AUTH="нет"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then AUTH="gh"; fi
echo "авторизация: $AUTH"

# --- 1. ядро роя ---
cd "$ROOT"
if ! git remote get-url origin >/dev/null 2>&1; then
  if [ "$AUTH" = "gh" ]; then
    gh repo create "$CORE_REPO" --public --source . --push
    echo "ядро: репо создано и запушено"
  else
    echo "1) создай ПУСТОЙ репо https://github.com/$CORE_REPO (без README), затем:"
    echo "   git remote add origin https://github.com/$CORE_REPO.git && git push -u origin main"
    echo "   (или поставь gh и сделай: gh auth login && ./deploy.sh)"
    exit 1
  fi
else
  git push origin main
  echo "ядро: main запушен"
fi

# --- 2. мембранные ветки клеток (клоны в cells/ — вне истории ядра) ---
[ "${1:-}" = "--core-only" ] && exit 0
for cell in "$ROOT"/cells/*/; do
  [ -d "$cell/.git" ] || continue
  name=$(basename "$cell")
  branch=$(git -C "$cell" rev-parse --abbrev-ref HEAD)
  default=$(git -C "$cell" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
  default="${default:-main}"
  if [ "$branch" = "$default" ]; then
    echo "$name: на дефолтной ветке — ветки для пуша нет, пропуск"
    continue
  fi
  git -C "$cell" push -u origin "$branch"
  echo "$name: ветка $branch запушена"
  if [ "$AUTH" = "gh" ]; then
    (cd "$cell" && gh pr create \
      --repo "$OWNER/$name" --base "$default" --head "$branch" \
      --title "membrane: llms.txt / AGENTS / MANIFEST от роя cell-swarm (2026-11-05)" \
      --body "Аддитивная мембрана от роя cell-swarm (Закон 1: мембрана для машин). Живые пути выверены клоном 2026-11-05. DCO: коммиты подписаны. Автор — $OWNER, соавтор — агент роя.")
    echo "$name: PR создан"
  else
    echo "$name: PR вручную → https://github.com/$OWNER/$name/pull/new/$branch"
  fi
done

echo "готово: всё, что могло быть сделано без человека, уже сделано — остальное было здесь."
