"""Приёмки роя: геном, грамматики согласия, кровь с цепочкой, мост с домом.

Только stdlib. Cross-тест против живого клона дома включается, если COMMONS
(или ../commons) существует — это проверка, что грамматика ДОМА принимает голос роя.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import verify  # noqa: E402
import emit  # noqa: E402
import handshake  # noqa: E402

COMMONS = Path(os.environ.get("COMMONS", ROOT.parent / "commons"))


def has_commons() -> bool:
    return (COMMONS / "synapse" / "consent.py").exists()


class Genome(unittest.TestCase):
    def test_genome_valid(self):
        verify.check_genome(json.loads((ROOT / "swarm.json").read_text(encoding="utf-8")))

    def test_manifest_five_laws(self):
        verify.check_manifest(json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8")))

    def test_pin_shape(self):
        genome = json.loads((ROOT / "swarm.json").read_text(encoding="utf-8"))
        for cell in genome["cells"]:
            self.assertRegex(cell["pin"], r"^[0-9a-f]{40}$", cell["name"])


class PeerGrammar(unittest.TestCase):
    """Зеркало грамматики дома: ровно четыре ключа, fail-closed (A02)."""

    def test_my_voice_valid(self):
        verify.check_peer_manifest(json.loads((ROOT / "peers/peer-manifest.json").read_text(encoding="utf-8")))

    def test_extra_key_poisoned(self):
        with self.assertRaises(verify.Rejection):
            verify.check_peer_manifest({"name": "x", "transport": "stdio", "consents": True,
                                        "provenance": "p", "url": "незаявленное"})

    def test_transport_vocabulary(self):
        with self.assertRaises(verify.Rejection):
            verify.check_peer_manifest({"name": "x", "transport": "wifi", "consents": True, "provenance": "p"})

    def test_grants_valid(self):
        for grant in json.loads((ROOT / "consent/grants.json").read_text(encoding="utf-8"))["grants"]:
            verify.check_grant(grant)

    def test_grant_empty_methods_poisoned(self):
        with self.assertRaises(verify.Rejection):
            verify.check_grant({"consent_id": "c", "peer": "p", "methods": [],
                                "granted_by": "human", "not_after": "2027-01-01T00:00:00+00:00"})

    def test_grant_bad_time_poisoned(self):
        with self.assertRaises(verify.Rejection):
            verify.check_grant({"consent_id": "c", "peer": "p", "methods": ["m"],
                                "granted_by": "human", "not_after": "вчера"})


class Verdicts(unittest.TestCase):
    GRANTS = [{"consent_id": "c1", "peer": "commons",
               "methods": ["genome.read"], "granted_by": "human",
               "not_after": "2030-01-01T00:00:00+00:00"}]

    def test_granted(self):
        self.assertEqual(verify.my_verdict("commons", "genome.read", self.GRANTS), ("granted", "both_sides_consent"))

    def test_unknown_peer(self):
        self.assertEqual(verify.my_verdict("stranger", "genome.read", self.GRANTS), ("denied", "peer_unknown"))

    def test_method_out_of_scope(self):
        self.assertEqual(verify.my_verdict("commons", "memory.write", self.GRANTS), ("denied", "method_not_in_scope"))

    def test_silent_peer(self):
        self.assertEqual(verify.my_verdict("commons", "genome.read", self.GRANTS, peer_consents=False),
                         ("denied", "peer_silent"))

    def test_expired(self):
        grants = [dict(self.GRANTS[0], not_after="2020-01-01T00:00:00+00:00")]
        self.assertEqual(verify.my_verdict("commons", "genome.read", grants), ("denied", "expired"))


class Blood(unittest.TestCase):
    def test_chain_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "journal.jsonl"
            first = emit.build_envelope(type="boot", source="swarm", organ="cell-swarm",
                                        trace_id="t", payload={"n": 1})
            emit.append(journal, first)
            second = emit.build_envelope(type="act", source="cell:polymath-os", organ="cell-swarm",
                                         trace_id="t", payload={"n": 2}, tokens_in=10, seconds=0.5)
            emit.append(journal, second)
            count, errors = emit.verify_journal(journal)
            self.assertEqual(count, 2)
            self.assertEqual(errors, [])
            # подмена содержания роняет ссылку на него
            lines = journal.read_text(encoding="utf-8").splitlines()
            poisoned = json.loads(lines[0])
            poisoned["payload"] = {"n": 999}
            lines[0] = json.dumps(poisoned, ensure_ascii=False)
            journal.write_text("\n".join(lines) + "\n", encoding="utf-8")
            _, errors = emit.verify_journal(journal)
            self.assertTrue(any("prev_sha256" in error or "подменено" in error for error in errors))

    def test_unknown_type_fail_closed(self):
        with self.assertRaises(verify.Rejection):
            emit.build_envelope(type="телепортация", source="swarm", organ="x", trace_id="t", payload={})

    def test_no_cost_no_event(self):
        envelope = emit.build_envelope(type="act", source="swarm", organ="x", trace_id="t", payload={})
        for key in ("tokens_in", "tokens_out", "seconds"):
            self.assertIn(key, envelope["cost"])


class Bridge(unittest.TestCase):
    @unittest.skipUnless(has_commons(), "нет клона commons (COMMONS=... )")
    def test_house_grammar_accepts_swarm_voice(self):
        """Грамматика ДОМА читает голос роя — мост жив байт-в-байт."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("house_consent", COMMONS / "synapse" / "consent.py")
        house = importlib.util.module_from_spec(spec)
        sys.modules["house_consent"] = house
        spec.loader.exec_module(house)
        my_voice = json.loads((ROOT / "peers/peer-manifest.json").read_text(encoding="utf-8"))
        peer = house.PeerManifest.from_dict(my_voice)  # не падает = грамматика дома приняла
        self.assertEqual(peer.name, "cell-swarm")

    @unittest.skipUnless(has_commons(), "нет клона commons (COMMONS=... )")
    def test_canonical_sha_matches_house(self):
        """Моя каноническая форма = canonical_sha256 дома на одном конверте."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("house_envelope", COMMONS / "blood" / "envelope.py")
        house = importlib.util.module_from_spec(spec)
        sys.modules["house_envelope"] = house
        spec.loader.exec_module(house)
        envelope = emit.build_envelope(type="observe", source="swarm", organ="cell-swarm",
                                       trace_id="t", payload={"k": "v"})
        envelope["stored_at"] = "2026-11-05T00:00:00+00:00"
        self.assertEqual(emit.canonical_sha256(envelope), house.canonical_sha256(envelope))

    def test_local_cli_handshake(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts/handshake.py"), "--method", "genome.read"],
                             capture_output=True, text=True)
        self.assertIn("granted", out.stdout)
        out = subprocess.run([sys.executable, str(ROOT / "scripts/handshake.py"),
                              "--method", "memory.write"], capture_output=True, text=True)
        self.assertIn("method_not_in_scope", out.stdout)
        self.assertEqual(out.returncode, 1)


if __name__ == "__main__":
    unittest.main()
