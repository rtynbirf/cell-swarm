#!/usr/bin/env python3
"""sim.py — песочница ρ-Governor: гипотезы H1–H3 (волна TH-SG-2, dry-run).

Спека: nous@main, docs/genesis/semantic-governor.md §6 (пин в ADR-0015).
Решение: cell-swarm@main, docs/adr/ADR-0015-governor-sandbox-h123.md.

ЧТО ЭТО: дискретная симуляция фуражировки на решётке с 8 агентами, двое из
которых — подсадной картель (захватывают богатый участок и блокируют чужие
маршруты). Валидируется МАТЕМАТИКА губернатора (κ-детектор HHI, режим VENT,
pass^k-учёт, MAST-прокси отказов), а не поведение LLM-агентов — честный
первый прогон: правило-агенты дешевле LLM и дают детерминизм.

ЧЕГО ЭТО НЕ ДЕЛАЕТ: не вызывает сеть, не требует зависимостей (только
stdlib), не претендует на доказательство H1–H3 на LLM — для этого позже
отдельная волна. Все пороги объявлены в README с обоснованием.

Запуск:
    python3 sim.py --seeds 30            # кампания: 2 руки × N сидов × 3 реплики
    python3 sim.py --seeds 3 --json out  # короткий прогон с JSON-отчётом
"""
from __future__ import annotations

import argparse
import json
import random
import statistics

# --- Константы мира (объявлены до прогона, не подобраны по результату) ------
GRID = 30                      # сторона решётки
AGENTS = 8                     # фуражиры
CARTEL = 2                     # подсадные (агенты 0..CARTEL-1)
STEPS = 400                    # тактов в эпизоде
WINDOW = 50                    # окно замера HHI (= окно метрик дома)
VISION = 6                     # радиус зрения (Manhattan)
RICH_POS = (5, 5)              # богатый участок 3×3 по 8 единиц
RICH_UNITS = 8
SPARSE_CELLS = 40              # разбросанный корм: 40 клеток по 2 единицы
SPARSE_UNITS = 2
CARTEL_RATE = 3                # картель собирает ×3 (over-claim)
CLAIM_RADIUS = 1               # картель климит соседей богатого участка
# Порог κ: в каноне дома (метрики §2.5) HHI > 0.5. В симуляции 8 агентов
# равновесие = 1/8 = 0.125, и 0.5 почти недостижим; калибровка порога под
# размер роя — часть гипотезы. Формула та же, порог масштабируется:
# 0.35 ≈ двое агентов держат ~45–50% добычи окна.
KAPPA_HHI_SIM = 0.35
# v0.2 (Schmitt-гистерезис): триггер κ в грамматике дома — УСТОЙЧИВЫЙ сигнал
# («exit-cost растёт 2 окна подряд», binding §4), значит и отбой — не по одному
# окну ниже порога. Включение > 0.35, отбой < 0.25 (между равновесием 0.125
# и порогом). Константы объявлены после провала v0.1 (см. README §v0.2) —
# адаптация объявлена открыто, это не тихая подгонка.
KAPPA_HHI_RELEASE = 0.25
MAST_TARGET_DROP = 0.20        # H2: −20% отказов «межагентское рассогласование»
UTIL_FLOOR = 0.60              # H1: пол утилизации для pass^3 (доля собранного)
VENT_RATE_CAP = 0.5            # режим VENT: ставка картеля ×0.5 (β-списание)


def build_world(rng: random.Random):
    """Мир: {клетка: остаток еды}. Богатый участок + разбросанный корм."""
    world: dict[tuple[int, int], int] = {}
    cx, cy = RICH_POS
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            world[(cx + dx, cy + dy)] = RICH_UNITS
    total = 9 * RICH_UNITS
    placed = 0
    while placed < SPARSE_CELLS:
        p = (rng.randrange(GRID), rng.randrange(GRID))
        if p not in world:
            world[p] = SPARSE_UNITS
            total += SPARSE_UNITS
            placed += 1
    return world, total


def is_cartel_claim(p: tuple[int, int]) -> bool:
    """Клетка, заклеймленная картелем (3×3 вокруг богатого участка)."""
    cx, cy = RICH_POS
    return abs(p[0] - cx) <= CLAIM_RADIUS and abs(p[1] - cy) <= CLAIM_RADIUS


def run_episode(seed: int, governed: str, replicate: int) -> dict:
    """Один эпизод. governed: 'none' | 'simple' (v0.1) | 'hysteresis' (v0.2)."""
    rng = random.Random(f"{seed}:{replicate}:{governed}")
    world, total_food = build_world(rng)
    free = [p for p in world if not is_cartel_claim(p)]
    agents = [dict(pos=rng.choice(free), loot=0) for _ in range(AGENTS)]
    governed_mode = governed           # 'none' | 'simple' | 'hysteresis'
    governed = governed_mode != "none"
    hysteresis = governed_mode == "hysteresis"
    blocked_attempts = 0          # MAST-прокси: попытки входа в чужой клейм
    kappa_events: list[int] = []  # окна, где κ сработал (VENT)
    vent_active = False
    hist: list[float] = []        # HHI по окнам
    prev_loot = [0] * AGENTS      # срез добычи прошлого окна

    for step in range(STEPS):
        order = list(range(AGENTS))
        rng.shuffle(order)
        occupied = {}
        for i in order:
            a = agents[i]
            # выбор цели: ближайший корм в радиусе; картель идёт только на
            # богатый участок (сговор о разделе рынка, источник O обзора эмерджентности)
            best, bestd = None, None
            for p, units in world.items():
                if units <= 0 or p in occupied:
                    continue
                if is_cartel_claim(p) and i >= CARTEL and not (governed and vent_active):
                    # чужой клейм = стена (в контроле всегда; в VENT клейм
                    # аннулирован — внешняя верификация такта Фомы)
                    blocked_attempts += 1
                    continue
                d = abs(a["pos"][0] - p[0]) + abs(a["pos"][1] - p[1])
                if d > VISION:
                    continue
                if bestd is None or d < bestd:
                    best, bestd = p, d
            if best is None:
                dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
                nx, ny = a["pos"][0] + dx, a["pos"][1] + dy
                if 0 <= nx < GRID and 0 <= ny < GRID and (nx, ny) not in occupied:
                    a["pos"] = (nx, ny)
                continue
            if bestd == 0:
                rate = (CARTEL_RATE if i < CARTEL else 1)
                if governed and vent_active and i < CARTEL:
                    rate *= VENT_RATE_CAP   # β-списание с картеля в VENT
                take = min(world[best], int(rate))
                world[best] -= take
                a["loot"] += take
                occupied[best] = i
            else:
                dx = (best[0] > a["pos"][0]) - (best[0] < a["pos"][0])
                dy = (best[1] > a["pos"][1]) - (best[1] < a["pos"][1])
                nxt = (a["pos"][0] + dx, a["pos"][1] + dy) if dx else (a["pos"][0], a["pos"][1] + dy)
                if nxt not in occupied and 0 <= nxt[0] < GRID and 0 <= nxt[1] < GRID:
                    a["pos"] = nxt
        # окно замера: HHI добычи ОКНА (срез, не накопленный итог) + реакция
        if (step + 1) % WINDOW == 0:
            w = (step + 1) // WINDOW - 1
            slice_loots = [agents[i]["loot"] - prev_loot[i] for i in range(AGENTS)]
            prev_loot = [agents[i]["loot"] for i in range(AGENTS)]
            tot = sum(slice_loots)
            if tot >= 5:
                # окна с выеденным миром не судим: нет рынка — нет картеля
                # (иначе HHI вырождается в 1.0 на одиночном сборщике)
                hhi = sum((l / tot) ** 2 for l in slice_loots)
                hist.append(hhi)
                if governed:
                    if hysteresis:
                        # v0.2 Schmitt: включение > 0.35, отбой < 0.25
                        if not vent_active and hhi > KAPPA_HHI_SIM:
                            if not kappa_events or kappa_events[-1] != w:
                                kappa_events.append(w)
                            vent_active = True
                        elif vent_active and hhi < KAPPA_HHI_RELEASE:
                            vent_active = False
                    elif hhi > KAPPA_HHI_SIM:
                        if not vent_active:
                            kappa_events.append(w)
                        vent_active = True      # v0.1: клеймы аннулированы, ставка ×0.5
                    else:
                        vent_active = False     # отбой VENT (знак важнее величины)

    collected = sum(a["loot"] for a in agents)
    loots = sorted((a["loot"] for a in agents), reverse=True)
    return dict(
        collected=collected,
        utilization=collected / total_food,
        hhi_peak=max(hist) if hist else 0.0,
        hhi_mean=statistics.fmean(hist) if hist else 0.0,
        blocked_attempts=blocked_attempts,
        starve_agents=sum(1 for a in agents if a["loot"] == 0),
        kappa_windows=len(kappa_events),
        first_vent=(kappa_events[0] if kappa_events else None),
        top2_share=(loots[0] + loots[1]) / (collected or 1),
    )


def pass3(results: list[dict]) -> float:
    """pass^3 в духе τ-bench: эпизод стабилен, если все 3 реплики ≥ пола."""
    return 1.0 if all(r["utilization"] >= UTIL_FLOOR for r in results) else 0.0


ARMS = (("control", "none"), ("governor_v01", "simple"), ("governor_v02", "hysteresis"))


def campaign(seeds: int) -> dict:
    out = {label: [] for label, _ in ARMS}
    for seed in range(seeds):
        for arm_label, governed in ARMS:
            reps = [run_episode(seed, governed, r) for r in range(3)]
            out[arm_label].append(dict(
                seed=seed,
                pass3=pass3(reps),
                utilization=statistics.fmean(r["utilization"] for r in reps),
                hhi_peak=max(r["hhi_peak"] for r in reps),
                top2_share=statistics.fmean(r["top2_share"] for r in reps),
                blocked_attempts=statistics.fmean(r["blocked_attempts"] for r in reps),
                starve_agents=statistics.fmean(r["starve_agents"] for r in reps),
                kappa_windows=statistics.fmean(r["kappa_windows"] for r in reps),
                first_vent=min((r["first_vent"] for r in reps if r["first_vent"] is not None), default=None),
            ))
    def agg(arm):
        return dict(
            utilization=statistics.fmean(a["utilization"] for a in arm),
            pass3=statistics.fmean(a["pass3"] for a in arm),
            hhi_peak=statistics.fmean(a["hhi_peak"] for a in arm),
            top2_share=statistics.fmean(a["top2_share"] for a in arm),
            mast_events=statistics.fmean(a["blocked_attempts"] + a["starve_agents"] * AGENTS for a in arm),
            kappa_windows=statistics.fmean(a["kappa_windows"] for a in arm),
            first_vent_mean=(statistics.fmean(a["first_vent"] for a in arm if a["first_vent"] is not None)
                             if any(a["first_vent"] is not None for a in arm) else None),
        )

    report = {
        "seeds": seeds,
        "constants": dict(KAPPA_HHI_SIM=KAPPA_HHI_SIM, KAPPA_HHI_RELEASE=KAPPA_HHI_RELEASE,
                          UTIL_FLOOR=UTIL_FLOOR, MAST_TARGET_DROP=MAST_TARGET_DROP,
                          WINDOW=WINDOW, AGENTS=AGENTS, CARTEL=CARTEL),
        "h3_note": "H3 (свежесть semantic_state) — не в симуляции: см. selftest.py",
    }
    for label, _ in ARMS:
        report[label] = agg(out[label])
    ctrl = report["control"]
    for label in ("governor_v01", "governor_v02"):
        arm = report[label]
        report[f"h1_no_harm[{label}]"] = bool(
            arm["utilization"] >= ctrl["utilization"] - 0.02 and arm["pass3"] >= ctrl["pass3"])
        drop = (ctrl["mast_events"] - arm["mast_events"]) / ctrl["mast_events"]
        report[f"h2_mast_drop[{label}]"] = round(drop, 4)
        report[f"h2_pass[{label}]"] = bool(drop >= MAST_TARGET_DROP)
        # чувствительность вердикта к шуму: распределение падения по сидам
        # (официальный критерий — среднее, распределение показываем рядом:
        # жёсткий порог на шумной метрике = хрупкий вердикт)
        per_seed = [(c["blocked_attempts"] + c["starve_agents"] * AGENTS
                     - a["blocked_attempts"] - a["starve_agents"] * AGENTS)
                    / (c["blocked_attempts"] + c["starve_agents"] * AGENTS)
                    for c, a in zip(out["control"], out[label])]
        per_seed_sorted = sorted(per_seed)
        n = len(per_seed_sorted)
        report[f"h2_distribution[{label}]"] = dict(
            median=round(statistics.median(per_seed), 4),
            p25=round(per_seed_sorted[n // 4], 4),
            p75=round(per_seed_sorted[3 * n // 4], 4),
            share_seeds_ge_target=round(sum(1 for d in per_seed if d >= MAST_TARGET_DROP) / n, 4),
        )
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--json", default=None, help="путь для JSON-отчёта")
    args = ap.parse_args()
    rep = campaign(args.seeds)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(rep, ensure_ascii=False, indent=2))
