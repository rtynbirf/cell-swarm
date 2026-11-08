"""Храповик пина корня пломб-цепи карточек (Э-2.2 · #9, волна ×6).

scripts/pin.py обязан после регенерации пинов клеток дописывать в геном
аддитивное поле cards_seals — корень хеш-цепи SEALS.jsonl:

(a) цепи нет            — поле честно «цепь ещё не начата» (tip: null);
(b) цепь цела           — tip = sha256 канон-сериализации последней строки,
                          т.е. ровно тот prev_hash, которым пломбир продолжит цепь;
(c) цепь рвана/мусорная — честный отказ (exit != 0), не тихое переписывание;
(d) повторный прогон    — идемпотентен: геном без факта не переписывается,
                          а при появлении цепи tip обновляется.

Только stdlib; tempfile — реальный swarm.json в тестах не портится.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))

import pin  # noqa: E402
import seal_agent_cards  # noqa: E402 — перекрёстная сверка корня с пломбиром

TODAY = "2026-11-08"  # дата песочницы; поле updated_at обязано взять её, не «по памяти»


def canon(obj) -> bytes:
    """Независимый пересчёт формулы сцепки (та же, что у пломбира/верификатора)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_chain(path: Path, lines: list) -> None:
    """Пишет цепь в форме пломбира: по одной JSON-строке с sort_keys."""
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in lines),
        encoding="utf-8")


def build_lines(broken: bool = False) -> list:
    """Цепь на 3 строки: a.json (две строки — дрейф) и b.json (одна)."""
    prev = "0" * 64
    lines = []
    for i, card in enumerate(["a.json", "b.json", "a.json"], 1):
        line = {"ts": "2026-11-08T00:00:%02dZ" % i, "card": card,
                "sha256": "%064x" % i,
                "prev_hash": "f" * 64 if (broken and i == 2) else prev}
        prev = sha_hex(canon(line))
        lines.append(line)
    return lines


class SealsField(unittest.TestCase):
    """Юнит-уровень: seals_field/apply_cards_seals на tempfile-цепях."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pins-seals-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.seals = self.root / "SEALS.jsonl"

    # (a) цепи нет — честное «не начато»
    def test_field_created_without_chain(self):
        genome = {"cells": [{"name": "x"}]}
        self.assertTrue(pin.apply_cards_seals(genome, self.seals, today=TODAY))
        field = genome["cards_seals"]
        self.assertEqual(field["seals"], "SEALS.jsonl")
        self.assertIsNone(field["tip"])
        self.assertIn("диспатч", field["note"])
        self.assertEqual(field["updated_at"], TODAY)

    def test_empty_chain_file_is_not_started(self):
        self.seals.write_text("", encoding="utf-8")
        field = pin.seals_field(self.seals, today=TODAY)
        self.assertIsNone(field["tip"])
        self.assertIn("не начата", field["note"])

    # (b) целая цепь — tip = хеш последней строки
    def test_tip_is_last_line_hash(self):
        lines = build_lines()
        write_chain(self.seals, lines)
        genome = {}
        self.assertTrue(pin.apply_cards_seals(genome, self.seals, today=TODAY))
        field = genome["cards_seals"]
        self.assertEqual(field["tip"], sha_hex(canon(lines[-1])))
        self.assertEqual(field["cards"], 2, "a.json и b.json — две разные карточки")
        self.assertEqual(field["updated_at"], TODAY)
        # перекрёстная сверка: пломбир продолжит цепь ровно от запиненного корня
        self.assertEqual(field["tip"],
                         seal_agent_cards.chain_link_ok(
                             seal_agent_cards.load_seal_lines(self.seals)))

    # (c) рваная цепь — честный отказ, тихого переписывания нет
    def test_broken_chain_refused(self):
        write_chain(self.seals, build_lines(broken=True))
        genome = {"cells": []}
        with self.assertRaises(SystemExit):
            pin.apply_cards_seals(genome, self.seals)
        self.assertNotIn("cards_seals", genome)

    def test_garbage_chain_refused(self):
        self.seals.write_text("{не json}\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            pin.seals_field(self.seals)

    def test_short_hash_refused(self):
        lines = build_lines()
        lines[-1]["sha256"] = "abc123"
        write_chain(self.seals, lines)
        with self.assertRaises(SystemExit):
            pin.seals_field(self.seals)


class CliAndIdempotency(unittest.TestCase):
    """CLI-уровень: --seals-root и живой путь --write на tempfile-геноме."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pins-seals-cli-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.gpath = self.root / "swarm.json"
        self.gpath.write_text(json.dumps({
            "genome_version": "test",
            "cells": [{"name": "a", "repo": "https://github.com/x/a.git",
                       "pin": "0" * 40, "role": "тест",
                       "license_pre": "MIT (верифицировано живым GitHub API 2026-11-05)"}],
        }, ensure_ascii=False), encoding="utf-8")

    def run_pin(self, argv: list) -> int:
        # SEALS_PATH патчится всегда: тесты герметичны и не зависят от состояния
        # корня реального репо (константная цепь может появиться позже)
        with mock.patch.object(pin, "GENOME", self.gpath), \
                mock.patch.object(pin, "SEALS_PATH", self.root / "SEALS.jsonl"), \
                mock.patch.object(sys, "argv", ["pin.py"] + argv):
            return pin.main()

    # (a)+(d) через CLI: поле создано; повтор — файл байт-в-байт тот же
    def test_seals_root_write_then_idempotent(self):
        rc = self.run_pin(["--seals-root", "--write"])
        self.assertEqual(rc, 0)
        after_first = self.gpath.read_bytes()
        field = json.loads(after_first.decode("utf-8"))["cards_seals"]
        self.assertIsNone(field["tip"])
        self.assertIn("диспатч", field["note"])
        self.assertNotIn("fetched_at", json.loads(after_first.decode("utf-8")),
                         "офлайн-операция не ставит fetched_at: сеть не читалась")
        self.assertEqual(self.run_pin(["--seals-root", "--write"]), 0)
        self.assertEqual(self.gpath.read_bytes(), after_first)

    # (b)+(d) цепь появилась — tip обновился, повтор снова идемпотентен
    def test_chain_appearance_updates_tip_then_idempotent(self):
        self.run_pin(["--seals-root", "--write"])  # прогон без цепи: tip=null
        lines = build_lines()
        write_chain(self.root / "SEALS.jsonl", lines)
        self.assertEqual(self.run_pin(["--seals-root", "--write"]), 0)
        genome = json.loads(self.gpath.read_text(encoding="utf-8"))
        self.assertEqual(genome["cards_seals"]["tip"], sha_hex(canon(lines[-1])))
        self.assertEqual(genome["cards_seals"]["cards"], 2)
        after = self.gpath.read_bytes()
        self.assertEqual(self.run_pin(["--seals-root", "--write"]), 0)
        self.assertEqual(self.gpath.read_bytes(), after)

    # (c) через CLI: рваная цепь — exit != 0, геном на диске не тронут
    def test_seals_root_broken_chain_fails_and_does_not_write(self):
        write_chain(self.root / "SEALS.jsonl", build_lines(broken=True))
        before = self.gpath.read_bytes()
        with self.assertRaises(SystemExit) as ctx:
            self.run_pin(["--seals-root", "--write"])
        self.assertNotEqual(ctx.exception.code, 0)
        self.assertEqual(self.gpath.read_bytes(), before)

    # Живой путь: сеть не ответила (пины НЕ ВЗЯТЫ) — поле дописано,
    # fetched_at НЕ поставлен (живых данных не было — фейкать дату нельзя)
    def test_network_down_writes_only_cards_seals(self):
        with mock.patch.object(pin, "ls_remote_head",
                               side_effect=RuntimeError("сеть запрещена (офлайн-режим)")):
            rc = self.run_pin(["--write"])
        self.assertEqual(rc, 0)
        genome = json.loads(self.gpath.read_text(encoding="utf-8"))
        self.assertIn("cards_seals", genome)
        self.assertIsNone(genome["cards_seals"]["tip"])
        self.assertNotIn("fetched_at", genome)

    # Живой путь: пины взяты без дрейфа, поле без факта — геном не переписывается
    def test_network_same_pins_no_rewrite(self):
        self.run_pin(["--seals-root", "--write"])  # поле уже в геноме (tip=null)
        after = self.gpath.read_bytes()
        with mock.patch.object(pin, "ls_remote_head", return_value="0" * 40):
            rc = self.run_pin(["--write"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.gpath.read_bytes(), after,
                         "нет ни дрейфа пинов, ни факта в цепи — файл обязан остаться тем же")

    # Живой путь: рваная цепь блокирует запись генома ЦЕЛИКОМ, даже при дрейфе пинов
    def test_broken_chain_blocks_genome_write_despite_pin_drift(self):
        write_chain(self.root / "SEALS.jsonl", build_lines(broken=True))
        before = self.gpath.read_bytes()
        with mock.patch.object(pin, "ls_remote_head", return_value="2" * 40):
            with self.assertRaises(SystemExit):
                self.run_pin(["--write"])
        self.assertEqual(self.gpath.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
