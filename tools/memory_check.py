#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory_check.py — сверка памяти роя: файлы с допуском, не истины.

Каждая строка знания — файл memory/MEM-*.json:
  statement   — сама строка знания;
  tol         — допуск на время: сколько живёт (ttl_days);
  acl         — допуск на доступ (волна ×9 «память роя = файлы с допуском»):
                  level — public (весь рой и мир) / cell (клетка-владелец) /
                  swarm (только рой); owner_cell — клетка генома, владеющая
                  доступом (обязательна при level != public); reason — почему
                  такой допуск (обязателен всегда). Входит в хеш-цепь:
                  подмена допуска ловится тампер-очевидностью памяти;
  source      — где проверяемо: repo@ref:path + source_sha256 (обязателен);
  verified_at — когда сверяли;
  prev/hash   — хеш-цепь памяти (GENESIS = 64 нуля).

Токен чтения (волна ×6): каскад GH_TOKEN → GITHUB_TOKEN. Воркфлоу передаёт
secrets.CELL_SWARM_DISPATCH_TOKEN || github.token — публичные источники
читаются штатным job-токеном, ротация PAT больше не слепит память;
fail-closed не ослаблен: несчитанный источник — по-прежнему рана.

Проверки (fail-closed, exit 1 при любой ране):
  1. ЦЕПЬ: hash пересчитывается, prev = хеш предыдущего файла.
  2. СВЕЖЕСТЬ: verified_at + tol.ttl_days >= сегодня — иначе DRIFT.
  3. ИСТОЧНИК (нужна сеть; --no-net пропускает с пометкой): content sha256
     источника по repo/ref/path == source_sha256 — иначе DRIFT.
  4. ДОПУСК: acl валиден (level ∈ {public, cell, swarm}; owner_cell — клетка
     генома при level != public; reason непуст всегда) — иначе РАНА.
"""
import base64
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEM_DIR = ROOT / "memory"
GENESIS = "0" * 64
API = "https://api.github.com"

def canonical_json(obj) -> str:
    """Канон памяти = канон крови (blood.py): сортировка ключей, байты без пробелов."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


ACL_LEVELS = ("public", "cell", "swarm")


def genome_cells() -> set:
    """Имена клеток генома (swarm.json) — только им выдаётся допуск доступа.

    Геном — единственный источник правды о ком-либо в рое: допуск доступа
    для клетки, которой нет в геноме, — это не допуск, а дыра.
    """
    genome_path = ROOT / "swarm.json"
    if not genome_path.exists():
        return set()
    try:
        genome = json.loads(genome_path.read_text("utf-8"))
        return {c["name"] for c in genome.get("cells", [])}
    except (json.JSONDecodeError, KeyError, TypeError):
        return set()


def check_acl(mem: dict, cells: set) -> str | None:
    """Проверка 4 — допуск доступа. Возвращает текст раны или None (чистая функция).

    Правила канона «память роя = файлы с допуском» (волна ×9):
      a) acl обязателен в каждой записи — память без допуска не принимается;
      b) level ∈ {public, cell, swarm};
      c) reason непуст всегда — допуск без причины не выдаётся;
      d) при level != public owner_cell обязателен и обязан быть клеткой генома.
    """
    acl = mem.get("acl")
    mid = mem.get("id", "?")
    if not isinstance(acl, dict):
        return f"{mid}: acl отсутствует или не объект — память без допуска не принимается"
    level = acl.get("level")
    if level not in ACL_LEVELS:
        return f"{mid}: acl.level={level!r} вне канона {ACL_LEVELS} — допуск не выдаётся"
    reason = acl.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return f"{mid}: acl.reason пуст — допуск без причины не выдаётся"
    if level != "public":
        owner = acl.get("owner_cell")
        if not isinstance(owner, str) or not owner.strip():
            return f"{mid}: level={level} без owner_cell — допуск не к кому привязать"
        if cells and owner not in cells:
            return f"{mid}: acl.owner_cell={owner!r} нет в геноме — допуск чужаку не выдаётся"
    return None


def api_raw(repo, ref, path, token):
    req = urllib.request.Request(
        f"{API}/repos/{repo}/contents/{path}?ref={ref}",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req) as r:
        return base64.b64decode(json.load(r)["content"])


def main():
    no_net = "--no-net" in sys.argv
    files = sorted(MEM_DIR.glob("MEM-*.json"))
    if not files:
        sys.exit("ФАКТ: память пуста — это не рана, но и не память")
    prev = GENESIS
    wounds = 0
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    now = datetime.now(timezone.utc)
    known_cells = genome_cells()
    for f in files:
        mem = json.loads(f.read_text("utf-8"))
        body = {k: v for k, v in mem.items() if k != "hash"}
        h = hashlib.sha256(canonical_json(body).encode()).hexdigest()
        mid = mem["id"]
        if h != mem.get("hash"):
            print(f"РАНА: {mid}: hash не сходится (файл правлен вне протокола)")
            wounds += 1
            continue
        if mem.get("prev") != prev:
            print(f"РАНА: {mid}: prev != хеш предыдущей записи (память разорвана)")
            wounds += 1
            continue
        prev = h
        acl_wound = check_acl(mem, cells=known_cells)
        if acl_wound:
            print(f"РАНА: {acl_wound}")
            wounds += 1
            continue
        born = datetime.strptime(mem["verified_at"], "%Y-%m-%dT%H:%M:%S%z")
        ttl = timedelta(days=mem["tol"]["ttl_days"])
        if now > born + ttl:
            print(f"ДРЕЙФ: {mid}: знание просрочено "
                  f"(verified_at={mem['verified_at'][:10]}, ttl={mem['tol']['ttl_days']}d) — пересверять")
            wounds += 1
            continue
        src = mem["source"]
        if no_net:
            print(f"ОК(офлайн): {mid}: цепь+свежесть, источник не сверялся (--no-net)")
            continue
        if not token:
            print(f"РАНА: {mid}: сеть доступна, но GH_TOKEN нет — источник не сверян")
            wounds += 1
            continue
        try:
            content = api_raw(src["repo"], src["ref"], src["path"], token)
            got = hashlib.sha256(content).hexdigest()
            if got != src["source_sha256"]:
                print(f"ДРЕЙФ: {mid}: источник {src['repo']}@{src['ref'][:7]}:{src['path']} "
                      f"изменился (sha256 не совпал) — знание пересверять")
                wounds += 1
                continue
            print(f"ОК: {mid}: цепь+свежесть+источник CONFIRMED")
        except Exception as e:  # noqa: BLE001 — fail-closed на любую рану связи
            print(f"РАНА: {mid}: источник недоступен: {e}")
            wounds += 1
    print(f"ФАКТ: память {len(files)} записей, ран {wounds}")
    sys.exit(1 if wounds else 0)


if __name__ == "__main__":
    main()
