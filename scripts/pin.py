#!/usr/bin/env python3
"""pin.py — обновление генома живым источником (по памяти пин не вносится).

make pins            → git ls-remote HEAD для каждой клетки; --write обновляет
                       swarm.json и ставит fetched_at = сегодня.
make licenses        → --licenses: добор лицензий живым GitHub API (нужен токен
                       GITHUB_TOKEN: анонимный лимит 60/ч честно называется).
make pins-seals      → --seals-root: офлайн, без сети — пересчитать корень
                       пломб-цепи карточек клеток (Э-2.2, #9) и вписать/обновить
                       аддитивное поле cards_seals в геноме. Саму цепь SEALS.jsonl
                       пин-инструмент НЕ пишет: живой диспатч cards-seals работает
                       в tempfile, константная цепь появится в репо отдельной
                       аккуратной операцией волны после живого диспатча.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENOME = ROOT / "swarm.json"
SEALS_PATH = ROOT / "SEALS.jsonl"   # константная цепь карточек: корень репо (после живого диспатча)

SEALS_FILE = "SEALS.jsonl"
SEALS_GENESIS = "0" * 64         # genesis-хеш цепи пломбира (tools/seal_agent_cards.py)
SEALS_FIELDS = ("ts", "card", "sha256", "prev_hash")
_SEALS_SHAHEX = re.compile(r"^[0-9a-f]{64}$")
SEALS_NOT_STARTED = (
    "цепь ещё не начата — первый живой диспатч её начнёт; константная SEALS.jsonl "
    "появится в репо отдельной аккуратной операцией волны после живого диспатча, "
    "пин-инструмент сам цепь не пишет"
)


def ls_remote_head(url: str, ref: str = "HEAD") -> str:
    # Волна ×9 (2026-11-09): контракт клетки может требовать ветку-тело,
    # а не default (singulyar: «пин следит за телом» = refs/heads/rumu).
    ref = ref or "HEAD"
    out = subprocess.run(["git", "ls-remote", url, ref], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"ls-remote {url} {ref}: {out.stderr.strip()[:120]}")
    return out.stdout.split()[0]


def github_license(repo_url: str, token: str | None) -> str:
    if not token:
        raise RuntimeError("GITHUB_TOKEN не задан — анонимный лимит 60/ч; токен только env, не в кровь")
    slug = repo_url.removeprefix("https://github.com/").removesuffix(".git")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{slug}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": "cell-swarm-pin"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    spdx = (data.get("license") or {}).get("spdx_id")
    return f"{spdx} (живой API, дата {date.today().isoformat()})" if spdx else \
        f"NOASSERTION (живой API: лицензии нет, дата {date.today().isoformat()})"


# --- корень пломб-цепи карточек (Э-2.2, #9, волна ×6) ---

def _canon(obj) -> bytes:
    """Дубликат формулы сцепки пломбира/верификатора: пин не импортирует
    проверяемых («доверие не импортируют»), формула совпадает байт-в-байт
    и сверяется тестами (tests/test_cards_seals_pin.py)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_chain(seals_path: Path) -> list:
    """Читает цепь пломб и проверяет сцепку; рваная — SystemExit (fail-closed).

    Сцепка: prev_hash строки i == sha256 канон-сериализации строки i-1
    (genesis = 64 нуля). Совпадение карточек с их sha256 — работа верификатора
    (tools/verify_card_seals.py, ему нужен каталог карточек); здесь проверяется
    только сама цепь, чтобы не запинить рваную.
    """
    lines = []
    for num, raw in enumerate(seals_path.read_text(encoding="utf-8").splitlines(), 1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        try:
            rec = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"ОТКАЗ: {seals_path} строка {num} не JSON ({exc}) — пин рваной цепи не ставится")
        if not isinstance(rec, dict):
            raise SystemExit(f"ОТКАЗ: {seals_path} строка {num} — не объект")
        for field in SEALS_FIELDS:
            if not isinstance(rec.get(field), str):
                raise SystemExit(f"ОТКАЗ: {seals_path} строка {num}: поле {field} отсутствует или не строка")
        if not _SEALS_SHAHEX.match(rec["sha256"]) or not _SEALS_SHAHEX.match(rec["prev_hash"]):
            raise SystemExit(f"ОТКАЗ: {seals_path} строка {num}: sha256/prev_hash не 64 hex")
        lines.append(rec)
    prev = SEALS_GENESIS
    for i, rec in enumerate(lines, 1):
        if rec["prev_hash"] != prev:
            raise SystemExit(f"ОТКАЗ: цепь {seals_path} рвана на строке {i} (prev_hash не сходится) — "
                             "пин рваной цепи не ставится, продлевать/переписывать молча запрещено")
        prev = _sha_hex(_canon(rec))
    return lines


def seals_field(seals_path: Path, today: str | None = None) -> dict:
    """Поле cards_seals — корень пломб-цепи карточек в форме генома.

    Цепи нет (файла нет или он пуст) — честное «не начато»: tip=null с note.
    Цепь цела — {seals, tip, cards, updated_at}: tip = sha256 канон-сериализации
    последней строки (ровно тот prev_hash, которым пломбир продолжит цепь);
    cards — число РАЗНЫХ карточек в цепи (дрейф карточки даёт несколько строк).
    """
    today = today or date.today().isoformat()
    if not seals_path.exists():
        return {"seals": SEALS_FILE, "tip": None, "note": SEALS_NOT_STARTED, "updated_at": today}
    lines = _load_chain(seals_path)
    if not lines:
        return {"seals": SEALS_FILE, "tip": None, "note": SEALS_NOT_STARTED, "updated_at": today}
    return {"seals": SEALS_FILE,
            "tip": _sha_hex(_canon(lines[-1])),
            "cards": len({rec["card"] for rec in lines}),
            "updated_at": today}


def _seals_core(field: dict) -> dict:
    """Содержательное ядро поля без календарного updated_at (для идемпотентности)."""
    return {key: value for key, value in field.items() if key != "updated_at"}


def apply_cards_seals(genome: dict, seals_path: Path, today: str | None = None) -> bool:
    """Пересчитывает cards_seals и вписывает в геном. True — поле изменилось.

    Аддитивно и идемпотентно: пока содержательное ядро поля не изменилось,
    поле не переписывается — updated_at не катится календарём без факта.
    Рваная цепь — SystemExit наружу: геном остаётся нетронутым (fail-closed).
    """
    fresh = seals_field(seals_path, today=today)
    current = genome.get("cards_seals")
    if current is not None and _seals_core(current) == _seals_core(fresh):
        return False
    genome["cards_seals"] = fresh
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="обновить пины в swarm.json")
    parser.add_argument("--licenses", action="store_true", help="добрать лицензии живым API (GITHUB_TOKEN)")
    parser.add_argument("--seals-root", action="store_true",
                        help="офлайн, без сети: пересчитать cards_seals (корень пломб-цепи карточек, Э-2.2 #9)")
    args = parser.parse_args()

    genome = json.loads(GENOME.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    changed = 0

    if args.seals_root:
        # Офлайн-операция волны: только корень пломб-цепи, живые пины не трогаем;
        # fetched_at не пишем — сеть не читалась, «живых данных» нет.
        stale = apply_cards_seals(genome, SEALS_PATH)
        field = genome.get("cards_seals") or {}
        print(f"  cards_seals                     tip={field.get('tip') or 'null (цепь не начата)'}; "
              f"карточек: {field.get('cards', 0)}")
        if args.write and stale:
            GENOME.write_text(json.dumps(genome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("\nгеном обновлён: cards_seals (офлайн; fetched_at не тронут — сеть не читалась)")
        elif args.write:
            print("\nполе cards_seals без изменений — геном свеж")
        else:
            print("\n(dry-run; --write запишет)")
        return 0

    if args.licenses:
        token = None
        import os
        token = os.environ.get("GITHUB_TOKEN")
        for cell in genome["cells"]:
            try:
                license_pre = github_license(cell["repo"], token)
            except Exception as exc:  # noqa: BLE001 — поимённый отчёт, продолжаем
                print(f"  {cell['name']:<32} лицензия: НЕ ВЗЯТА ({exc})")
                continue
            print(f"  {cell['name']:<32} {license_pre}")
            if args.write:
                cell["license_pre"] = license_pre
                changed += 1

    if not args.licenses or True:  # пины — основная работа цели
        for cell in genome["cells"]:
            try:
                sha = ls_remote_head(cell["repo"], cell.get("pin_ref") or "HEAD")
            except Exception as exc:  # noqa: BLE001
                print(f"  {cell['name']:<32} пин: НЕ ВЗЯТ ({exc})")
                continue
            status = "same" if sha == cell["pin"] else f"drift {cell['pin'][:8]} → {sha[:8]}"
            print(f"  {cell['name']:<32} {status}")
            if args.write and sha != cell["pin"]:
                cell["pin"] = sha
                changed += 1

    # Волна ×6: корень пломб-цепи карточек (Э-2.2, #9) — аддитивное поле генома,
    # вычисляется офлайн ПОСЛЕ регенерации пинов; рваная цепь — SystemExit,
    # геном не пишется вовсе (fail-closed).
    seals_stale = apply_cards_seals(genome, SEALS_PATH)
    if seals_stale:
        field = genome["cards_seals"]
        print(f"  cards_seals                     tip={field['tip'] or 'null (цепь не начата)'}; "
              f"карточек: {field.get('cards', 0)}")

    if args.write and (changed or seals_stale):
        if changed:
            genome["fetched_at"] = today
            genome["fetch_method"] = f"git ls-remote HEAD + GitHub API (где взялось) — живые данные на {today}"
        GENOME.write_text(json.dumps(genome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nгеном обновлён: {changed} изменений пинов, cards_seals "
              f"{'обновлено' if seals_stale else 'без изменений'}, "
              f"fetched_at={genome.get('fetched_at', '(не тронут)')}")
    elif not args.write:
        print("\n(dry-run; --write запишет)")
    else:
        print("\nдрейфа нет — геном свеж")
    return 0


if __name__ == "__main__":
    sys.exit(main())
