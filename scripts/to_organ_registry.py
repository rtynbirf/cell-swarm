#!/usr/bin/env python3
"""to_organ_registry.py — экспорт клеток роя в словарь реестра органов дома.

Формат — flow-style строки organs/registry.yaml дома (прочитан в клоне
2026-11-05). Это ЗАГОТОВКА для ритуала ADR-0005 дома (перепроверка лицензии
живым API → живой пульс → приёмка в CI), не сам ритуал: до ритуала статус —
proposal, лицензии — только с пометкой честности.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def yaml_quote(value: str) -> str:
    value = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{value}'" if any(ch in value for ch in ":{}[],&*#?|-<>=!%@\"`\n") else value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="куда писать (по умолчанию stdout)")
    args = parser.parse_args()

    genome = json.loads((ROOT / "swarm.json").read_text(encoding="utf-8"))
    today = genome["fetched_at"]  # дата пинов, не дата экспорта — честное происхождение
    lines = [
        f"# Реестр органов из роя cell-swarm — заготовка для ритуала ADR-0005 дома.",
        f"# Пины живые (genom fetched_at {genome['fetched_at']}); лицензии — только с пометкой честности",
        f"# (инвариант 5 дома): до перепроверки живым API статус не поднимается выше proposal.",
        "organs:",
    ]
    for cell in genome["cells"]:
        slug = cell["repo"].removeprefix("https://github.com/").removesuffix(".git")
        if cell.get("bridge"):
            continue  # дом сам себе реестр; пир дома не орган дома
        fields = [
            f"repo: {slug}",
            f"system: {cell.get('system_pre', 'substrate')}",
            f"role: {yaml_quote(cell['role'])}",
            f"license_pre: {yaml_quote(cell['license_pre'])}",
            "mode: dependency",
            "status: proposal",
            f"pin: {cell['pin']}",
            f"pin_date: {today}",
        ]
        lines.append("  - {" + ", ".join(fields) + "}")
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"записано: {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
