# DEPLOY — как реализовать рой на GitHub

Поставка собрана офлайн; сеть нужна только GitHub-у. Порядок:

## 1. Создать репозиторий cell-swarm

Поставка уже инициализирована (`git init`, DCO-коммит сделан агентом роя;
автор — rtynbirf). Осталось:

```bash
cd cell-swarm
# создать пустой репо на GitHub (без README!), затем:
git remote add origin https://github.com/rtynbirf/cell-swarm.git
git push -u origin main
```

`-s` — DCO (Signed-off-by): тот же протокол, что у дома.

Клетки в `cells/` — живые клоны с мембранными ветками; `./deploy.sh` запушит
их сам. Клон `cells/singulyar-rumu/` — доказательство проверки тела (не пушится:
он на дефолтной ветке); в zip-поставку он не входит и восстанавливается одной
командой: `git clone -b rumu https://github.com/rtynbirf/singulyar cells/singulyar-rumu`.

## 2. Проверить мост против живого клона дома

```bash
git clone https://github.com/rtynbirf/commons ../commons   # если клона нет
make cross-handshake COMMONS=../commons
make test            # cross-тесты включатся сами, если клон рядом
```

## 3. Живой обмен (когда скажет Человек)

Дом держит свой ConsentGrant у себя (воля Человека — PID 1, не роя).
Человек заводит в доме grant с `peer: "cell-swarm"` и белым списком методов —
после этого `make cross-handshake` показывает вердикты обеих сторон на живой
грамматике `synapse/consent.py`.

## 3-бис. Разблокировка клетки и живой grant — как это делается

Оба действия исполнены роем 2026-11-05 (воля PID 1: «делай сам»); здесь —
команды повтора и отката.

Разблокировать репо клетки (пример rumu) и запушить мембрану:

```bash
# разблокировать (откат — та же команда с {"archived": true}):
curl -X PATCH -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/rtynbirf/rumu -d '{"archived": false}'

# мембрана: клонировать, ветка, три файла (AGENTS.md, MANIFEST.json, llms.txt),
# коммит -s, затем:
git push origin membrane-2026-11-05    # PR открывается в вебе или API
```

Живой grant дома: `commons/consent/grants.json` (волна №34, PR#6) — воля
PID 1; отзыв — удалением записи или файла; отозванный `consent_id` не оживает,
новый обмен требует нового согласия (ADR-0017 п.4 дома).

## 4. Дисциплина дальше

- пины: `make pins W=1` (сухой прогон — просто `make pins`)
- лицензии клеток: `make licenses W=1 GITHUB_TOKEN=...` (токен в env, не в кровь)
- митоз клетки: `cp templates/MANIFEST.json <новая>/`, ADR в ядре
- кровь: `python3 scripts/emit.py ... && python3 scripts/emit.py --verify`

## 5. Что нельзя

- force-push и правка крови задним числом (append-only);
- пин без живого источника и даты;
- обмен с домом мимо согласия (даже технически возможный);
- наружный шлюз (транспорты только stdio/http-localhost — ADR-0016 дома).
