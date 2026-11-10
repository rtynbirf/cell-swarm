"""CI-приёмка песочницы ρ-Governor (TH-SG-2).

Гипотезы H1–H3 из nous@main docs/genesis/semantic-governor.md §6;
решение о песочнице — cell-swarm docs/adr/ADR-0015. Офлайн, детерминизм,
умещается в секунды: кампания на 1 сид (3 руки × 3 реплики) + правила
свежести GAC (H3) + κ-детектор на фиксированном мире.
"""
import pathlib
import sys
import unittest

_SB = pathlib.Path(__file__).resolve().parent.parent / "sandbox" / "governor-h123"
sys.path.insert(0, str(_SB))

import selftest  # noqa: E402
import sim  # noqa: E402


class TestSemanticStateFreshness(unittest.TestCase):
    """H3: просрочка/порча semantic_state понижает полосу до amber."""

    def setUp(self):
        self.now = selftest.dt.datetime(2026, 11, 10, 12, 0, 0)

    def test_fresh_keeps_band(self):
        st = {"measured_at": "2026-11-08T00:00:00", "rhi_band": "green"}
        self.assertEqual(selftest.semantic_state_fresh(st, self.now), "green")

    def test_stale_forced_amber(self):
        st = {"measured_at": "2026-10-01T00:00:00", "rhi_band": "green"}
        self.assertEqual(selftest.semantic_state_fresh(st, self.now), "amber")

    def test_broken_date_fail_closed(self):
        st = {"measured_at": "мусор", "rhi_band": "green"}
        self.assertEqual(selftest.semantic_state_fresh(st, self.now), "amber")

    def test_missing_field_fail_closed(self):
        self.assertEqual(selftest.semantic_state_fresh({"rhi_band": "red"}, self.now), "amber")


class TestKappaDetector(unittest.TestCase):
    """κ-детектор ловит подсадной картель на детерминированном мире."""

    def test_cartel_inflates_hhi(self):
        ep = sim.run_episode(0, "none", 0)
        self.assertGreater(ep["hhi_peak"], sim.KAPPA_HHI_SIM)

    def test_governor_vent_fires_early(self):
        ep = sim.run_episode(0, "simple", 0)
        self.assertIsNotNone(ep["first_vent"])
        self.assertLessEqual(ep["first_vent"], 2)

    def test_governor_keeps_world_alive(self):
        ep = sim.run_episode(0, "simple", 0)
        self.assertGreater(ep["utilization"], 0.5)


class TestCampaignSmoke(unittest.TestCase):
    """Кампания на 1 сиде: отчёт собирается, ключи гипотез на месте."""

    def test_report_shape(self):
        rep = sim.campaign(1)
        for key in ("control", "governor_v01", "governor_v02",
                    "h1_no_harm[governor_v01]", "h2_mast_drop[governor_v01]"):
            self.assertIn(key, rep)


if __name__ == "__main__":
    unittest.main()
