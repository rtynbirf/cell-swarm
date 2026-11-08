#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пломба A2A-карточек клеток роя cell-swarm (Э-2.2, волна ×5 «Реестр-добой»).

Роль — генератор. Верификатор — tools/verify_card_seals.py, сознательно
отдельный файл: доверие не импортируют, проверяющий не зависит от проверяемого.

Механика (без PKI): геном swarm.json (НЕ изменяется) -> для каждой клетки
строится A2A-стиль Agent Card {name, identity{repo,cell}, skills, endpoints};
карточка пишется в <out-dir>/cards/<имя>.json; sha256 её байтов дописывается
append-only строкой в SEALS.jsonl вида:

    {"ts": "...", "card": "<имя>.json", "sha256": "<64 hex>", "prev_hash": "<64 hex>"}

где prev_hash = sha256 канонической сериализации предыдущей строки цепи
(genesis: 64 нуля). Целостность карточки доказывается пересчётом цепи.

Правила чистоты:
- только stdlib;
- постоянные карточки в репо не создаются: вне --selftest обязателен --out-dir
  (живой цикл пишет в tempfile, репо не меняется, swarm.json не пишется);
- endpoints — файл-транспорт роя (реальные файлы репо), никаких выдуманных URL;
- повторный запуск идемпотентен: строка цепи дописывается только для карточки,
  которой ещё нет в цепи или чей sha256 изменился;
- перед дописыванием существующая цепь проверяется на сцепку: рваную цепь
  продлеваем отказом (exit 1), а не молчанием.

Использование:
  python3 tools/seal_agent_cards.py --out-dir DIR [--genome PATH] [--seals PATH]
  python3 tools/seal_agent_cards.py --selftest
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

GENESIS_HASH = "0" * 64
# Карточку строит геном роя; если пин клетки не несёт репо, клетка живёт в теле
# самого роя (как cell-rs/ внутри cell-swarm) — это честный дефолт, не выдумка.
DEFAULT_REPO = "rtynbirf/cell-swarm"
# Файл-транспорт роя: реальные файлы репо (подписки на пульс генома и летопись
# конвертов крови). Никаких сетевых URL здесь нет и не нужно.
ENDPOINTS = (
    {"transport": "file", "path": "subscribes.jsonl"},
    {"transport": "file", "path": "blood/LEDGER.jsonl"},
)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_SHAHEX = re.compile(r"^[0-9a-f]{64}$")


def canon(obj) -> bytes:
    """Каноническая сериализация строки цепи — детерминированная, для хеш-сцепки."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cell_from_entry(entry):
    """(name, repo, skills) из элемента коллекции клеток; None — элемент пропустить.

    Терпимые формы: строка (имя клетки) или словарь с именем в name/cell/id,
    репо в repo/repository (строка), навыки в skills (список, если есть).
    """
    if isinstance(entry, str):
        return entry, None, []
    if isinstance(entry, dict):
        name = entry.get("name") or entry.get("cell") or entry.get("id")
        if not isinstance(name, str) or not name.strip():
            return None
        repo = entry.get("repo", entry.get("repository"))
        if not isinstance(repo, str) or not repo.strip():
            repo = None
        skills = entry.get("skills") if isinstance(entry.get("skills"), list) else []
        return name.strip(), repo, skills
    return None


def extract_cells(genome):
    """Достаёт клетки из генома в формах, которые действительно встречаются.

    Порядок попыток: топ-уровень-список; genome["cells"]; genome["pins"]
    (пины генома — клетка, вписанная пином). Словарь вида {имя: строка}
    читается так: строка-похожая-на-хеш — это HEAD, не репо (репо неизвестно,
    берётся DEFAULT_REPO); прочая строка — репо клетки. Неопознанная форма —
    честный отказ с перечнем увиденных ключей, а не тихий пустой список.
    """
    if isinstance(genome, list):
        raw, where = genome, "топ-уровень генома (список)"
    elif isinstance(genome, dict):
        raw, where = None, ""
        for key in ("cells", "pins"):
            if key in genome:
                raw, where = genome[key], 'геном["%s"]' % key
                break
        if raw is None:
            keys = ", ".join(sorted(str(k) for k in genome)[:20])
            raise SystemExit("ОТКАЗ: в геноме не найдена коллекция клеток "
                             "(ожидались ключи cells или pins); ключи генома: %s" % keys)
    else:
        raise SystemExit("ОТКАЗ: геном не словарь и не список — форма неизвестна")

    cells = []
    if isinstance(raw, dict):
        for key, val in raw.items():
            if isinstance(val, dict):
                merged = dict(val)
                merged.setdefault("name", key)
                sub = cell_from_entry(merged)
            elif isinstance(val, str):
                if _SHAHEX.match(val):
                    sub = (str(key), None, [])  # это HEAD-пин, репо из него не читается
                else:
                    sub = (str(key), val, [])
            else:
                sub = (str(key), None, [])
            if sub:
                cells.append(sub)
    elif isinstance(raw, list):
        for entry in raw:
            sub = cell_from_entry(entry)
            if sub:
                cells.append(sub)
    else:
        raise SystemExit("ОТКАЗ: %s — не список и не словарь" % where)
    if not cells:
        raise SystemExit("ОТКАЗ: %s пуст — нечему ставить пломбу" % where)
    return cells


def build_card(name: str, repo: str, skills: list) -> dict:
    """A2A-стиль Agent Card клетки: четыре обязательных поля, ничего лишнего."""
    return {
        "name": name,
        "identity": {"repo": repo, "cell": name},
        "skills": list(skills),
        "endpoints": [dict(e) for e in ENDPOINTS],
    }


def card_bytes(card: dict) -> bytes:
    return json.dumps(card, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def load_seal_lines(path: Path) -> list:
    """Читает цепь: пустые строки и '#' -комментарии пропускаются, остальное — JSON."""
    lines = []
    if not path.exists():
        return lines
    for num, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        try:
            rec = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SystemExit("ОТКАЗ: %s строка %d не JSON (%s)" % (path, num, exc))
        if not isinstance(rec, dict):
            raise SystemExit("ОТКАЗ: %s строка %d — не объект" % (path, num))
        lines.append(rec)
    return lines


def chain_link_ok(lines: list) -> str:
    """Проверяет сцепку существующих строк; возвращает prev_hash для новой строки.

    Существующие строки (кроме сцепки) не перевалидируются целиком — это работа
    верификатора; здесь только защита от продления рваной цепи.
    """
    prev = GENESIS_HASH
    for i, rec in enumerate(lines):
        if not _SHAHEX.match(str(rec.get("prev_hash", ""))):
            raise SystemExit("ОТКАЗ: строка %d цепи — prev_hash не 64 hex" % (i + 1))
        if rec["prev_hash"] != prev:
            raise SystemExit("ОТКАЗ: цепь рвана на строке %d (prev_hash не сходится); "
                             "продлевать рваную цепь отказом, а не молчанием" % (i + 1))
        prev = sha_hex(canon(rec))
    return prev


def seal_cards(genome_path: Path, out_dir: Path, seals_path: Path) -> int:
    """Строит карточки, пишет их в out_dir/cards/ и дописывает цепь в seals_path."""
    try:
        genome = json.loads(genome_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit("ОТКАЗ: геном %s не читается (%s)" % (genome_path, exc))
    except json.JSONDecodeError as exc:
        raise SystemExit("ОТКАЗ: геном %s не JSON (%s)" % (genome_path, exc))

    cells = extract_cells(genome)
    existing = load_seal_lines(seals_path)
    prev = chain_link_ok(existing)
    latest = {}
    for rec in existing:
        latest[rec.get("card")] = rec.get("sha256")

    cards_dir = out_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    if seals_path.parent != Path(""):
        seals_path.parent.mkdir(parents=True, exist_ok=True)

    appended = 0
    sealed_now = 0
    used_names = set()
    for name, repo, skills in cells:
        fname = _UNSAFE.sub("_", name) + ".json"
        if fname in used_names:
            raise SystemExit("ОТКАЗ: коллизия имён карточек после санитизации: %s" % fname)
        used_names.add(fname)
        card = build_card(name, repo or DEFAULT_REPO, skills)
        data = card_bytes(card)
        (cards_dir / fname).write_bytes(data)
        sealed_now += 1
        digest = sha_hex(data)
        if latest.get(fname) == digest:
            continue  # идемпотентность: карточка не менялась — новых строк нет
        line = {"ts": now_ts(), "card": fname, "sha256": digest, "prev_hash": prev}
        prev = sha_hex(canon(line))
        existing.append(line)
        appended += 1
        latest[fname] = digest

    seals_path.write_text(
        "".join(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n" for rec in existing),
        encoding="utf-8")
    print("клеток в геноме: %d; карточек записано: %d; строк в цепи: %d (дописано %d); "
          "цепь: %s; карточки: %s" % (len(cells), sealed_now, len(existing), appended,
                                      seals_path, cards_dir))
    return 0


VERIFY_SCRIPT = Path(__file__).resolve().with_name("verify_card_seals.py")


def _run_verifier(seals: Path, cards_dir: Path) -> int:
    return subprocess.run([sys.executable, str(VERIFY_SCRIPT),
                           "--seals", str(seals), "--cards-dir", str(cards_dir)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT).returncode


def selftest() -> int:
    """Самотест в tempfile: пломба -> зелёная верификация -> порча карточки ->
    ожидаемый отказ верификатора -> идемпотентность и живой дрейф."""
    with tempfile.TemporaryDirectory(prefix="seal-cards-selftest-") as tmp:
        root = Path(tmp)
        genome = {"cells": [
            {"name": "cell-a", "repo": "rtynbirf/cell-swarm", "skills": ["пульс", "кровь"]},
            {"name": "cell-b"},  # без пина-репо и без навыков: дефолт-репо, skills=[]
            "cell-c",
        ]}
        gpath = root / "swarm.json"
        gpath.write_text(json.dumps(genome, ensure_ascii=False), encoding="utf-8")
        seals = root / "SEALS.jsonl"

        rc = seal_cards(gpath, root, seals)
        if rc != 0:
            print("САМОТЕСТ: пломба вернула %d" % rc)
            return 1
        if _run_verifier(seals, root / "cards") != 0:
            print("САМОТЕСТ: верификатор красный на свежей целой цепи")
            return 1

        # Негатив: портим одну карточку — верификатор обязан отказать (fail-closed).
        victim = root / "cards" / "cell-a.json"
        card = json.loads(victim.read_text(encoding="utf-8"))
        card["name"] = "cell-a-подмена"
        victim.write_bytes(card_bytes(card))
        if _run_verifier(seals, root / "cards") == 0:
            print("САМОТЕСТ: верификатор пропустил порченую карточку — так нельзя")
            return 1
        print("негатив пройден: порченая карточка -> отказ верификатора")

        # Идемпотентность: повторная пломба без изменений генома не дописывает строки.
        before = len(load_seal_lines(seals))
        seal_cards(gpath, root, seals)
        after = len(load_seal_lines(seals))
        if before != after:
            print("САМОТЕСТ: повторная пломба дописала %d строк без дрейфа" % (after - before))
            return 1

        # Дрейф: карточка изменилась -> дописывается новая строка -> снова зелено.
        genome["cells"][0]["skills"].append("новый-навык")
        gpath.write_text(json.dumps(genome, ensure_ascii=False), encoding="utf-8")
        seal_cards(gpath, root, seals)
        if _run_verifier(seals, root / "cards") != 0:
            print("САМОТЕСТ: верификатор красный после честной перепломбы дрейфа")
            return 1
    print("SELFTEST OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Пломба A2A-карточек клеток роя в хеш-цепь SEALS.jsonl (без PKI)")
    parser.add_argument("--genome", default=str(Path(__file__).resolve().parent.parent / "swarm.json"),
                        help="путь к геному swarm.json (по умолчанию — в корне репо)")
    parser.add_argument("--out-dir", default=None,
                        help="каталог для cards/ (вне --selftest обязателен; репо не засоряем)")
    parser.add_argument("--seals", default=None,
                        help="путь к цепи SEALS.jsonl (по умолчанию <out-dir>/SEALS.jsonl)")
    parser.add_argument("--selftest", action="store_true",
                        help="самотест в tempfile: пломба, верификация, негатив, дрейф")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if not args.out_dir:
        parser.error("вне --selftest обязателен --out-dir (постоянные карточки в репо не создаются)")
    out_dir = Path(args.out_dir)
    seals = Path(args.seals) if args.seals else out_dir / "SEALS.jsonl"
    return seal_cards(Path(args.genome), out_dir, seals)


if __name__ == "__main__":
    sys.exit(main())
