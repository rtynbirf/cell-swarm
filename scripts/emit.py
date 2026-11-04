#!/usr/bin/env python3
"""emit.py — кровь роя: конверты SPEC-0003 дома с хэш-цепочкой журнала.

Конверт несёт цену всегда (событие без цены недействительно), тип — только
из словаря дома (SPEC-0003 п.17), журнал append-only. Цепочка — как в доме:
`prev_id` + `prev_sha256` = SHA-256 канонической JSON-формы предыдущего
конверта; каноническая форма — json.dumps(sort_keys=True, ensure_ascii=False,
separators=(",", ":")) — совместима с canonical_sha256 дома байт-в-байт
(blood/envelope.py дома, прочитано в клоне 2026-11-05).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from verify import BLOOD_TYPES, Rejection  # noqa: E402

DEFAULT_JOURNAL = ROOT / "blood" / "journal.jsonl"


def canonical_sha256(envelope: dict) -> str:
    canonical = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_envelope(*, type: str, source: str, organ: str, trace_id: str,
                   payload: dict, tokens_in: int = 0, tokens_out: int = 0,
                   seconds: float = 0.0, attention: int = 0,
                   idempotency_key: str | None = None) -> dict:
    if type not in BLOOD_TYPES:
        raise Rejection(f"emit: тип {type!r} не из словаря дома — незаявленное не пишется (ADR-0014, fail-closed)")
    if not source or not organ or not trace_id:
        raise Rejection("emit: source/organ/trace_id пусты — конверт без происхождения недействителен")
    cost: dict = {"tokens_in": int(tokens_in), "tokens_out": int(tokens_out), "seconds": float(seconds)}
    if tokens_in < 0 or tokens_out < 0 or seconds < 0 or attention < 0:
        raise Rejection("emit: отрицательная цена — цена бывает только неотрицательной")
    if attention:
        cost["attention"] = int(attention)  # 0 не пишется: старый стиль жив
    envelope: dict = {
        "id": str(uuid.uuid4()),
        "ts": now_utc(),
        "type": type,
        "source": source,
        "organ": organ,
        "trace_id": trace_id,
        "payload": payload,
        "cost": cost,
    }
    if idempotency_key:
        envelope["idempotency_key"] = idempotency_key
    return envelope


def last_envelope(journal: Path) -> dict | None:
    if not journal.exists():
        return None
    lines = [line for line in journal.read_text(encoding="utf-8").splitlines() if line.strip()]
    return json.loads(lines[-1]) if lines else None


def append(journal: Path, envelope: dict) -> dict:
    """Журнал ставит stored_at и пришивает цепочку (как в доме, blood/journal.py)."""
    envelope["stored_at"] = now_utc()
    previous = last_envelope(journal)
    if previous is not None:
        envelope["prev_id"] = previous["id"]
        envelope["prev_sha256"] = canonical_sha256(previous)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    return envelope


def verify_journal(journal: Path) -> tuple[int, list[str]]:
    """Цепочка целостности: разрыв/подмена ловятся при чтении."""
    errors: list[str] = []
    if not journal.exists():
        return 0, ["журнала нет — крови нет (это не ошибка для demo)"]
    envelopes = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line.strip()]
    for index, envelope in enumerate(envelopes):
        for key in ("id", "ts", "type", "source", "organ", "trace_id", "payload", "cost"):
            if key not in envelope:
                errors.append(f"[{index}] нет обязательного {key!r} — событие без тела недействительно")
        if envelope.get("type") not in BLOOD_TYPES:
            errors.append(f"[{index}] тип {envelope.get('type')!r} вне словаря дома")
        cost = envelope.get("cost", {})
        if not isinstance(cost, dict) or any(k not in cost for k in ("tokens_in", "tokens_out", "seconds")):
            errors.append(f"[{index}] цена неполна — событие без цены недействительно")
        if index == 0:
            if "prev_id" in envelope:
                errors.append("[0] первый конверт не несёт prev_id")
        else:
            previous = envelopes[index - 1]
            if envelope.get("prev_id") != previous.get("id"):
                errors.append(f"[{index}] prev_id не шьётся с предыдущим")
            if envelope.get("prev_sha256") != canonical_sha256(previous):
                errors.append(f"[{index}] prev_sha256 не сходится — содержание подменено")
    return len(envelopes), errors


def main() -> int:
    parser = argparse.ArgumentParser(description="кровь роя: конверт SPEC-0003 в append-only журнал")
    parser.add_argument("--type", choices=BLOOD_TYPES)
    parser.add_argument("--source", help="эмитент: swarm | cell:<имя>")
    parser.add_argument("--organ")
    parser.add_argument("--trace")
    parser.add_argument("--payload", default="{}")
    parser.add_argument("--tokens-in", type=int, default=0)
    parser.add_argument("--tokens-out", type=int, default=0)
    parser.add_argument("--seconds", type=float, default=0.0)
    parser.add_argument("--attention", type=int, default=0)
    parser.add_argument("--idempotency-key")
    parser.add_argument("--journal", default=str(DEFAULT_JOURNAL))
    parser.add_argument("--verify", action="store_true", help="только проверить цепочку журнала")
    args = parser.parse_args()

    journal = Path(args.journal)
    if args.verify:
        count, errors = verify_journal(journal)
        print(f"конвертов: {count}; ошибок цепочки: {len(errors)}")
        for error in errors:
            print(f"  - {error}")
        return 1 if errors else 0

    missing = [name for name in ("type", "source", "organ", "trace") if getattr(args, name) is None]
    if missing:
        parser.error(f"для пролива крови не хватает: {', '.join('--' + m for m in missing)} (или используй --verify)")

    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as exc:
        print(f"emit: payload не JSON: {exc}", file=sys.stderr)
        return 1
    try:
        envelope = build_envelope(
            type=args.type, source=args.source, organ=args.organ, trace_id=args.trace,
            payload=payload, tokens_in=args.tokens_in, tokens_out=args.tokens_out,
            seconds=args.seconds, attention=args.attention, idempotency_key=args.idempotency_key,
        )
    except Rejection as exc:
        print(f"ОТКАЗ: {exc}", file=sys.stderr)
        return 1
    append(journal, envelope)
    print(f"кровь пролита: {envelope['id']} (type={envelope['type']}, journal={journal})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
