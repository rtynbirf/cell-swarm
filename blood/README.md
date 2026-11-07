# Кровь роя (межтельная)

Два носителя крови в рое — не дубли, а разные русла:

| Носитель | Что несёт | Где живёт |
| --- | --- | --- |
| Журнал тела (`scripts/emit.py`, SPEC-0003) | события ОДНОГО тела (plan/act/observe/…) | локальный jsonl, хеш-цепь |
| **Конверт крови** (`blood/kernel/blood.py`) | состояние МЕЖДУ телами: желаемое ↔ наблюдаемое ↔ статус, с допуском и ttl | `blood/LEDGER.jsonl` — общая летопись роя |

## Как течёт кровь (пульс)

```
геном cell-swarm (workflow_dispatch: blood-genome)
  → конверт: живые HEAD клеток, допуск eps=0 (SHA точен), ttl=900s
  → прививка к хвосту LEDGER.jsonl (хеш-цепь, tamper-evident)
  → dispatch repository_dispatch(blood-pulse) → runtime-protocol
      → сверка github.sha с конвертом → эхо в LEDGER.jsonl
      → dispatch → polymath-os
            → сверка → эхо в LEDGER.jsonl (конец пульса)
```

Запуск — только по событию. Текущий факт цепи можно сверить офлайн:

```bash
python3 - <<'EOF'
import json, sys
sys.path.insert(0, "blood/kernel")
from blood import chain_verify
lines = open("blood/LEDGER.jsonl").read().splitlines()
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
