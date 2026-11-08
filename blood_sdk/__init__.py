"""blood_sdk — конверт крови как один пакет (ПРЕДЛОЖЕНИЕ-21, волна ×3 W3-D).
Только stdlib, Python 3.11. Границы: SDK не доставляет события (это workflow-цепь),
только строит и верифицирует конверты.

Три функции:
  build_envelope(type, payload, source, ttl_days, tol, prev_hash, created_at)
      -> конверт с id, prev_hash и hash = SHA-256;
  put_envelope(url, envelope) — идемпотентный PUT («повтор не рана»: тот же id возвращает
      тот же ответ и не создаёт вторую запись). url «fixture:ПУТЬ» — локальный приёмник
      для золотых проб (без сети); иначе HTTP PUT (urllib);
  verify_response(body, envelope) — проверка ответа: битый JSON, просроченный ttl_days,
      чужой hash — поимённый отказ BloodError.

Канон v1 (зафиксирован здесь и в selftest): JSON с сортировкой ключей, компактными
разделителями, UTF-8; hash = SHA-256 канона записи без поля hash; id = первые 16 hex
SHA-256 канона записи без id и hash. Если репо-канон иной — diff самотеста покажет
поимённо, правило уточняется живым ходом.
"""
import hashlib
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ZERO_HASH = "0" * 64

SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "blood-конверт cell-swarm (волна ×3, ПРЕДЛОЖЕНИЕ-21)",
    "type": "object",
    "required": ["id", "type", "payload", "source", "ttl_days", "prev_hash", "hash"],
    "properties": {
        "id": {"type": "string", "pattern": "^[0-9a-f]{16}$"},
        "type": {"type": "string", "minLength": 1},
        "payload": {"type": "object"},
        "source": {
            "type": "object",
            "required": ["repo", "path"],
            "properties": {
                "repo": {"type": "string"},
                "ref": {"type": "string"},
                "path": {"type": "string"},
                "sha256": {"type": "string"},
            },
        },
        "ttl_days": {"type": "integer", "minimum": 0},
        "tol": {
            "type": "object",
            "properties": {"eps": {"type": "number"}, "deadband": {"type": "number"}},
        },
        "created_at": {"type": "string",
                       "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"},
        "prev_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    },
}


class BloodError(Exception):
    """Поимённый отказ контракта крови."""


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_envelope(*, type, payload, source, ttl_days, tol=None,
                   prev_hash=ZERO_HASH, created_at=None):
    body = {"type": type, "payload": payload, "source": source,
            "ttl_days": int(ttl_days), "prev_hash": prev_hash}
    if tol is not None:
        body["tol"] = tol
    body["created_at"] = created_at or now_iso()
    body["id"] = sha_hex(canon(body))[:16]
    body["hash"] = sha_hex(canon(body))
    return body


def _fixture_put(path: str, envelope):
    p = Path(path)
    lines = []
    if p.exists():
        lines = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    mine = [x for x in lines if x.get("id") == envelope.get("id")]
    if not mine:
        lines.append(envelope)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n"
                             for x in lines), encoding="utf-8")
    return {"id": envelope.get("id"), "status": "created",
            "count": len([x for x in lines if x.get("id") == envelope.get("id")])}


def put_envelope(url, envelope, timeout=30):
    """Идемпотентный PUT. Повтор с тем же id — тот же ответ, второй записи нет."""
    if url.startswith("fixture:"):
        return _fixture_put(url[len("fixture:"):], envelope)
    req = urllib.request.Request(
        url, data=canon(envelope), method="PUT",
        headers={"Content-Type": "application/json", "User-Agent": "blood-sdk-wave3"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def verify_response(body, envelope=None):
    if isinstance(body, (bytes, bytearray)):
        try:
            obj = json.loads(bytes(body).decode("utf-8"))
        except Exception as e:
            raise BloodError("битый JSON ответа: %s" % e)
    else:
        obj = body
    if not isinstance(obj, dict):
        raise BloodError("ответ не объект")
    src = envelope if isinstance(envelope, dict) else obj
    ttl, created = src.get("ttl_days"), src.get("created_at")
    if isinstance(ttl, int) and isinstance(created, str):
        try:
            c = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            raise BloodError("created_at не в формате ISO-UTC")
        if datetime.now(timezone.utc) > c + timedelta(days=ttl):
            raise BloodError("просроченный ttl_days: конверт истёк (истёкший — не рана, а отказ верификации)")
    if "hash" in obj:
        rebuilt = sha_hex(canon({k: v for k, v in obj.items() if k != "hash"}))
        if rebuilt != obj["hash"]:
            raise BloodError("чужой hash: пересчёт канона не совпал")
    if not obj.get("status"):
        raise BloodError("в ответе нет status")
    return obj


def write_schema(path=None):
    """Материализует контракт полей в blood_sdk/schema.json (при первом прогоне)."""
    p = Path(path) if path else Path(__file__).resolve().parent / "schema.json"
    if not p.exists():
        p.write_text(json.dumps(SCHEMA, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p
