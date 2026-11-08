#!/usr/bin/env python3
"""Память-сад cell-swarm (ПРЕДЛОЖЕНИЕ-10, волна ×3 W3-D). Только stdlib, Python 3.11.

Протокол MEM: statement + tol(ttl_days) + source(repo/ref/path/sha256) + prev/hash.
Версия 2 (поля необязательные, добавляются дополнением): observed_at (когда факт был
истинен), verified_at (когда сверяли), key (тема знания), tension_with, proto="2".
Незаявленное поле в v2-записи = поимённый отказ (A02). Записи-наследие (без proto)
проходят структурный осмотр — v2-закон к ним не применяется (версии растут с пробами).
Канон хеша v2: sha256 канонического JSON записи без поля hash (ключи сортированы, компактно, UTF-8).

Режимы:
  check            — fail-closed чекер v2 по всем MEM-*.json под каталогом памяти;
  tension-selftest — искусственный конфликт двух MEM: чекер репортует tension, цепь цела;
  garden [--apply] — самопрореживание: просроченные (ttl) записи — в memory/archive/
                     (гербарий, без удаления), пульс-сводка: геном + активные/архивные.
"""
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

ALLOWED = {"statement", "tol", "source", "prev", "hash", "observed_at",
           "verified_at", "key", "tension_with", "proto"}
REQUIRED = ("statement", "tol", "source", "prev", "hash")
ZERO = "0" * 64
ROOT = Path(__file__).resolve().parents[2]


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def parse_day(s):
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            pass
    return None


def check_dir(d: Path):
    """Возвращает (ошибки, tensions). Ничего не переписывает."""
    errors, records, tensions = [], [], []
    files = sorted(d.rglob("MEM-*.json"))
    if not files:
        print("память: MEM-*.json не найдены в %s — нечего проверять" % d)
    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append("%s: битый JSON (%s)" % (f.name, e))
            continue
        if not isinstance(rec, dict):
            errors.append("%s: запись не объект" % f.name)
            continue
        if rec.get("proto") == "2":
            unknown = set(rec) - ALLOWED
            if unknown:
                errors.append("%s: незаявленные поля v2: %s" % (f.name, ", ".join(sorted(unknown))))
            for k in REQUIRED:
                if k not in rec:
                    errors.append("%s: нет обязательного поля %s" % (f.name, k))
            tol = rec.get("tol")
            if not isinstance(tol, dict) or not isinstance(tol.get("ttl_days"), int) or tol["ttl_days"] < 0:
                errors.append("%s: tol.ttl_days должен быть целым >= 0" % f.name)
            src = rec.get("source")
            if not isinstance(src, dict) or not all(
                    isinstance(src.get(x), str) and src.get(x) for x in ("repo", "ref", "path", "sha256")):
                errors.append("%s: source неполон (нужны repo, ref, path, sha256)" % f.name)
            body = {k: v for k, v in rec.items() if k != "hash"}
            if "hash" in rec and sha_hex(canon(body)) != rec["hash"]:
                errors.append("%s: hash не сходится с каноном v2" % f.name)
            for tf in ("observed_at", "verified_at"):
                if tf in rec and (not isinstance(rec[tf], str) or parse_day(rec[tf]) is None):
                    errors.append("%s: %s должен быть ISO-датой" % (f.name, tf))
            records.append((f, rec))
        else:
            print("наследие: %s — структурный осмотр (v2-закон не применяется)" % f.name)
            records.append((f, rec))
    prev = ZERO
    for f, rec in records:
        if rec.get("proto") != "2":
            continue
        if rec.get("prev") != prev:
            errors.append("%s: prev не равен hash предыдущей v2-записи" % f.name)
        prev = rec.get("hash", prev)
    by_key = {}
    for f, rec in records:
        if rec.get("proto") == "2" and rec.get("key"):
            by_key.setdefault(rec["key"], []).append((f.name, rec.get("statement")))
    for key, lst in sorted(by_key.items()):
        if len(lst) > 1 and len({s for _, s in lst}) > 1:
            names = " <-> ".join(n for n, _ in lst)
            tensions.append("[%s] %s" % (key, names))
            print("tension: [%s] %s — конфликт дополнением, записи не перезаписаны" % (key, names))
    return errors, tensions


def fixture_rec(name, statement, key, prev):
    body = {"statement": statement, "tol": {"ttl_days": 30},
            "source": {"repo": "rtynbirf/cell-swarm", "ref": "main",
                       "path": "memory/%s" % name, "sha256": ZERO},
            "prev": prev, "observed_at": "2026-11-09", "verified_at": "2026-11-09",
            "key": key, "proto": "2"}
    body["hash"] = sha_hex(canon(body))
    return body


def tension_selftest():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        r1 = fixture_rec("MEM-9001.json", "Окно сверки клетки: eps + deadband", "окно-сверки", ZERO)
        r2 = fixture_rec("MEM-9002.json", "Окно сверки клетки: eps, deadband, phase",
                         "окно-сверки", r1["hash"])
        (d / "MEM-9001.json").write_text(json.dumps(r1, ensure_ascii=False), encoding="utf-8")
        (d / "MEM-9002.json").write_text(json.dumps(r2, ensure_ascii=False), encoding="utf-8")
        errors, tensions = check_dir(d)
        if errors:
            print("самотест: цепь не цела —", "; ".join(errors))
            return 1
        if len(tensions) != 1:
            print("самотест: ожидался ровно один tension, найдено %d" % len(tensions))
            return 1
    print("самотест: искусственный конфликт — tension репортован, цепь цела (записи обе живы)")
    return 0


def garden(d: Path, apply: bool):
    today = date.today()
    archive = d / "archive"
    active = [f for f in sorted(d.rglob("MEM-*.json")) if archive not in f.parents]
    expired, errors = [], []
    for f in active:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append("%s: битый JSON (%s)" % (f.name, e))
            continue
        ttl = rec.get("tol", {}).get("ttl_days") if isinstance(rec.get("tol"), dict) else None
        day = parse_day(rec.get("verified_at")) or parse_day(rec.get("observed_at"))
        if isinstance(ttl, int) and day is not None and (today - day).days > ttl:
            expired.append(f)
    if apply and expired:
        archive.mkdir(parents=True, exist_ok=True)
        for f in expired:
            shutil.move(str(f), str(archive / f.name))
            print("гербарий: %s вынесен в memory/archive/ (байты и цепь сохранены)" % f.name)
    archived = len(list(archive.glob("MEM-*.json"))) if archive.exists() else 0
    version = "нет данных"
    gp = ROOT / "swarm.json"
    if gp.exists():
        try:
            g = json.loads(gp.read_text(encoding="utf-8"))
            version = str(g.get("version", "нет данных"))
        except Exception:
            pass
    print("пульс-сводка: геном=%s; активных=%d; архивных=%d; просроченных=%d"
          % (version, len(active) - (len(expired) if apply else 0), archived, len(expired)))
    print("правило: просроченные не удаляются — выносятся в гербарий memory/archive/ с сохранением цепи")
    if errors:
        print("гербарий: ошибки чтения —", "; ".join(errors))
        return 1
    return 0


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "check":
        d = Path(args[1]) if len(args) > 1 else ROOT / "memory"
        errors, tensions = check_dir(d)
        for e in errors:
            print("ОТКАЗ A02:", e)
        print("чекер v2: tensions=%d, ошибок=%d" % (len(tensions), len(errors)))
        return 1 if errors else 0
    if cmd == "tension-selftest":
        return tension_selftest()
    if cmd == "garden":
        apply = "--apply" in args
        rest = [a for a in args[1:] if a != "--apply"]
        d = Path(rest[0]) if rest else ROOT / "memory"
        return garden(d, apply)
    print("режимы: check [dir] | tension-selftest | garden [--apply] [dir]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
