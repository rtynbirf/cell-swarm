#!/usr/bin/env python3
"""genome_drift.py — детектор/догонщик дрейфа пинов генома (П-05 «Геном как локфайл»,
polimat-hub #23, волна WAVE9-2B).

Геном — локфайл: каждый пин swarm.json сверяется с живым HEAD отслеживаемого
ref клетки. Отслеживаемый ref задаётся полем pin_ref клетки (singulyar →
"rumu" — «пин следит за телом», ADR-0011/0012; остальные клетки → "main").
Источник истины — GitHub API GET /repos/<owner>/<repo>/branches/<ref>;
если API не пустил (анонимный лимит 60/ч даёт HTTP 403, сеть недоступна),
HEAD берётся вторым живым транспортом — git ls-remote refs/heads/<ref> (тот
же SHA, независимый транспорт; оба метода сверяются между собой в СВЕРКА-
ПИНОВ-*.md). Клетка, которую не удалось сверить ни одним транспортом, — тоже
дрейф: не подтверждённая свежесть не считается свежестью (fail-closed).

Целостность: integrity = "sha256-" + sha256(строки полного пина, utf-8).
Конвенция зафиксирована в swarm.json полем integrity_method. Расхождение
integrity с пином — тоже дрейф: детектор ловит пины, переписанные мимо
формулы (например, родным контуром scripts/pin.py, который integrity не
пересчитывает), и --fix приводит их в порядок.

Режимы:
  --check  печатает JSON-отчёт дрейфа в stdout (машинный, single object);
           exit 0 — все пины свежи; exit 2 — есть дрейф или ошибки сверки.
  --fix    переписывает пины на живые HEAD, пересчитывает integrity,
           обновляет fetched_at (клеткам, по которым прошла живая сверка,
           и геному), поднимает genome_version (patch +1) — только если
           геном действительно изменился («дрейфа нет — коммита нет»).
           Запись атомарная (tmp + os.replace), после записи файл
           валидируется json.load. Клетка с ошибкой сверки не трогается.

Авторизация: если задана переменная окружения GITHUB_TOKEN — заголовок
Authorization: Bearer; иначе анонимные запросы (репо роя публичные).
Токен никогда не печатается и не попадает в отчёт.

Зависимости: чистый stdlib (urllib, subprocess для запасного ls-remote).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENOME = ROOT / "swarm.json"

API_BASE = "https://api.github.com"
INTEGRITY_METHOD = (
    "sha256(hex(utf8(commit_sha))) — свердываем содержимое через пин-сумму"
)
EXIT_FRESH = 0
EXIT_DRIFT = 2


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def integrity_of(pin: str) -> str:
    """integrity клетки: sha256 от строки полного пина (hex, utf-8)."""
    return "sha256-" + hashlib.sha256(pin.encode("utf-8")).hexdigest()


def _slug(repo_url: str) -> str:
    return str(repo_url).removeprefix("https://github.com/").removesuffix(".git")


def api_branch_head(repo_url: str, ref: str, token: str | None) -> str | None:
    """Живой HEAD ветки через GitHub API; None — API не пустил (лимит/сеть)."""
    url = f"{API_BASE}/repos/{_slug(repo_url)}/branches/{ref}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "cell-swarm-genome-drift",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError,
            TimeoutError, json.JSONDecodeError):
        return None
    sha = (data.get("commit") or {}).get("sha")
    return sha if isinstance(sha, str) and sha else None


def ls_remote_head(repo_url: str, ref: str) -> str:
    """Живой HEAD ветки вторым транспортом — git ls-remote refs/heads/<ref>."""
    out = subprocess.run(
        ["git", "ls-remote", str(repo_url), f"refs/heads/{ref}"],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"ls-remote {ref}: {out.stderr.strip()[:120] or 'пусто'}")
    return out.stdout.strip().splitlines()[0].split()[0]


def live_head(repo_url: str, ref: str, token: str | None) -> tuple[str, str]:
    """(sha, источник): API приоритетен, ls-remote — живой запасной транспорт."""
    sha = api_branch_head(repo_url, ref, token)
    if sha:
        return sha, "api"
    return ls_remote_head(repo_url, ref), "ls-remote"


def _ref_of(cell: dict) -> tuple[str, str]:
    """(ref, источник правила): поле pin_ref; без него — main по умолчанию."""
    ref = cell.get("pin_ref")
    return (str(ref), "pin_ref") if ref else ("main", "default")


def bump_patch(version: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(version))
    if not match:
        raise SystemExit(
            f"ОТКАЗ: genome_version={version!r} не semver X.Y.Z — patch не поднимется"
        )
    return f"{match.group(1)}.{match.group(2)}.{int(match.group(3)) + 1}"


def _sweep(genome: dict, token: str | None) -> tuple[list[dict], list[dict]]:
    """Живая сверка всех клеток. Возвращает (rows, errors); rows — по клеткам."""
    rows: list[dict] = []
    errors: list[dict] = []
    for cell in genome["cells"]:
        ref, ref_source = _ref_of(cell)
        row = {
            "name": cell.get("name"),
            "ref": ref,
            "ref_source": ref_source,
            "pin": cell.get("pin"),
            "live": None,
            "source": None,
            "status": None,
            "integrity_stale": cell.get("integrity") != integrity_of(cell["pin"]),
        }
        try:
            sha, source = live_head(cell["repo"], ref, token)
        except Exception as exc:  # noqa: BLE001 — поимённый отчёт, сверка продолжается
            row["status"] = "error"
            row["error"] = str(exc)[:200]
            errors.append({"name": row["name"], "ref": ref, "error": row["error"]})
            rows.append(row)
            continue
        row["live"] = sha
        row["source"] = source
        row["status"] = "fresh" if (sha == cell["pin"] and not row["integrity_stale"]) else "drift"
        rows.append(row)
    return rows, errors


def _emit(report: dict) -> None:
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def cmd_check(genome: dict, token: str | None) -> int:
    rows, errors = _sweep(genome, token)
    drifted = [r for r in rows if r["status"] != "fresh"]
    report = {
        "tool": "genome_drift",
        "mode": "check",
        "genome_version": genome.get("genome_version"),
        "checked_at": _now_iso(),
        "integrity_method": INTEGRITY_METHOD,
        "cells_total": len(rows),
        "fresh_count": len(rows) - len(drifted),
        "drifted": [r["name"] for r in rows if r["status"] == "drift"],
        "errors": errors,
        "drift": bool(drifted),
        "cells": rows,
    }
    _emit(report)
    return EXIT_DRIFT if drifted else EXIT_FRESH


def cmd_fix(genome: dict, token: str | None) -> int:
    rows, errors = _sweep(genome, token)
    today = _today()
    changed: list[str] = []
    unchanged: list[str] = []
    version_before = genome.get("genome_version")

    for row in rows:
        cell = next(c for c in genome["cells"] if c["name"] == row["name"])
        if row["status"] == "error":
            # fail-closed: клетку не подтвердили живым HEAD — пин по памяти не пишется
            unchanged.append(cell["name"])
            continue
        cell_changed = False
        if cell["pin"] != row["live"]:
            cell["pin"] = row["live"]
            cell_changed = True
        fresh_integrity = integrity_of(cell["pin"])
        if cell.get("integrity") != fresh_integrity:
            cell["integrity"] = fresh_integrity
            cell_changed = True
        if cell.get("fetched_at") != today:
            cell["fetched_at"] = today
            cell_changed = True
        if cell_changed:
            changed.append(cell["name"])
        else:
            unchanged.append(cell["name"])

    written = bool(changed)
    if written:
        genome["genome_version"] = bump_patch(genome.get("genome_version", "0.0.0"))
        genome["fetched_at"] = today
        genome["fetch_method"] = (
            "GitHub API /repos/<owner>/<repo>/branches/<pin_ref> "
            "(fallback: git ls-remote refs/heads/<pin_ref>, SHA эквивалентны) — "
            f"живая сверка genome_drift.py на {today}"
        )

    report = {
        "tool": "genome_drift",
        "mode": "fix",
        "fixed_at": _now_iso(),
        "genome_version_before": version_before,
        "genome_version_after": genome.get("genome_version"),
        "changed": changed,
        "unchanged": unchanged,
        "errors": errors,
        "written": written,
    }

    if not written:
        _emit(report)
        print("дрейфа нет — геном свеж, запись не производилась", file=sys.stderr)
        return EXIT_DRIFT if errors else EXIT_FRESH

    # атомарная запись: tmp рядом с геномом → валидация → os.replace
    tmp = GENOME.with_name(GENOME.name + ".tmp")
    tmp.write_text(
        json.dumps(genome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    json.load(tmp.open(encoding="utf-8"))  # валидация записанного tmp
    os.replace(tmp, GENOME)
    json.load(GENOME.open(encoding="utf-8"))  # валидация генома после записи

    _emit(report)
    print(
        f"геном обновлён: {len(changed)} клеток догнано живым HEAD, "
        f"genome_version {version_before} → {genome['genome_version']}",
        file=sys.stderr,
    )
    return EXIT_DRIFT if errors else EXIT_FRESH


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a in ("--check", "--fix")]
    if len(args) != 1 or len(argv) != len(args) + 1:
        print(
            "использование: genome_drift.py --check | --fix\n"
            "  --check  JSON-отчёт дрейфа; exit 0 свеж, exit 2 дрейф\n"
            "  --fix    догнать пины живым HEAD (атомарная запись)",
            file=sys.stderr,
        )
        return 1
    try:
        genome = json.loads(GENOME.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ОТКАЗ: геном {GENOME} нечитаем: {exc}", file=sys.stderr)
        return 1
    token = os.environ.get("GITHUB_TOKEN") or None
    return cmd_check(genome, token) if args[0] == "--check" else cmd_fix(genome, token)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
