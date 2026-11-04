#!/usr/bin/env python3
"""handshake.py — согласие обеих сторон обмена ДО факта (зеркало ADR-0017 дома).

Своя грамматика — для обменов, где рой решает (мой белый список против пира).
--cross <путь к клону commons> — импортирует ИХ synapse/consent.py и прогоняет
голос роя (peers/peer-manifest.json) через грамматику ДОМА: дом читает мой
PeerManifest, вердикт поимённый. Это и есть мост: обе грамматики признают
одни и те же четыре ключа.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from verify import check_peer_manifest, my_verdict, Rejection  # noqa: E402


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def local_handshake(peer_name: str, method: str, peer_consents: bool = True) -> tuple[str, str]:
    grants = _load(ROOT / "consent/grants.json")["grants"]
    return my_verdict(peer_name, method, grants, peer_consents=peer_consents)


def cross_handshake(commons_path: Path) -> int:
    """Грамматика ДОМА читает голос роя. Вердикт дома — поимённый."""
    module_path = commons_path / "synapse" / "consent.py"
    if not module_path.exists():
        print(f"cross: {module_path} не найден — укажи корень клона commons", file=sys.stderr)
        return 2
    spec = importlib.util.spec_from_file_location("house_consent", module_path)
    house = importlib.util.module_from_spec(spec)
    sys.modules["house_consent"] = house  # dataclasses дома требуют живой записи в sys.modules
    spec.loader.exec_module(house)  # синапсы дома: только stdlib, без побочных эффектов

    my_voice = _load(ROOT / "peers/peer-manifest.json")
    print("— голос роя читается грамматикой дома —")
    try:
        peer = house.PeerManifest.from_dict(my_voice)
        print(f"дом: PeerManifest принят: name={peer.name!r} transport={peer.transport!r} consents={peer.consents}")
    except ValueError as exc:
        print(f"дом: PeerManifest ОТКЛОНЁН: {exc}")
        return 1

    # Согласие дома — воля Человека (PID 1). Для пробы handshake берём заявленный
    # grant: в живом обмене его держит реестр дома, не рой. Грамматика дома строго
    # требует кортеж methods (JSON даёт список — конвертация на стыке, это её
    # заявленная форма, не ослабление).
    sample_grant = {
        "consent_id": "house-probe-2026-11-05",
        "peer": my_voice["name"],
        "methods": ("genome.read", "genome.pins.read", "organ.proposal.draft",
                    "blood.envelope.emit", "blood.journal.append"),
        "granted_by": "human",
        "not_after": "2027-11-05T00:00:00+00:00",
    }
    registry = house.ConsentRegistry([sample_grant], clock=lambda: "2026-11-05T12:00:00+00:00")

    print("— вердикты дома до факта обмена —")
    rc = 0
    for method in ["genome.read", "blood.envelope.emit", "memory.write"]:
        verdict = registry.verify(f"probe:{method}", peer, method)
        reason = verdict.reason if verdict.verdict == "granted" else f"denied({verdict.reason})"
        print(f"  {method:<22} → {verdict.verdict} ({reason})")
        if method == "memory.write" and verdict.ok:
            print("  косяк: незаявленный метод получил granted — fail-closed нарушен")
            rc = 1
    my_grants = _load(ROOT / "consent/grants.json")["grants"]
    verdict, reason = my_verdict("commons", "genome.read", my_grants)
    print(f"  обратная сторона    → {verdict} ({reason})  [грамматика роя читает дом]")
    print("мост жив: обе грамматики говорят одним словарём согласия")
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="вердикт согласия ДО факта обмена")
    parser.add_argument("--method", default="genome.read", help="метод обмена")
    parser.add_argument("--peer", default="commons", help="имя второй стороны")
    parser.add_argument("--silent", action="store_true", help="вторая сторона не согласна")
    parser.add_argument("--cross", metavar="COMMONS", help="путь к клону commons: грамматика дома читает голос роя")
    args = parser.parse_args()

    if args.cross:
        return cross_handshake(Path(args.cross))

    try:
        check_peer_manifest(_load(ROOT / "peers/peer-manifest.json"))
    except Rejection as exc:
        print(f"handshake: свой голос невалиден: {exc}", file=sys.stderr)
        return 1
    verdict, reason = local_handshake(args.peer, args.method, peer_consents=not args.silent)
    print(f"{args.method:<22} peer={args.peer:<10} → {verdict} ({reason})")
    return 0 if verdict == "granted" else 1


if __name__ == "__main__":
    sys.exit(main())
