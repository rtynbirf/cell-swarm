#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Верификация константной цепи SEALS.jsonl против карточек живого генома.

Карточки в репо не живут (канон волны ×5: живой цикл пишет в tempfile) —
восстанавливаем их из генома на месте и сверяем с константной цепью:

    генератор (tempfile: карточки из swarm.json)
        → верификатор (константная SEALS.jsonl против восстановленных)

Обе стороны вызываются subprocess'ом — доверие не импортируют, проверяющий
не зависит от проверяемого. Отказ — exit 1, fail-closed, без сети.

Использование:
  python3 tools/verify_cards_from_genome.py [--genome PATH] [--seals PATH]
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

GEN = Path(__file__).resolve().with_name("seal_agent_cards.py")
VER = Path(__file__).resolve().with_name("verify_card_seals.py")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Константная цепь пломб против карточек живого генома")
    parser.add_argument("--genome", default=str(root / "swarm.json"))
    parser.add_argument("--seals", default=str(root / "SEALS.jsonl"))
    args = parser.parse_args()

    seals = Path(args.seals)
    if not seals.is_file():
        print("ОТКАЗ: константная цепь %s не существует" % seals)
        return 1

    with tempfile.TemporaryDirectory(prefix="cards-from-genome-") as tmp:
        # 1) карточки из живого генома — в tempfile; временная цепь уходит
        #    в tempfile же: константная цепь не переписывается никогда.
        r = subprocess.run(
            [sys.executable, str(GEN), "--genome", args.genome,
             "--out-dir", tmp, "--seals", str(Path(tmp) / "SEALS.tmp.jsonl")],
            capture_output=True, text=True)
        if r.returncode != 0:
            print("ОТКАЗ: карточки из генома не собрались:\n%s%s"
                  % (r.stdout, r.stderr))
            return 1
        # 2) константная цепь против восстановленных карточек.
        r = subprocess.run(
            [sys.executable, str(VER), "--seals", str(seals),
             "--cards-dir", str(Path(tmp) / "cards")],
            capture_output=True, text=True)
        if r.returncode != 0:
            print("ОТКАЗ: константная цепь не сходится с карточками "
                  "живого генома:\n%s%s" % (r.stdout, r.stderr))
            return 1
    print("ФАКТ: константная цепь SEALS.jsonl == карточкам живого генома 🟢")
    return 0


if __name__ == "__main__":
    sys.exit(main())
