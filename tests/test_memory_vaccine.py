"""Приёмка прививки от стирания памяти (ADR-0007).

Орган sandbox/ обязателен: нуль с якорями, STATE с ключами, зеркало скриптов,
ADR в журнале решений. Только stdlib, офлайн.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = ROOT / "sandbox"


class MemoryVaccine(unittest.TestCase):
    def test_null_exists_and_anchored(self):
        memory = SANDBOX / "MEMORY.md"
        self.assertTrue(memory.exists(), "нуля нет — стирание памяти не привито")
        text = memory.read_text(encoding="utf-8")
        self.assertGreater(len(text), 1000, "нуль пуст — прививка холостая")
        for anchor in ("rtynbirf", "нуль", "РОЙ", " commons", "ADR-0007"):
            self.assertIn(anchor, text, f"нуль без якоря {anchor!r}")

    def test_state_parses(self):
        state = json.loads((SANDBOX / "STATE.json").read_text(encoding="utf-8"))
        for key in ("synced_at", "session_id", "author", "directive", "recovery"):
            self.assertIn(key, state, f"STATE без {key!r} — точка прерывания нечитаема")
        self.assertEqual(state["author"], "rtynbirf")
        self.assertIn("text", state["directive"])

    def test_scripts_mirror_not_empty(self):
        scripts = list((SANDBOX / "scripts").glob("*"))
        self.assertTrue(scripts, "зеркало скриптов пустое")

    def test_adr_in_journal(self):
        adr = ROOT / "docs/adr/ADR-0007-memory-vaccine.md"
        self.assertTrue(adr.exists(), "решения нет в журнале — храповик прокручен назад")
        self.assertIn("Статус", adr.read_text(encoding="utf-8"))

    def test_manifest_declares_vaccine(self):
        manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["body"].get("vaccine"), "sandbox/")


if __name__ == "__main__":
    unittest.main()
