#!/usr/bin/env python3
"""Золотой обмен cell-rs ↔ Python-клетка (ПРЕДЛОЖЕНИЕ-09, такт 2) — байт-в-байт.

Эталон — hashlib (stdlib). Проверки:
  T1. SHA-256 cell-rs == hashlib на фиксированных векторах (в т.ч. пустой ввод и многочан).
  T2. Такт 1 «цепь»: Python строит файл канонических записей и считает корень,
      cell-rs chain должен вернуть те же корень и число строк.
  T3. Такт 2 «конверт»: Python строит blood-конверт (id, prev_hash, hash=SHA-256 канона)
      и ожидаемый verdict JSON; verdict cell-rs должен совпасть байт-в-байт (OK/WARN/HALT).

Запуск: python3 cell-rs/golden_exchange.py ./cell-rs/cell-rs
Сборка: rustc -O cell-rs/src/main.rs -o cell-rs/cell-rs
Выход: 0 — обмен сошёлся; 1 — байты разошлись; 2 — среду не приготовить.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

CANON_DATE = "2026-11-09T00:00:00Z"  # дата волны, фиксирована для воспроизводимости


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_bin(binpath: str, args, stdin=None):
    p = subprocess.run([binpath, *args], input=stdin, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=60)
    return p.returncode, p.stdout, p.stderr


def build_envelope(value, center, eps, deadband):
    body = {
        "type": "probe",
        "payload": {"value": value, "center": center},
        "tol": {"eps": eps, "deadband": deadband},
        "source": {"repo": "rtynbirf/cell-swarm", "ref": "main",
                   "path": "cell-rs/golden_exchange.py"},
        "ttl_days": 7,
        "created_at": CANON_DATE,
        "prev_hash": "0" * 64,
    }
    body["id"] = sha_hex(canon(body))[:16]
    body["hash"] = sha_hex(canon(body))
    return body


def expected_verdict(value, center, eps, deadband, envelope_hash):
    delta = value - center
    ad = abs(delta)
    v = "OK" if ad <= eps else ("WARN" if ad <= eps + deadband else "HALT")
    return ('{"delta":"%s","envelope_hash":"%s","verdict":"%s"}'
            % (format(delta, ".6f"), envelope_hash, v)).encode("utf-8") + b"\n"


def t1_hash(binpath, fails):
    vectors = [b"", b"cell-swarm", "кровь-конверт".encode("utf-8"), bytes(range(256)) * 3]
    for i, data in enumerate(vectors, 1):
        rc, out, err = run_bin(binpath, ["hash-stdin"], stdin=data)
        want = hashlib.sha256(data).hexdigest().encode() + b"\n"
        if rc != 0 or out != want:
            fails.append("T1.%d: sha256 разошёлся с hashlib (rc=%d, err=%s)" % (i, rc, err.decode()[:80]))
        else:
            print("T1.%d: sha256 совпал с hashlib (%d байт ввода)" % (i, len(data)))


def t2_chain(binpath, fails, tmp: Path):
    chain_file = tmp / "chain-golden.jsonl"
    lines = []
    for i in range(5):
        lines.append(canon({"n": i, "word": "звено", "ok": True}))
    chain_file.write_bytes(b"\n".join(lines) + b"\n")
    prev = "0" * 64
    for line in lines:
        prev = sha_hex(prev.encode("ascii") + line)
    rc, out, err = run_bin(binpath, ["chain", str(chain_file)])
    want = ("root=%s lines=5" % prev).encode() + b"\n"
    if rc != 0 or out != want:
        fails.append("T2: цепь разошлась (rc=%d, got=%r, want=%r, err=%s)"
                     % (rc, out[:120], want[:120], err.decode()[:80]))
    else:
        print("T2: такт 1 «цепь» — корень и число строк совпали байт-в-байт")


def t3_verdict(binpath, fails):
    cases = [
        ("OK", 1.05, 1.0, 0.2, 0.1),
        ("WARN", 1.25, 1.0, 0.2, 0.1),
        ("HALT", 1.5, 1.0, 0.2, 0.1),
        ("HALT-отрицательный", 0.5, 1.0, 0.2, 0.1),
    ]
    for name, value, center, eps, deadband in cases:
        env = build_envelope(value, center, eps, deadband)
        args = ["verdict", "--value", repr(value), "--center", repr(center),
                "--eps", repr(eps), "--deadband", repr(deadband),
                "--envelope-hash", env["hash"]]
        rc, out, err = run_bin(binpath, args)
        want = expected_verdict(value, center, eps, deadband, env["hash"])
        if rc != 0 or out != want:
            fails.append("T3/%s: вердикт разошёлся байт-в-байт (rc=%d, got=%r, want=%r, err=%s)"
                         % (name, rc, out[:160], want[:160], err.decode()[:80]))
        else:
            print("T3/%s: вердикт совпал байт-в-байт (%d байт)" % (name, len(out)))


def main():
    if len(sys.argv) != 2:
        print("использование: golden_exchange.py <путь до собранного cell-rs>", file=sys.stderr)
        return 2
    binpath = sys.argv[1]
    if not Path(binpath).exists():
        print("нет бинарника %s; соберите: rustc -O cell-rs/src/main.rs -o cell-rs/cell-rs" % binpath,
              file=sys.stderr)
        return 2
    fails = []
    with tempfile.TemporaryDirectory() as td:
        t1_hash(binpath, fails)
        t2_chain(binpath, fails, Path(td))
        t3_verdict(binpath, fails)
    if fails:
        print("золотой обмен НЕ сошёлся, расхождений: %d" % len(fails))
        for f in fails:
            print("  расхождение:", f)
        return 1
    print("золотой обмен сошёлся: цепь и конверт байт-в-байт, эталон hashlib")
    return 0


if __name__ == "__main__":
    sys.exit(main())
