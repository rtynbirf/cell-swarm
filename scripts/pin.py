#!/usr/bin/env python3
"""pin.py — обновление генома живым источником (по памяти пин не вносится).

make pins            → git ls-remote HEAD для каждой клетки; --write обновляет
                       swarm.json и ставит fetched_at = сегодня.
make licenses        → --licenses: добор лицензий живым GitHub API (нужен токен
                       GITHUB_TOKEN: анонимный лимит 60/ч честно называется).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENOME = ROOT / "swarm.json"


def ls_remote_head(url: str) -> str:
    out = subprocess.run(["git", "ls-remote", url, "HEAD"], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"ls-remote {url}: {out.stderr.strip()[:120]}")
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="обновить пины в swarm.json")
    parser.add_argument("--licenses", action="store_true", help="добрать лицензии живым API (GITHUB_TOKEN)")
    args = parser.parse_args()

    genome = json.loads(GENOME.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    changed = 0

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
                sha = ls_remote_head(cell["repo"])
            except Exception as exc:  # noqa: BLE001
                print(f"  {cell['name']:<32} пин: НЕ ВЗЯТ ({exc})")
                continue
            status = "same" if sha == cell["pin"] else f"drift {cell['pin'][:8]} → {sha[:8]}"
            print(f"  {cell['name']:<32} {status}")
            if args.write and sha != cell["pin"]:
                cell["pin"] = sha
                changed += 1

    if args.write and changed:
        genome["fetched_at"] = today
        genome["fetch_method"] = f"git ls-remote HEAD + GitHub API (где взялось) — живые данные на {today}"
        GENOME.write_text(json.dumps(genome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nгеном обновлён: {changed} изменений, fetched_at={today}")
    elif not args.write:
        print("\n(dry-run; --write запишет)")
    else:
        print("\nдрейфа нет — геном свеж")
    return 0


if __name__ == "__main__":
    sys.exit(main())
