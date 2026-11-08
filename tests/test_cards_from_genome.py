"""Храповик константной цепи SEALS.jsonl против карточек живого генома (×6).

Прогоняется как часть приёмок роя (make test), офлайн:

(a) живой репо-геном: swarm.json + константная SEALS.jsonl сходятся
    с карточками, восстановленными из генома — exit 0;
(b) подменённый геном (навык клетки изменён) — восстановленная карточка
    не совпадает с константной цепью — честный отказ;
(c) цепи нет — отказ без шумихи;
(d) сам верификатор-от-генома не трогает ни константную цепь, ни геном
    (mtime байт-в-байт до и после).

Только stdlib + subprocess; живые файлы репо только читаются.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "verify_cards_from_genome.py"
SEALS = ROOT / "SEALS.jsonl"
GENOME = ROOT / "swarm.json"


def run_tool(genome: Path, seals: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), "--genome", str(genome), "--seals", str(seals)],
        capture_output=True, text=True)


@unittest.skipUnless(SEALS.is_file() and GENOME.is_file(),
                     "константная цепь/геном отсутствуют — живой дожим не доехал")
class TestCardsFromGenome(unittest.TestCase):

    def test_a_live_genome_matches_constant_chain(self):
        r = run_tool(GENOME, SEALS)
        self.assertEqual(r.returncode, 0,
                         "живой геном обязан сходиться с константной цепью:\n%s%s"
                         % (r.stdout, r.stderr))
        self.assertIn("🟢", r.stdout)

    def test_b_tampered_genome_is_rejected(self):
        genome = json.loads(GENOME.read_text(encoding="utf-8"))
        cell = genome["cells"][0]
        cell.setdefault("skills", []).append("навык-подмена-для-теста")
        with tempfile.TemporaryDirectory(prefix="cards-tampered-") as tmp:
            bad = Path(tmp) / "swarm.json"
            bad.write_text(json.dumps(genome, ensure_ascii=False), encoding="utf-8")
            r = run_tool(bad, SEALS)
            self.assertNotEqual(r.returncode, 0,
                                "подменённый геном обязан получать отказ верификатора")
            self.assertIn("ОТКАЗ", r.stdout)

    def test_c_missing_chain_is_honest_refusal(self):
        with tempfile.TemporaryDirectory(prefix="cards-nochain-") as tmp:
            r = run_tool(GENOME, Path(tmp) / "SEALS.jsonl")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("не существует", r.stdout)

    def test_d_tool_touches_neither_chain_nor_genome(self):
        before_chain = hashlib.sha256(SEALS.read_bytes()).hexdigest()
        before_genome = hashlib.sha256(GENOME.read_bytes()).hexdigest()
        self.assertEqual(run_tool(GENOME, SEALS).returncode, 0)
        self.assertEqual(hashlib.sha256(SEALS.read_bytes()).hexdigest(), before_chain)
        self.assertEqual(hashlib.sha256(GENOME.read_bytes()).hexdigest(), before_genome)


if __name__ == "__main__":
    unittest.main()
