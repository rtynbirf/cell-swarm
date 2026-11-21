#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""zhivoe_litso_commit.py · дедуп полотна ЖИВОГО ЛИЦА (совет 6, РЁВО-ДЕДУП-0.1).

ПРОТОКОЛ (короткий):
  1) перерисовать полотно (--draw, команда приходит от автомата);
  2) проверить магию PNG (правило 15: гейт смотрит магию формата, не размер);
  3) sha256 нового banner.png против sha256 HEAD:banner.png;
  4) равны — тишина: 0 коммитов, 0 пушей, exit 0;
  5) разные — git add + commit: в сообщении дифференциал фактов (--facts,
     как у РЁВО-АВТОМАТА: n_files 2632→2636, коммиты 282→283, звёзды 0→0)
     и дельта sha256 + REVE=РЕВО (правило 12);
  6) --push — пуш по дисциплине правила 10: до 3 попыток, при отказе
     fetch + pull --rebase=merges origin <ветка>, повтор.

ЧАСТНЫЕ ГРАНИЦЫ (честно):
  * факты не переданы (--facts пуст) — закон молчит: 0 коммитов, 0 пушей,
    exit 0 («данных API нет — молчать, не рисовать»);
  * токенов внутри нет: только локальный git; доверие — кредам окружения;
  * автомат, красящий через contents-API без локального клона, хелпером не
    идёт: там зуб тот же, но сравнение — blob-ша текущего баннера до PUT;
  * штамп перерисовки в полотне ломает дедуп: штамп меняется при каждой
    перерисовке → байты всегда новые. Ставить штамп только при смене фактов;
  * хелпер коммитит только --banner, остальные изменения не трогает.
"""
import argparse
import hashlib
import os
import subprocess
import sys

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser(
        description="Дедуп-коммит полотна ЖИВОГО ЛИЦА: нет изменения sha256 — нет коммита.")
    ap.add_argument("--draw", required=True,
                    help="команда перерисовки полотна, напр. \"python3 make_banner.py\"")
    ap.add_argument("--facts", required=True,
                    help="дифференциал фактов, напр. \"коммиты 282→283, звёзды 0→0\"")
    ap.add_argument("--banner", default="banner.png", help="путь к полотну (по умолчанию banner.png)")
    ap.add_argument("--title", default="ЖИВОЕ ЛИЦО: полотно переписано реальными данными API",
                    help="заголовок коммита")
    ap.add_argument("--repo", default=".", help="корень рабочего дерева (по умолчанию текущий)")
    ap.add_argument("--push", action="store_true", help="пушить после коммита (правило 10: до 3 попыток)")
    args = ap.parse_args()

    cwd = os.path.abspath(args.repo)
    banner = os.path.join(cwd, args.banner)

    inside = run(["git", "rev-parse", "--is-inside-work-tree"], cwd)
    if inside.returncode != 0 or inside.stdout.strip() != b"true":
        print("не рабочее дерево git — тишина, exit 1")
        return 1

    facts = args.facts.strip()
    if not facts:
        # закон: в сообщении коммита — дифференциал фактов; нет фактов — нет коммита
        print("факты не переданы — по закону молчу (0 коммитов, 0 пушей)")
        return 0

    # 1) перерисовка
    draw = run(["bash", "-c", args.draw], cwd=cwd)  # shell-команда от автомата
    if draw.returncode != 0:
        print("перерисовка пала — тишина, мусор не коммитим")
        if draw.stderr:
            print(draw.stderr.decode("utf-8", "replace").strip()[-500:])
        return 1

    # 2) магия PNG (правило 15), не размер
    if not os.path.exists(banner):
        print(f"{args.banner} после перерисовки не существует — тишина, exit 1")
        return 1
    with open(banner, "rb") as f:
        head = f.read(8)
    if not head.startswith(PNG_MAGIC):
        print("магия PNG не на месте — запись незавершённая (правило 5), exit 1")
        return 1
    with open(banner, "rb") as f:
        new_sha = sha256_bytes(f.read())

    # 3) полотно в HEAD
    old = run(["git", "show", f"HEAD:{args.banner}"], cwd)
    if old.returncode == 0:
        old_sha = sha256_bytes(old.stdout)
    else:
        old_sha = None

    # 4) дедуп
    if old_sha == new_sha:
        print("полотно не изменилось — тишина")
        return 0

    # 5) коммит с дифференциалом фактов
    old_part = old_sha[:12] if old_sha else "пусто"
    add = run(["git", "add", "--", args.banner], cwd)
    if add.returncode != 0:
        print("git add пала: " + add.stderr.decode("utf-8", "replace").strip()[-300:])
        return 1
    subject = f"{args.title} ({facts})"
    body = f"ДЕДУП-ДЕЛЬТА: sha256 полотна {old_part}→{new_sha[:12]}. REVE=РЕВО"
    commit = run(["git", "commit", "-m", subject, "-m", body], cwd)
    if commit.returncode != 0:
        print("commit пал: " + commit.stderr.decode("utf-8", "replace").strip()[-300:])
        return 1
    print(f"коммит есть: sha256 полотна {old_part}→{new_sha[:12]} ({facts})")

    # 6) пуш (правило 10: до 3 попыток)
    if args.push:
        br = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.decode().strip()
        for attempt in range(1, 4):
            p = run(["git", "push", "origin", br], cwd)
            if p.returncode == 0:
                print(f"пуш прошёл с {attempt}-й попытки (ветка {br})")
                return 0
            print(f"пуш {attempt}/3 пал — fetch + rebase=merges, повтор")
            run(["git", "fetch", "origin", br], cwd)
            run(["git", "pull", "--rebase=merges", "origin", br], cwd)
        print("пуш не прошёл за 3 попытки — честный отказ, exit 1")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
