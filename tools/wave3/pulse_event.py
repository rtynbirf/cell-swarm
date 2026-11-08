"""Пульс генома как событие (ПРЕДЛОЖЕНИЕ-24, волна ×3 W3-D). Только stdlib, Python 3.11.

Режимы:
  lint [файл]            — линт подписок subscribes.jsonl: без target, с event вне
                           {pulse, genesis} — поимённый отказ (выход 2);
  lint-selftest          — самотест линта: плохие строки обязаны быть отклонены;
  run --genome F --ledger F [--apply]
                         — конверт пульса: genome_sha256 -> pulse_id, append-строка в
                           blood/LEDGER.jsonl (цепь prev/hash) и ТОЛЬКО ЗАТЕМ рассылка
                           подписчикам (transactional outbox: сначала летопись, потом
                           рассылка). Повтор с тем же genome_sha256 не создаёт ни второго
                           конверта, ни второй строки, ни второго тега — «повтор не рана».
Конверт строится тем же кодом крови: blood_sdk.build_envelope(type="pulse", ttl_days=7).
TTL истёк -> конверт не рана: доставка не повторяется по истёкшим конвертам.
Без --apply — сухой прогон (только план)."""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from blood_sdk import (ZERO_HASH, BloodError, build_envelope, canon,  # noqa: E402
                       put_envelope, sha_hex, verify_response)

SUBS = ROOT / "subscribes.jsonl"
EVENTS = ("pulse", "genesis")
HEADER = """# subscribes.jsonl — подписки клеток на пульс генома (ПРЕДЛОЖЕНИЕ-24, волна ×3).
# Формат: {"cell": "имя-клетки", "event": "pulse", "target": "https://.../приёмник-конвертов"}
# Линт: python3 tools/wave3/pulse_event.py lint — отклоняет строки без target
# и с event вне {pulse, genesis}.
# Идемпотентность: повторный пульс с тем же genome_sha256 не создаёт второго конверта
# («повтор не рана»). TTL истёк -> конверт не рана: конверт с истёкшим ttl_days не
# доставляется повторно и не считается раной.
# Подписка — акт самого клеточного репо: одна строка дополнением; клетки могут молча
# читать летопись blood/LEDGER.jsonl вместо подписки — оба режима равноправны.
# (активных подписок пока нет — строки дописываются клетками живым ходом)
"""


def read_subs(path: Path):
    subs, errors = [], []
    if not path.exists():
        path.write_text(HEADER, encoding="utf-8")
        print("файл подписок создан с документацией в шапке: %s (подписок нет — клетки дописывают живым ходом)" % path.name)
        return subs, errors
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            rec = json.loads(s)
        except Exception as e:
            errors.append("строка %d: битый JSON (%s)" % (n, e))
            continue
        if not isinstance(rec, dict):
            errors.append("строка %d: запись не объект" % n)
            continue
        if not rec.get("target") or not isinstance(rec.get("target"), str):
            errors.append("строка %d: нет target" % n)
            continue
        if rec.get("event") not in EVENTS:
            errors.append("строка %d: event вне {%s}" % (n, ", ".join(EVENTS)))
            continue
        subs.append(rec)
    return subs, errors


def lint(path: Path):
    subs, errors = read_subs(path)
    for e in errors:
        print("ОТКАЗ линта подписок:", e)
    print("подписок валидных: %d, отказов: %d" % (len(subs), len(errors)))
    return 2 if errors else 0


def lint_selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "subs.jsonl"
        p.write_text('\n'.join([
            '{"cell": "a", "event": "pulse", "target": "https://example.test/sink"}',
            '{"cell": "b", "event": "pulse"}',
            '{"cell": "c", "event": "release", "target": "https://example.test/sink"}',
        ]) + "\n", encoding="utf-8")
        _, errors = read_subs(p)
        if len(errors) != 2:
            print("самотест линта: ожидалось 2 отказа, получено %d" % len(errors))
            return 1
        print("самотест линта: строка без target и с чужим event отклонены поимённо")
        return 0


def load_ledger(path: Path):
    lines = []
    if path.exists():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                lines.append(json.loads(line))
            except Exception:
                print("летопись: строка %d не JSON — дальше цепь не считается" % n)
                break
    return lines


def run(genome_path: Path, ledger_path: Path, apply: bool):
    genome_sha = hashlib.sha256(genome_path.read_bytes()).hexdigest()
    env_sha = os.environ.get("GENOME_SHA")
    if env_sha and env_sha != genome_sha:
        print("ОТКАЗ: sha256 swarm.json не совпал с шагом тега (%s != %s)" % (env_sha, genome_sha))
        return 1
    try:
        genome = json.loads(genome_path.read_text(encoding="utf-8"))
    except Exception as e:
        print("ОТКАЗ: swarm.json не читается (%s)" % e)
        return 1
    pulse_id = "pulse-" + hashlib.sha256(genome_sha.encode()).hexdigest()[:12]
    ledger = load_ledger(ledger_path)
    for rec in ledger:
        if isinstance(rec, dict) and rec.get("payload", {}).get("pulse_id") == pulse_id:
            print("повтор не рана: pulse_id %s уже в летописи; новых конвертов: 0; новых строк: 0" % pulse_id)
            return 0
    prev = next((rec["hash"] for rec in reversed(ledger)
                 if isinstance(rec, dict) and isinstance(rec.get("hash"), str)), ZERO_HASH)
    pins = genome.get("pins") if isinstance(genome, dict) else None
    envelope = build_envelope(
        type="pulse",
        payload={"pulse_id": pulse_id, "genome_sha256": genome_sha, "pins": pins},
        source={"repo": "rtynbirf/cell-swarm", "ref": "main", "path": "swarm.json",
                "sha256": genome_sha},
        ttl_days=7, prev_hash=prev)
    subs, sub_errors = read_subs(SUBS)
    if sub_errors:
        return lint(SUBS)
    targets = [s for s in subs if s.get("event") == "pulse"]
    if not apply:
        print("сухой прогон: pulse_id=%s; genome_sha256=%s; подписчиков pulse: %d; ttl_days=7"
              % (pulse_id, genome_sha, len(targets)))
        print("с --apply: 1 строка в летопись (prev_hash=%s...), затем рассылка" % prev[:12])
        return 0
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
    print("летопись: строка дописана (pulse_id=%s, prev_hash=%s...) — теперь рассылка" % (pulse_id, prev[:12]))
    delivered, missed = 0, 0
    for s in targets:
        try:
            resp = put_envelope(s["target"], envelope)
            verify_response(resp, envelope=envelope)
            delivered += 1
            print("  конверт доставлен: %s (%s)" % (s.get("cell", "?"), s["target"]))
        except BloodError as e:
            missed += 1
            print("  ПРЕДУПРЕЖДЕНИЕ: конверт не принят: %s — %s (летопись уже правдива)" % (s.get("cell", "?"), e))
        except Exception as e:
            missed += 1
            print("  ПРЕДУПРЕЖДЕНИЕ: доставка не удалась: %s — %s (летопись уже правдива)" % (s.get("cell", "?"), e))
    print("итог: новых строк летописи: 1; конвертов доставлено: %d; не доставлено: %d; ttl_days=7 — истёкший конверт не рана" % (delivered, missed))
    return 0


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "lint":
        return lint(Path(args[1]) if len(args) > 1 else SUBS)
    if cmd == "lint-selftest":
        return lint_selftest()
    if cmd == "run":
        if "--genome" not in args or "--ledger" not in args:
            print("run: нужны --genome swarm.json и --ledger blood/LEDGER.jsonl", file=sys.stderr)
            return 2
        genome = Path(args[args.index("--genome") + 1])
        ledger = Path(args[args.index("--ledger") + 1])
        return run(genome, ledger, "--apply" in args)
    print("режимы: lint [файл] | lint-selftest | run --genome F --ledger F [--apply]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
