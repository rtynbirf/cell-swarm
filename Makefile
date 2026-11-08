# Метаболизм роя: короткие цели, всё офлайн кроме pins/licenses (они честно зовут сеть).
PYTHON ?= python3
COMMONS ?= ../commons
METHOD ?= genome.read

.PHONY: help verify handshake cross-handshake blood-demo blood-genome memory pins pins-seals licenses bootstrap to-organ-registry test

help:
	@echo "make verify            — геном/ДНК/голос/согласия fail-closed"
	@echo "make handshake METHOD=genome.read — вердикт согласия до факта"
	@echo "make cross-handshake COMMONS=../commons — грамматика дома читает голос роя"
	@echo "make blood-demo        — конверты SPEC-0003 + цепочка в tmp"
	@echo "make blood-genome      — удар крови: конверт+летопись+dispatch (нужен GH_TOKEN)"
	@echo "make memory            — сверка памяти роя: цепь+свежесть+источники"
	@echo "make pins              — живые SHA + корень SEALS-цепи карточек (dry-run; make pins W=1 — записать)"
	@echo "make pins-seals        — корень пломб-цепи карточек cards_seals в геноме (офлайн; W=1 — записать)"
	@echo "make licenses          — лицензии живым API (нужен GITHUB_TOKEN)"
	@echo "make bootstrap         — поднять клетки по пинам (./bootstrap.sh)"
	@echo "make to-organ-registry — экспорт клеток в словарь реестра органов дома"
	@echo "make test              — unittest приёмки"

verify:
	$(PYTHON) scripts/verify.py

handshake:
	$(PYTHON) scripts/handshake.py --method $(METHOD)

cross-handshake:
	$(PYTHON) scripts/handshake.py --cross $(COMMONS)

blood-demo:
	@J=$$(mktemp -d)/journal.jsonl; \
	$(PYTHON) scripts/emit.py --type boot  --source swarm --organ cell-swarm --trace demo --payload '{"note":"первая кровь роя"}' --journal $$J && \
	$(PYTHON) scripts/emit.py --type act   --source cell:polymath-os --organ cell-swarm --trace demo --payload '{"note":"клетка собралась"}' --tokens-in 120 --tokens-out 40 --seconds 1.5 --journal $$J && \
	$(PYTHON) scripts/emit.py --type observe --source swarm --organ cell-swarm --trace demo --payload '{"note":"наблюдение записано"}' --seconds 0.2 --journal $$J && \
	echo "--- цепочка:" && $(PYTHON) scripts/emit.py --verify --journal $$J && \
	echo "--- журнальный файл: $$J"

blood-genome:
	$(PYTHON) scripts/genome_pulse.py

memory:
	$(PYTHON) tools/memory_check.py $(if $(NO_NET),--no-net,)

pins:
	$(PYTHON) scripts/pin.py $(if $(W),--write,)

pins-seals:
	$(PYTHON) scripts/pin.py --seals-root $(if $(W),--write,)

licenses:
	$(PYTHON) scripts/pin.py --licenses $(if $(W),--write,)

bootstrap:
	./bootstrap.sh

to-organ-registry:
	$(PYTHON) scripts/to_organ_registry.py

test:
	$(PYTHON) -m unittest discover -s tests -v
