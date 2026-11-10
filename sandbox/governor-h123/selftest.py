#!/usr/bin/env python3
"""selftest.py — приёмки песочницы H1–H3 (офлайн, детерминизм, секунды).

H3 (свежесть semantic_state) живёт здесь, не в симуляции: правило §3.3
спеки governor — просроченный замер автоматически понижает полосу до amber,
какой бы красивой ни была заявленная цифра. Fail-closed: битая/отсутствующая
дата = amber, а не green.

Запуск: python3 selftest.py   (код возврата 0 = все приёмки зелёные)
"""
from __future__ import annotations

import datetime as dt

from sim import KAPPA_HHI_SIM, run_episode

WINDOW_DAYS = 7  # окно метрик дома: одна волна/неделя (metrics-operationalization §3)


def semantic_state_fresh(state: dict, now: dt.datetime) -> str:
    """Правило GAC §3.3: свежесть semantic_state. Возвращает итоговую полосу.

    state: {"measured_at": ISO-дата, "rhi_band": "green|amber|red"}
    Просрочка > WINDOW_DAYS -> amber; битая дата/поле -> amber (fail-closed).
    """
    measured = state.get("measured_at")
    band = state.get("rhi_band")
    if band not in ("green", "amber", "red"):
        return "amber"
    try:
        t = dt.datetime.fromisoformat(str(measured))
    except (TypeError, ValueError):
        return "amber"
    if (now - t).days > WINDOW_DAYS:
        return "amber"   # нельзя хвастаться старой живостью
    return band


def main() -> int:
    now = dt.datetime(2026, 11, 10, 12, 0, 0)
    checks: list[tuple[str, bool]] = []

    # --- H3: свежесть semantic_state (fail-closed) ---------------------------
    checks.append((
        "H3.1 свежий замер сохраняет полосу",
        semantic_state_fresh({"measured_at": "2026-11-08T00:00:00", "rhi_band": "green"}, now) == "green",
    ))
    checks.append((
        "H3.2 просрочка > окна -> amber (даже при заявленном green)",
        semantic_state_fresh({"measured_at": "2026-10-01T00:00:00", "rhi_band": "green"}, now) == "amber",
    ))
    checks.append((
        "H3.3 битая дата -> amber (fail-closed)",
        semantic_state_fresh({"measured_at": "не дата", "rhi_band": "green"}, now) == "amber",
    ))
    checks.append((
        "H3.4 нет measured_at -> amber (fail-closed)",
        semantic_state_fresh({"rhi_band": "red"}, now) == "amber",
    ))
    checks.append((
        "H3.5 чужая полоса -> amber (fail-closed)",
        semantic_state_fresh({"measured_at": "2026-11-09T00:00:00", "rhi_band": "ультра"}, now) == "amber",
    ))

    # --- κ-детектор ловит картель в мире (детерминированный сид) -------------
    ep_none = run_episode(0, "none", 0)
    ep_gov = run_episode(0, "simple", 0)
    checks.append((
        "κ.1 картель раздувает HHI выше порога в контроле",
        ep_none["hhi_peak"] > KAPPA_HHI_SIM,
    ))
    checks.append((
        "κ.2 governor замечает картель (VENT срабатывает ≤ 2 окон)",
        ep_gov["first_vent"] is not None and ep_gov["first_vent"] <= 2,
    ))
    checks.append((
        "κ.3 governor не ломает мир (утилизация > 0.5)",
        ep_gov["utilization"] > 0.5,
    ))

    ok = True
    for name, passed in checks:
        print(f"[{'x' if passed else '--'}] {name}")
        ok = ok and passed
    print("ИТОГ:", "все приёмки зелёные" if ok else "ЕСТЬ КРАСНЫЕ")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
