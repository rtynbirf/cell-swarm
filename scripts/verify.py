#!/usr/bin/env python3
"""verify.py — fail-closed проверка роя.

Грамматики: геном (swarm.json), ДНК (MANIFEST.json), голос пира (peers/peer-manifest.json
— зеркало PeerManifest дома, ADR-0017), согласия роя (consent/grants.json — зеркало
ConsentGrant). Незаявленное не достраивается (A02): незаявленный ключ, незаявленный
транспорт, пустой белый список, нечитаемое окно — поимённая ошибка, exit 1.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TRANSPORTS = ("stdio", "http-localhost", "none")  # словарь дома, ADR-0016
GRANTED_BY = ("human", "organ")  # словарь дома, ADR-0017
PEER_KEYS = {"name", "transport", "consents", "provenance"}  # ровно как дома
GRANT_KEYS = {"consent_id", "peer", "methods", "granted_by", "not_after"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
BLOOD_TYPES = (
    "plan", "act", "observe", "reflect", "halt", "veto", "error",
    "security.violation", "organ.health", "organ.replace", "boot", "shutdown",
    "alert", "approval.request", "approval.grant", "approval.requested",
    "approval.granted", "approval.veto", "approval.expired", "stop.requested",
    "forget",
)  # словарь дома, SPEC-0003 п.17 (справочно для emit.py)


class Rejection(Exception):
    """Поимённый отказ — незаявленное не достраивается."""


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Rejection(f"{path.name}: файл не найден") from None
    except json.JSONDecodeError as exc:
        raise Rejection(f"{path.name}: нечитаемый JSON: {exc}") from None


# --- голос пира (зеркало PeerManifest дома) ---

def check_peer_manifest(data: dict) -> None:
    unknown = set(data) - PEER_KEYS
    if unknown:
        raise Rejection(f"peer manifest: незаявленные ключи {sorted(unknown)} — незаявленное не достраивается (A02)")
    missing = PEER_KEYS - set(data)
    if missing:
        raise Rejection(f"peer manifest: не хватает ключей {sorted(missing)} — голос неполон")
    if not isinstance(data["name"], str) or not data["name"]:
        raise Rejection("peer manifest: имя пусто — обмен с безымянным не начинается")
    if data["transport"] not in TRANSPORTS:
        raise Rejection(f"peer manifest: транспорт {data['transport']!r} не из {TRANSPORTS} (ADR-0016)")
    if not isinstance(data["consents"], bool):
        raise Rejection("peer manifest: consents не bool — чужое слово не фантазируем")
    if not isinstance(data["provenance"], str) or not data["provenance"]:
        raise Rejection("peer manifest: provenance пуст — неизвестно, откуда знаем о пире")


# --- согласия роя (зеркало ConsentGrant дома) ---

def _moment(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise Rejection("grant: not_after пуст — нечитаемая свежесть не согласие")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise Rejection(f"grant: not_after {value!r} не ISO-8601 — окно нечитаемо") from None


def check_grant(data: dict) -> None:
    unknown = set(data) - GRANT_KEYS
    if unknown:
        raise Rejection(f"grant: незаявленные ключи {sorted(unknown)} (A02)")
    missing = GRANT_KEYS - set(data)
    if missing:
        raise Rejection(f"grant: не хватает ключей {sorted(missing)} — согласие неполно")
    if not isinstance(data["consent_id"], str) or not data["consent_id"]:
        raise Rejection("grant: consent_id пуст — согласие без ключа не живёт")
    if not isinstance(data["peer"], str) or not data["peer"]:
        raise Rejection("grant: peer пуст — согласие «с кем-то» не согласие")
    methods = data["methods"]
    if not isinstance(methods, list) or not methods or not all(isinstance(m, str) and m for m in methods):
        raise Rejection("grant: methods пуст или не список строк — согласие на всё подряд не согласие")
    if data["granted_by"] not in GRANTED_BY:
        raise Rejection(f"grant: granted_by {data['granted_by']!r} не из {GRANTED_BY} (A02)")
    _moment(data["not_after"])


# --- геном и ДНК ---

def check_genome(data: dict) -> None:
    for key in ("genome_version", "fetched_at", "cells"):
        if key not in data:
            raise Rejection(f"genom: нет ключа {key!r} — геном без даты/клеток не геном")
    if not isinstance(data["cells"], list) or not data["cells"]:
        raise Rejection("genom: cells пуст — пустой рой не рой")
    seen = set()
    for cell in data["cells"]:
        for key in ("name", "repo", "pin", "role", "license_pre"):
            if key not in cell:
                raise Rejection(f"genom: клетка без {key!r} — незаявленное не достраивается")
        if cell["name"] in seen:
            raise Rejection(f"genom: клетка {cell['name']!r} задвоена")
        seen.add(cell["name"])
        if not SHA_RE.match(cell["pin"]):
            raise Rejection(f"genom: пин {cell['name']!r} не SHA-1 (40 hex) — пин «по памяти» не вносится")
        if not str(cell["repo"]).startswith("https://"):
            raise Rejection(f"genom: repo {cell['name']!r} не https — анонимного клонирования не заявляем")
        if "предварительно" not in cell["license_pre"] and "верифицировано" not in cell["license_pre"] and "Apache-2.0" not in cell["license_pre"]:
            raise Rejection(f"genom: license_pre {cell['name']!r} без пометки статуса — метрики/лицензии только с датой или «предварительно»")


def check_manifest(data: dict) -> None:
    for key in ("name", "kind", "license", "membrane", "metabolism", "body", "laws"):
        if key not in data:
            raise Rejection(f"manifest: нет ключа {key!r} — клетка без органа не клетка")
    if len(data["laws"]) != 5:
        raise Rejection("manifest: законов роя не пять — пять или никак")


# --- вердикт согласия роя ДО факта (зеркало verify дома) ---

def my_verdict(peer_name: str, method: str, grants: list, peer_consents: bool = True,
               now: datetime | None = None) -> tuple[str, str]:
    """Объединение поимённых грантов: метод покрыт, пока свеж хотя бы один грант,
    его покрывающий (у роя может быть несколько грантов с одним пиром — по-методно).
    Порядок отказов — как у дома: peer_unknown → peer_silent → method_not_in_scope → expired."""
    now = now or datetime.now().astimezone()
    rows = [g for g in grants if g["peer"] == peer_name]
    if not rows:
        return "denied", "peer_unknown"
    if not peer_consents:
        return "denied", "peer_silent"
    covered_fresh = covered_expired = False
    for grant in rows:
        if method in grant["methods"]:
            if now <= _moment(grant["not_after"]):
                covered_fresh = True
            else:
                covered_expired = True
    if covered_fresh:
        return "granted", "both_sides_consent"
    if covered_expired:
        return "denied", "expired"
    return "denied", "method_not_in_scope"


def main() -> int:
    failures: list[str] = []
    try:
        check_manifest(load(ROOT / "MANIFEST.json"))
        print("MANIFEST.json        : ok")
    except Rejection as exc:
        failures.append(str(exc))
    try:
        check_genome(load(ROOT / "swarm.json"))
        print("swarm.json           : ok")
    except Rejection as exc:
        failures.append(str(exc))
    try:
        check_peer_manifest(load(ROOT / "peers/peer-manifest.json"))
        print("peers/peer-manifest  : ok (грамматика ADR-0017)")
    except Rejection as exc:
        failures.append(str(exc))
    try:
        grants = load(ROOT / "consent/grants.json")
        for grant in grants["grants"]:
            check_grant(grant)
        print("consent/grants.json  : ok (зеркало ConsentGrant)")
    except (Rejection, KeyError) as exc:
        failures.append(f"grants: {exc}")
    if failures:
        print("\nОТКАЗЫ:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nрой цел: геном, ДНК, голос пира и согласия — поимённо валидны")
    return 0


if __name__ == "__main__":
    sys.exit(main())
