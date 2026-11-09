"""Приёмка канона «память роя = файлы с допуском» (волна ×9, 2026-11-09).

Проверка 4 memory_check.py — ДОПУСК (acl) — fail-closed:
  a) acl обязателен в каждой записи;
  b) level ∈ {public, cell, swarm};
  c) reason непуст всегда — допуск без причины не выдаётся;
  d) при level != public owner_cell обязателен и обязан быть клеткой генома.
Только stdlib, офлайн, чистая функция check_acl — без сети и без файлов.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import memory_check  # noqa: E402

CELLS = {"cell-swarm", "polymath-os", "cell-rs", "voice-atlas-llm"}


def base_mem() -> dict:
    return {
        "id": "MEM-TEST",
        "statement": "тестовая строка знания",
        "tol": {"ttl_days": 30},
        "acl": {"level": "public", "reason": "тестовый допуск"},
        "source": {"repo": "rtynbirf/cell-swarm", "ref": "0" * 40,
                   "path": "README.md", "source_sha256": "0" * 64},
        "verified_at": "2026-11-09T00:00:00+00:00",
        "prev": "0" * 64,
        "hash": "0" * 64,
    }


class MemoryAcl(unittest.TestCase):
    def test_valid_public(self):
        self.assertIsNone(memory_check.check_acl(base_mem(), CELLS))

    def test_valid_cell_level(self):
        mem = base_mem()
        mem["acl"] = {"level": "cell", "owner_cell": "cell-swarm",
                      "reason": "внутренний такт клетки"}
        self.assertIsNone(memory_check.check_acl(mem, CELLS))

    def test_valid_swarm_level(self):
        mem = base_mem()
        mem["acl"] = {"level": "swarm", "owner_cell": "polymath-os",
                      "reason": "рой до публикации"}
        self.assertIsNone(memory_check.check_acl(mem, CELLS))

    def test_missing_acl_is_wound(self):
        mem = base_mem()
        del mem["acl"]
        self.assertIsNotNone(memory_check.check_acl(mem, CELLS))

    def test_bad_level_is_wound(self):
        mem = base_mem()
        mem["acl"] = {"level": "secret", "reason": "x"}
        self.assertIsNotNone(memory_check.check_acl(mem, CELLS))

    def test_empty_reason_is_wound(self):
        for reason in ("", "   ", None):
            mem = base_mem()
            mem["acl"] = {"level": "public", "reason": reason}
            self.assertIsNotNone(memory_check.check_acl(mem, CELLS),
                                 f"reason={reason!r} прошёл без раны")

    def test_cell_level_without_owner_is_wound(self):
        mem = base_mem()
        mem["acl"] = {"level": "cell", "reason": "x"}
        self.assertIsNotNone(memory_check.check_acl(mem, CELLS))

    def test_owner_outside_genome_is_wound(self):
        mem = base_mem()
        mem["acl"] = {"level": "cell", "owner_cell": "stranger-cell", "reason": "x"}
        self.assertIsNotNone(memory_check.check_acl(mem, CELLS))

    def test_owner_ok_when_genome_unreadable(self):
        # fail-open только для генома (пустое множество) — but проверка owner обязателен
        mem = base_mem()
        mem["acl"] = {"level": "cell", "owner_cell": "cell-swarm", "reason": "x"}
        self.assertIsNone(memory_check.check_acl(mem, set()))

    def test_production_memory_chain_with_acl(self):
        """Живая память роя: цепь пересчитывается ВМЕСТЕ с acl."""
        import hashlib
        files = sorted((ROOT / "memory").glob("MEM-*.json"))
        self.assertTrue(files, "память пуста")
        prev = "0" * 64
        for f in files:
            mem = json_load(f)
            body = {k: v for k, v in mem.items() if k != "hash"}
            h = hashlib.sha256(memory_check.canonical_json(body).encode()).hexdigest()
            self.assertEqual(h, mem["hash"], f"{mem['id']}: hash не сходится с acl")
            self.assertEqual(mem["prev"], prev, f"{mem['id']}: цепь разорвана")
            self.assertIsNone(memory_check.check_acl(mem, memory_check.genome_cells()),
                              f"{mem['id']}: живой acl невалиден")
            prev = h


def json_load(p: Path) -> dict:
    import json
    return json.loads(p.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
