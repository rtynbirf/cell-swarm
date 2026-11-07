# CHANGELOG — рой cell-swarm

Формат — Keep a Changelog. Версии и релизы — за Человеком (PID 1);
агент роя пополняет только раздел Unreleased. Даты — по факту, без задним числом.

## [Unreleased]

### Добавлено

- межтельная кровь (ADR-0013): `blood/kernel/` + `scripts/genome_pulse.py` +
  workflow `blood-genome`; летопись `blood/LEDGER.jsonl`; приёмник второй
  живой клетки в polymath-os; статусы эха VERIFIED/OBSERVED; идемпотентный
  повтор доставки.
- память роя с допуском: `memory/MEM-0001..0003.json` (ttl_days, хеш-цепь,
  провенанс CONFIRMED) + `tools/memory_check.py` (`make memory`, CI-хук).
- Rust-тропа в клетке runtime-protocol (`rust_trail/`, ADR-0005 клетки):
  канон + sha256 std-only, байт-в-байт с ядром по золотым пробам (CI `rust-trail`).

### Изменено

- сверка генома genome-reconcile стала контуром: перечитать территорию
  (`fetch` + `rebase`) → пины живым ls-remote → вписать факт → повторить
  до схождения (3 попытки); гонка с параллельным пушем 2631bd6 больше
  не роняет сверку — актюатор перечитывает карту непосредственно перед
  действием (урок TH-RTP-06, ADR-0003 клетки runtime-protocol).
- геном 0.1.9: cell-rs вписана пином живым ls-remote (10 клеток).

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
- `deploy.sh`: ВСЕ действия, требующие авторизации (пуш ядра, мембранные ветки,
  PR через gh) — одной командой; у агента песочницы токенов нет и не должно быть.
- мембранные ветки клеток (клоны в `cells/`, вне истории ядра):
  polymath-os — llms.txt (единственная дыра мембраны ОС, только живые пути);
  rumu — AGENTS.md + MANIFEST.json + llms.txt: клетка-указатель (Закон 3),
  пин на singulyar@rumu `30bcf37b`, жанр README «честная заглушка» сохранён.

### Проверено живым (2026-11-05)

- дом COMMONS HEAD `5501dafd` — байт-в-байт равен `anchor_pin` генома;
- `make cross-handshake`: обе грамматики читают друг друга, вердикты совпали
  (granted / granted / denied(method_not_in_scope) — ожидаемо и поимённо);
- ритуал усиления дома (пакет `commons-strengthen`): pytest дома 4/4,
  doctor дома 970 ok / 0 failed (на полной истории клона).
- свЕРка генома: все 8 пинов равны живым HEAD (`git ls-remote`, 2026-11-05).
- лицензии всех 8 клеток верифицированы живым GitHub API: MIT ×5, Apache-2.0 ×2,
  CC-BY-4.0 ×1; прежняя запись «license=null» — следствие лимита API, не факта
  (геном 0.1.1, поля licenses_*).
- тело rumu подтверждено живым клоном ветки singulyar@rumu: cinema.html,
  catalog.js, cord.js, autopilot_client.js — пин генома и MANIFEST клетки совпадают.
