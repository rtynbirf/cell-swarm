"""Самопроверка blood_sdk: `python -m blood_sdk.selftest` (ПРЕДЛОЖЕНИЕ-21, критерии приёмки).

1) Выращивает blood_sdk/golden/ из blood/LEDGER.jsonl (первые 10 конвертов; строки со
   статусом VERIFIED приоритетны) и воспроизводит хеш-цепь: пересборка проб даёт те же
   sha256 — diff пуст; prev/hash цепочка проб восстанавливается.
2) Идемпотентный PUT: двойной put_envelope с тем же id в fixture-приёмник возвращает
   идентичный ответ, в приёмнике ровно 1 запись.
3) verify_response падает на 3 подложных кейсах (чужой hash, просроченный ttl_days,
   битый JSON); каждая золотая проба и каждый собранный конверт валидны по schema.json
   (мини-валидатор stdlib: type/required/properties/pattern/minimum/enum).

Коды выхода: 0 — всё зелёное; 1 — расхождения или нехватка проб (нужен живой LEDGER);
2 — среда не пригодна. golden/ и schema.json выращиваются при первом прогоне
(заполняется скриптом; пустые структуры в репо не выдумываются).
"""
import json
import re
import sys
import tempfile
from pathlib import Path

from . import (SCHEMA, BloodError, build_envelope, canon, put_envelope, sha_hex,
               verify_response, write_schema)

ROOT = Path(__file__).resolve().parents[1]
SDK = Path(__file__).resolve().parent
GOLDEN = SDK / "golden"
NEED = 10
FIXED_DATE = "2026-11-09T00:00:00Z"


def mini_validate(obj, schema, path="$"):
    errs = []
    types = {"object": dict, "string": str, "integer": int, "number": (int, float),
             "boolean": bool, "array": list, "null": type(None)}
    t = schema.get("type")
    if t:
        ok = isinstance(obj, types[t]) and not (t in ("integer", "number") and isinstance(obj, bool))
        if not ok:
            return ["%s: ожидался тип %s" % (path, t)]
    for k in schema.get("required", []):
        if k not in obj:
            errs.append("%s: нет обязательного поля %s" % (path, k))
    for k, sub in schema.get("properties", {}).items():
        if k in obj:
            errs += mini_validate(obj[k], sub, "%s.%s" % (path, k))
    if "enum" in schema and obj not in schema["enum"]:
        errs.append("%s: вне enum" % path)
    if isinstance(schema.get("pattern"), str) and isinstance(obj, str) \
            and not re.search(schema["pattern"], obj):
        errs.append("%s: не совпадает с pattern" % path)
    if "minimum" in schema and isinstance(obj, (int, float)) \
            and not isinstance(obj, bool) and obj < schema["minimum"]:
        errs.append("%s: меньше minimum" % path)
    return errs


def grow_golden():
    """Возвращает (сколько выращено, диффы). Пробы = сырые строки LEDGER."""
    ledger = ROOT / "blood" / "LEDGER.jsonl"
    if not ledger.exists():
        return 0, ["blood/LEDGER.jsonl не найден — золотые пробы растут из живого LEDGER"]
    raw_lines = [x for x in ledger.read_text(encoding="utf-8").splitlines() if x.strip()]
    parsed = []
    for i, line in enumerate(raw_lines):
        try:
            parsed.append((i, line, json.loads(line)))
        except Exception:
            print("  LEDGER: строка %d не JSON — пропущена" % (i + 1))
    verified = [t for t in parsed if isinstance(t[2], dict) and t[2].get("status") == "VERIFIED"]
    take = verified if len(verified) >= NEED else parsed
    take = [t for t in take if isinstance(t[2], dict) and "hash" in t[2]][:NEED]
    if len(take) < NEED:
        return len(take), ["конвертов с hash в LEDGER: %d из %d — нужен живой LEDGER" % (len(take), NEED)]
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for n, (i, line, rec) in enumerate(take, 1):
        (GOLDEN / ("golden-%02d.json" % n)).write_text(line + "\n", encoding="utf-8")
    print("выращено проб: %d из %s (строки LEDGER %s)"
          % (len(take), NEED, ", ".join(str(i + 1) for i, _, _ in take)))
    return len(take), []


def replay_chain():
    files = sorted(GOLDEN.glob("golden-*.json"))
    diffs, prev = [], None
    for f in files:
        rec = json.loads(f.read_text(encoding="utf-8"))
        body = {k: v for k, v in rec.items() if k != "hash"}
        if sha_hex(canon(body)) != rec.get("hash"):
            diffs.append("%s: пересобранный sha256 не совпал с hash пробы" % f.name)
        if prev is not None and rec.get("prev_hash") != prev:
            diffs.append("%s: prev_hash не равен hash предыдущей пробы (цепь LEDGER не восстанавливается)" % f.name)
        prev = rec.get("hash")
    return files, diffs


def test_idempotent_put():
    with tempfile.TemporaryDirectory() as td:
        sink = str(Path(td) / "sink.jsonl")
        env = build_envelope(type="probe", payload={"case": "idempotent"},
                             source={"repo": "rtynbirf/cell-swarm", "ref": "main",
                                     "path": "blood_sdk/selftest.py"},
                             ttl_days=7, created_at=FIXED_DATE)
        r1 = put_envelope("fixture:" + sink, env)
        r2 = put_envelope("fixture:" + sink, env)
        stored = [x for x in Path(sink).read_text(encoding="utf-8").splitlines() if x.strip()]
        if r1 != r2:
            return ["двойной PUT вернул разные ответы: %r vs %r" % (r1, r2)]
        if len(stored) != 1:
            return ["в приёмнике записей: %d, ожидалась ровно 1" % len(stored)]
        print("идемпотентный PUT: ответы идентичны (%s), записей в приёмнике: 1" % r1["status"])
        return []


def test_verify_negative():
    env = build_envelope(type="probe", payload={"case": "fake"},
                         source={"repo": "rtynbirf/cell-swarm", "ref": "main",
                                 "path": "blood_sdk/selftest.py"},
                         ttl_days=7, created_at=FIXED_DATE)
    stranger = dict(env, hash="f" * 64)
    expired = dict(env, ttl_days=1, created_at="2026-01-01T00:00:00Z")
    cases = [("чужой hash", stranger), ("просроченный ttl_days", expired),
             ("битый JSON", "{нет".encode("utf-8"))]
    fails = 0
    for name, payload in cases:
        try:
            verify_response(payload)
            print("ПОДЛОЖНЫЙ КЕЙС ПРОШЁЛ (плохо): %s" % name)
            fails += 1
        except BloodError as e:
            print("  отклонён поимённо: %s — %s" % (name, e))
    return [] if fails == 0 else ["подложные кейсы: %d прошли вместо отказа" % fails]


def test_schema():
    errs = mini_validate(build_envelope(type="probe", payload={}, source={"repo": "r", "path": "p"},
                                        ttl_days=7, created_at=FIXED_DATE),
                         SCHEMA)
    files = sorted(GOLDEN.glob("golden-*.json"))
    for f in files:
        errs += mini_validate(json.loads(f.read_text(encoding="utf-8")), SCHEMA, f.name)
    if errs:
        return ["schema.json: " + "; ".join(errs)]
    print("schema.json: собранный конверт и все пробы (%d) валидны" % len(files))
    return []


def main():
    problems = []
    schema_path = SDK / "schema.json"
    fresh = not schema_path.exists()
    write_schema()
    print("контракт: blood_sdk/schema.json%s" % (" (создан при первом прогоне)" if fresh else ""))
    grown, diffs = grow_golden()
    problems += diffs
    if grown:
        files, chain_diffs = replay_chain()
        problems += chain_diffs
        if not chain_diffs:
            print("хеш-цепь из %d проб воспроизведена: пересборка даёт те же sha256, diff пуст" % len(files))
    problems += test_idempotent_put()
    problems += test_verify_negative()
    problems += test_schema()
    if problems:
        print("selftest: КРАСНЫЙ, проблем: %d" % len(problems))
        for p in problems:
            print("  проблема:", p)
        return 1
    print("selftest: зелёный (идемпотентность, отказы поимённо, schema, цепь проб)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
