#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Верификатор SEALS-цепи карточек клеток роя cell-swarm (Э-2.2, волна ×5).

Fail-closed: любое расхождение — красный exit 1. Проверяет:
1. Каждая строка SEALS.jsonl — объект с полями ts/card/sha256/prev_hash,
   где sha256 и prev_hash — 64 hex-символа.
2. Сцепка цепи: prev_hash строки i == sha256 канонической сериализации строки
   i-1; у первой строки (genesis) prev_hash = 64 нуля.
3. Карточки: для каждой карточки берётся последняя её строка в цепи (пин);
   sha256 текущих байтов файла обязан совпасть; файл обязан лежать внутри
   --cards-dir (выход за каталог — отказ).
4. Покрытие: каждый *.json в --cards-dir имеет хотя бы одну строку цепи —
   карточка без пломбы не проходит свёртку при рождении (fail-closed).

Верификатор сознательно НЕ импортирует пломбир: хелперы канонизации и sha256
продублированы здесь — проверяющий независим от проверяемого.

Использование:
  python3 tools/verify_card_seals.py --seals PATH --cards-dir DIR
  python3 tools/verify_card_seals.py --selftest
"""
import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

GENESIS_HASH = "0" * 64
_SHAHEX = re.compile(r"^[0-9a-f]{64}$")
FIELDS = ("ts", "card", "sha256", "prev_hash")


def canon(obj) -> bytes:
    """Дубликат канонизации пломбира (байт-в-байт та же формула сцепки)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_lines(path: Path) -> list:
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


def verify(seals_path: Path, cards_dir: Path) -> list:
    """Возвращает список проблем; пустой список = цепь и карточки целы."""
    errors = []
    lines = load_lines(seals_path)
    prev = GENESIS_HASH
    latest = {}  # card -> sha256 последней строки этой карточки
    for i, rec in enumerate(lines, 1):
        for field in FIELDS:
            if not isinstance(rec.get(field), str):
                errors.append("строка %d: поле %s отсутствует или не строка" % (i, field))
        if errors and errors[-1].startswith("строка %d" % i):
            continue
        if not _SHAHEX.match(rec["sha256"]):
            errors.append("строка %d: sha256 не 64 hex" % i)
        if not _SHAHEX.match(rec["prev_hash"]):
            errors.append("строка %d: prev_hash не 64 hex" % i)
        else:
            if rec["prev_hash"] != prev:
                errors.append("строка %d: сцепка порвана (prev_hash не равен хешу строки %d)"
                              % (i, i - 1))
            prev = sha_hex(canon(rec))
        latest[rec["card"]] = rec["sha256"]

    if not lines and not errors:
        if any(cards_dir.glob("*.json")):
            errors.append("цепь пуста, а карточки есть: ни одна не запломбирована")

    seen_on_disk = set()
    if cards_dir.is_dir():
        for card_file in sorted(cards_dir.glob("*.json")):
            name = card_file.name
            seen_on_disk.add(name)
            if name not in latest:
                errors.append("карточка %s: нет ни одной строки в цепи (fail-closed)" % name)
                continue
            data = card_file.read_bytes()
            if sha_hex(data) != latest[name]:
                errors.append("карточка %s: sha256 не совпал с пином цепи (дрейф или подмена)" % name)
    else:
        errors.append("каталог карточек %s не существует" % cards_dir)

    for name in latest:
        if name not in seen_on_disk:
            errors.append("строка цепи указывает на отсутствующую карточку %s" % name)
    return errors


def _seal_line(ts: str, card: str, data: bytes, prev: str) -> dict:
    """Мини-пломбир для самотеста (та же формула строки, что у генератора)."""
    return {"ts": ts, "card": card, "sha256": sha_hex(data), "prev_hash": prev}


def selftest() -> int:
    """Самотест в tempfile: зелёная цепь обязана пройти, три порчи — обязаны попасть."""
    with tempfile.TemporaryDirectory(prefix="verify-seals-selftest-") as tmp:
        root = Path(tmp)
        cards = root / "cards"
        cards.mkdir()
        cards_a = b'{"identity": {"cell": "a", "repo": "rtynbirf/cell-swarm"}, "name": "a"}\n'
        cards_b = b'{"identity": {"cell": "b", "repo": "rtynbirf/cell-swarm"}, "name": "b"}\n'
        (cards / "a.json").write_bytes(cards_a)
        (cards / "b.json").write_bytes(cards_b)
        seals = root / "SEALS.jsonl"
        line1 = _seal_line("2026-11-09T00:00:00Z", "a.json", cards_a, GENESIS_HASH)
        line2 = _seal_line("2026-11-09T00:01:00Z", "b.json", cards_b, sha_hex(canon(line1)))
        seals.write_text(json.dumps(line1, sort_keys=True) + "\n" +
                         json.dumps(line2, sort_keys=True) + "\n", encoding="utf-8")

        if verify(seals, cards):
            print("САМОТЕСТ: зелёная цепь не прошла: %s" % verify(seals, cards))
            return 1

        # Негатив 1: дрейф карточки (подмена байтов).
        (cards / "b.json").write_bytes(cards_b + "дрейф\n".encode("utf-8"))
        if not verify(seals, cards):
            print("САМОТЕСТ: подменённая карточка прошла верификацию")
            return 1
        (cards / "b.json").write_bytes(cards_b)

        # Негатив 2: рваная сцепка (порченый prev_hash второй строки).
        broken = dict(line2, prev_hash="f" * 64)
        seals.write_text(json.dumps(line1, sort_keys=True) + "\n" +
                         json.dumps(broken, sort_keys=True) + "\n", encoding="utf-8")
        if not verify(seals, cards):
            print("САМОТЕСТ: рваная сцепка прошла верификацию")
            return 1
        seals.write_text(json.dumps(line1, sort_keys=True) + "\n" +
                         json.dumps(line2, sort_keys=True) + "\n", encoding="utf-8")

        # Негатив 3: карточка без пломбы (не проходит свёртку).
        (cards / "c.json").write_bytes(b'{"name": "c"}\n')
        if not verify(seals, cards):
            print("САМОТЕСТ: незапломбированная карточка прошла верификацию")
            return 1
        (cards / "c.json").unlink()
    print("SELFTEST OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed верификатор хеш-цепи SEALS.jsonl карточек клеток")
    parser.add_argument("--seals", default="SEALS.jsonl", help="путь к цепи (по умолчанию SEALS.jsonl)")
    parser.add_argument("--cards-dir", default="cards", help="каталог карточек (по умолчанию cards/)")
    parser.add_argument("--selftest", action="store_true",
                        help="самотест в tempfile: зелёная цепь + три негатива")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    problems = verify(Path(args.seals), Path(args.cards_dir))
    if problems:
        print("ВЕРДИКТ: 🔴 цепь SEALS не принята (fail-closed), проблем: %d" % len(problems))
        for problem in problems:
            print("  - %s" % problem)
        return 1
    print("ВЕРДИКТ: 🟢 цепь цела, все карточки совпадают с пинами")
    return 0


if __name__ == "__main__":
    sys.exit(main())
