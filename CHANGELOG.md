# CHANGELOG — рой cell-swarm

Формат — Keep a Changelog. Версии и релизы — за Человеком (PID 1);
агент роя пополняет только раздел Unreleased. Даты — по факту, без задним числом.

## [0.1.0] — 2026-11-05

### Добавлено

- геном `swarm.json`: 8 клеток с живыми SHA `git ls-remote` на 2026-11-05;
  мост в дом COMMONS (`anchor_pin` 5501dafd).
- фермент `bootstrap.sh`: подъём клеток по пинам; `--offline` — поимённый отказ.
- грамматики согласия: голос пира (ADR-0017 дома), согласия роя (ConsentGrant),
  вердикты до факта (`scripts/handshake.py`, `--cross` читает грамматику ДОМА).
- кровь SPEC-0003: конверты с ценой, append-only журнал, хэш-цепочка
  (`scripts/emit.py`); каноническая форма дома — совместимость байт-в-байт.
- прививка памяти: `sandbox/` (ADR-0007) — нуль агента (`MEMORY.md`),
  точка прерывания (`STATE.json`), зеркало скриптов; тест-храповик.
- приёмки: 25 тестов на stdlib; cross-тесты против живого клона дома.
- CI-метаболизм: `.github/workflows/ci.yml` (verify + tests на push/PR).

### Проверено живым (2026-11-05)

- дом COMMONS HEAD `5501dafd` — байт-в-байт равен `anchor_pin` генома;
- `make cross-handshake`: обе грамматики читают друг друга, вердикты совпали
  (granted / granted / denied(method_not_in_scope) — ожидаемо и поимённо);
- ритуал усиления дома (пакет `commons-strengthen`): pytest дома 4/4,
  doctor дома 970 ok / 0 failed (на полной истории клона).
