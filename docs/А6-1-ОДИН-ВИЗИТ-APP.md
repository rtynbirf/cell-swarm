# А6-1 · ОДИН-ВИЗИТ · App «кровь-геном»

Дверь крови (`blood-genome.yml`, механизм скован на `67ed939`) УЖЕ умеет чеканить короткие
App-токены (create-github-app-token@64ab729a, SHA-пин С128) — не хватает только факта App'а.
Этот пакет делает активацию ОДНИМ визитом владельца (~3 минуты). Фолбэк на конверт B′
(`CELL_SWARM_DISPATCH_TOKEN`) остаётся честным, пока переменная не поставлена.

## Шаг 1 · Создать App (UI, рука владельца — физика API не умеет создавать Apps)
1. Открыть: https://github.com/settings/apps/new
2. Заполнить ровно так:
   - **GitHub App name**: `blood-genome` (или «кровь-геном»)
   - **Homepage URL**: `https://github.com/rtynbirf/cell-swarm`
   - **Webhook**: снять галочку Active (хуки не нужны)
   - **Permissions · Repository permissions**: `Contents` → **Read-only**; `Actions` → **Read and write**
   - **Where can this app be installed**: **Only on this account** (rtynbirf)
   - **Install App** → установить ТОЛЬКО на `rtynbirf` (не на все репо — по канону конверта: минимум прав)
3. После создания: **Generate private key** → скачается `.pem` (показывается ОДИН раз)
4. Со страницы App взять **App ID** (число)

## Шаг 2 · Секреты и переменная (можно руками в UI или командой ниже)
| что | куда | значение |
|---|---|---|
| App ID | cell-swarm → Settings → Secrets → Actions → `CELL_SWARM_APP_ID` | число из шага 1.4 |
| приватный ключ | там же → `CELL_SWARM_APP_PRIVATE_KEY` | содержимое `.pem` целиком (с BEGIN/END строками) |
| рубильник | cell-swarm → Settings → Variables → Actions → `CELL_SWARM_APP_ON` | `1` |

Командный путь (если PAT под рукой; токен только чат/env — протокол дома):
    gh secret set CELL_SWARM_APP_ID --repo rtynbirf/cell-swarm --body "<App ID>"
    gh secret set CELL_SWARM_APP_PRIVATE_KEY --repo rtynbirf/cell-swarm < blood-genome.pem
    gh variable set CELL_SWARM_APP_ON --repo rtynbirf/cell-swarm --body 1

## Шаг 3 · Приёмка одним диспатчем
    gh workflow run blood-genome.yml --repo rtynbirf/cell-swarm
Приёмка = зелёный прогон blood-genome: пульс дойдёт цепью runtime-protocol → polymath-os →
cell-rs → voice-atlas-llm, в логе будет видно, что токен чеканен App'ом (не B′-фолбэк).
Правило дома ×30: НЕ ставить CELL_SWARM_APP_ON=1 до живых секретов — гарантированный красный.

## Что это меняет
- Дверь крови перестанет тратить длинный PAT: короткие App-токены (≈1 ч), права ровно
  contents:read + actions:write, установка только на rtynbirf.
- Конверт B′ (смерть ключа 2026-12-16) станет запасным, а не основным.
- Прецедент мирового поиска ×30: GitHub-to-GitHub = App installation token (stepsecurity.io).
