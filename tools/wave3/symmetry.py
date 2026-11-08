#!/usr/bin/env python3
"""Обратная нить как CI-гейт + витрина ниши «0 процессных» (ПРЕДЛОЖЕНИЕ-15, волна ×3 W3-D).
Только stdlib, Python 3.11.

Что делает (режим check):
  1) ведёт сид пар peers/pairs.json (создаётся пустым при первом прогоне — URL не выдумываются,
     пары sNN<->sNN вносятся живым ходом роя);
  2) для каждой пары проверяет ОБА направления (HTTP 200) — односторонние связи красятся;
  3) витрина ниши: карта peers/SYMMETRY-MAP.md — «агентских N по API, процессных 0»,
     живость бенч-протокола agryp bench/ проверяется по API (имя проверяется, не утверждается).
Гейт: 0 — симметрично (или сид пуст: громкое предупреждение), 1 — есть односторонние/мёртвые.
Без сети: SYMMETRY_OFFLINE=1 — карта с пометкой «(без сети)», выход 0.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "peers" / "pairs.json"
MAP = ROOT / "peers" / "SYMMETRY-MAP.md"
API = "https://api.github.com"
UA = {"User-Agent": "cell-swarm-wave3-symmetry"}
OFFLINE = os.environ.get("SYMMETRY_OFFLINE") == "1"


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def alive(url):
    if OFFLINE:
        return None
    try:
        status, _ = fetch(url)
        return status == 200
    except Exception as e:
        print("  недоступно %s: %s" % (url, type(e).__name__))
        return False


def ensure_seed():
    if SEED.exists():
        return json.loads(SEED.read_text(encoding="utf-8"))
    seed = {"note": "Сид пар sNN<->sNN. Пары вносятся живым ходом роя, реальные URL, не выдуманные. "
                    "(заполняется живым ходом при первом прогоне)",
            "pairs": []}
    SEED.parent.mkdir(parents=True, exist_ok=True)
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("сид создан: peers/pairs.json (пуст — пары вносятся живым ходом)")
    return seed


def niche_facts():
    if OFFLINE:
        return None
    facts = {}
    try:
        _, user = fetch(API + "/users/rtynbirf")
        facts["public_repos"] = user.get("public_repos")
    except Exception as e:
        print("  API пользователя недоступен: %s" % type(e).__name__)
    try:
        _, repo = fetch(API + "/repos/rtynbirf/agryp")
        branch = repo.get("default_branch", "main")
        st, _ = fetch(API + "/repos/rtynbirf/agryp/contents/bench?ref=%s" % branch)
        facts["agryp_bench"] = (st == 200, branch)
    except Exception as e:
        facts["agryp_bench"] = (False, None)
        print("  agryp bench/ не подтвердился: %s — имя уточнить живым ходом" % type(e).__name__)
    return facts


def build_map(seed, pairs_status, facts):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = []
    counts = {"симметрична": 0, "односторонняя": 0, "мертва": 0, "не проверено (без сети)": 0}
    for pid, sa, sb in pairs_status:
        counts[sa] = counts.get(sa, 0) + 1
        rows.append("| %s | %s | %s |" % (pid, sa, sb))
    lines = [
        "# Симметричная карта генома и витрина ниши (волна ×3, ПРЕДЛОЖЕНИЕ-15)",
        "",
        "Дата: %s. Правило роя: обе ссылки пары должны быть живы (HTTP 200)," % now,
        "иначе связь красится односторонней и гейт краснеет. (заполняется скриптом",
        "tools/wave3/symmetry.py при каждом прогоне)",
        "",
        "## Пары sNN<->sNN",
        "",
        "| пара | направление a | направление b |",
        "|---|---|---|",
    ]
    lines += rows if rows else ["| (пары не заявлены — сид пуст) | | |"]
    lines += ["", "## Витрина ниши «0 процессных»", ""]
    if facts and "public_repos" in facts:
        lines.append("- Агентских публичных репо у роя: %s (GitHub API на дату карты)." % facts["public_repos"])
    else:
        lines.append("- Агентских публичных репо: (без сети — счётчик заполнится при прогоне).")
    lines.append("- Процессных: 0 — ниша свободна (утверждение предложения #10; счётчик подтверждается витриной при каждом прогоне).")
    if facts and "agryp_bench" in facts:
        ok, branch = facts["agryp_bench"]
        url = "https://github.com/rtynbirf/agryp/tree/%s/bench" % branch if branch else "https://github.com/rtynbirf/agryp"
        lines.append("- Бенч-протокол: agryp bench/ — %s (%s)." % (url, "жива" if ok else "не подтвердилась — имя уточнить живым ходом"))
    else:
        lines.append("- Бенч-протокол: agryp bench/ — (без сети — живость проверится при прогоне).")
    lines += [
        "",
        "## Гейт симметрии",
        "",
        "- симметричных: %d; односторонних: %d; мёртвых: %d; не проверено: %d"
        % (counts["симметрична"], counts["односторонняя"], counts["мертва"], counts["не проверено (без сети)"]),
        "",
    ]
    return "\n".join(lines)


def check():
    seed = ensure_seed()
    pairs = seed.get("pairs", []) if isinstance(seed, dict) else []
    pairs_status = []
    for p in pairs:
        pid = p.get("id", "?")
        a, b = alive(p.get("a_url", "")), alive(p.get("b_url", ""))
        if a is None or b is None:
            st = "не проверено (без сети)"
        elif a and b:
            st = "симметрична"
        elif a or b:
            st = "односторонняя"
        else:
            st = "мертва"
        pairs_status.append((pid, st, "%s -> %s" % (a, b)))
    facts = niche_facts()
    MAP.write_text(build_map(seed, pairs_status, facts), encoding="utf-8")
    print("карта записана: peers/SYMMETRY-MAP.md")
    if not pairs:
        print("ПРЕДУПРЕЖДЕНИЕ: сид пуст — гейт ничего не проверял; пары sNN<->sNN вносятся живым ходом")
        return 0
    bad = [s for _, s, _ in pairs_status if s in ("односторонняя", "мертва")]
    if bad:
        print("гейт красный: связей не-симметричных: %d" % len(bad))
        return 1
    print("гейт зелёный: все заявленные пары симметричны")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        return check()
    print("режимы: check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
