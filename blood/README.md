# Кровь роя (межтельная)

Два носителя крови в рое — не дубли, а разные русла:

| Носитель | Что несёт | Где живёт |
| --- | --- | --- |
| Журнал тела (`scripts/emit.py`, SPEC-0003) | события ОДНОГО тела (plan/act/observe/…) | локальный jsonl, хеш-цепь |
| **Конверт крови клеточной цепи** (`blood/kernel/blood.py`, ADR-0013) | состояние МЕЖДУ телами: желаемое ↔ наблюдаемое ↔ статус, с допуском и ttl | `blood/CELLS-LEDGER.jsonl` — летопись цепи (геному → клеткам) |
| Пульс-конверты П-24 (`blood_sdk`, подписки) | объявление пульса генома подписчикам | `blood/LEDGER.jsonl` — летопись П-24 |

## Как течёт кровь (пульс)

```
геном cell-swarm (workflow_dispatch: blood-genome)
  → конверт: живые HEAD клеток цепи, допуск eps=0 (SHA точен), ttl=900s
  → прививка к хвосту CELLS-LEDGER.jsonl (хеш-цепь, tamper-evident)
  → dispatch repository_dispatch(blood-pulse) → runtime-protocol
      → сверка github.sha с конвертом → эхо в CELLS-LEDGER.jsonl
      → dispatch → polymath-os
            → сверка → эхо в CELLS-LEDGER.jsonl
            → dispatch → cell-rs   (ВОЛНА ×9: первая Rust-клетка)
                  → сверка конверта ВТОРЫМ ЯЗЫКОМ (Rust-гейт blood_gate)
                    ДО эха: подделка не дойдёт до летописи
                  → эхо в CELLS-LEDGER.jsonl
                  → dispatch → voice-atlas-llm
                        → сверка → эхо в CELLS-LEDGER.jsonl (конец пульса)
```

Волна ×9 «рой из модели в кровь» (2026-11-09): цепь = **четыре живые клетки**.
Канон вердиктов (ядро ADR-0004/0013): геномный конверт несёт ожидания
payload.cells — их точно сверяет ПЕРВАЯ клетка цепи (VERIFIED/DRIFT, eps=0);
дальше эхо несёт факт вперёд, последующие клетки дают честное OBSERVED
(ожидания в эхе нет — клетка не сверяется вслепую). Руст-гейт cell-rs
дополнительно сверяет геномное ожидание клетки, извлекая его из байтов
летописи (геномный пульс запечатан в цепи) — вторым языком, fail-closed
на подделку.

Запуск — только по событию. Текущий факт цепи можно сверить офлайн:

```bash
python3 - <<'EOF'
import json, sys
sys.path.insert(0, "blood/kernel")
from blood import chain_verify
lines = open("blood/CELLS-LEDGER.jsonl").read().splitlines()
print(chain_verify(lines))
EOF
```

Ядро конверта продаётся из клетки-ядра (vendored): `blood/kernel/blood.py`
= `rtynbirf/runtime-protocol@2337fc2:blood.py`, sha256
`482db96b2935ac10b2ddfbdc03a56ad9eb662cc8471d6934d7e3035ffb986057`.
Обновление = новый пин ядра + пересверка суммы (не править руками).

`blood_cell.py` там же, из того же пина: sha256
`1f5bdc99600a25d58bca308dc299956c639b9805356088e4b46ce6fb73cc15ce`
(включает идемпотентный повтор: конверт уже в летописи = не рана).
