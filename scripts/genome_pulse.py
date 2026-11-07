#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Геномный пульс: геном роя сам открывает удар крови.

Что делает (по вызову workflow_dispatch — СОБЫТИЕ, не таймер):
1. Читает swarm.json (ЖЕЛАЕМОЕ: пины клеток).
2. Спрашивает GitHub API живые HEAD (НАБЛЮДАЕМОЕ).
3. Слет конверт крови (допуск eps=0: SHA сверяется точно), прививает его
   к хвосту летописи blood/LEDGER.jsonl и дописывает (ДЕЙСТВИЕ).
4. Dispatch → первая клетка цепи (runtime-protocol) — кровь потекла.
Каждый шаг печатает ФАКТ (HTTP-код, хеш, статус).

Переменные: GH_TOKEN (обязателен), BLOOD_FIRST_CELL (по умолчанию
rtynbirf/runtime-protocol), BLOOD_LEDGER_PATH (по умолчанию blood/LEDGER.jsonl).
"""
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "blood" / "kernel"))
from blood import canonical_json, chain_verify, make_envelope, tail_hash  # noqa: E402

API = "https://api.github.com"
OWNER = "rtynbirf"
LEDGER_REPO = os.environ.get("BLOOD_LEDGER_REPO", "rtynbirf/cell-swarm")
LEDGER_PATH = os.environ.get("BLOOD_LEDGER_PATH", "blood/LEDGER.jsonl")
FIRST_CELL = os.environ.get("BLOOD_FIRST_CELL", "rtynbirf/runtime-protocol")
TTL_S = 900  # удар крови должен догнать цепь быстрее, чем высохнет


def api(method, url, token, payload=None):
    req = urllib.request.Request(
        url, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def live_head(token, repo):
    st, data = api("GET", f"{API}/repos/{repo}/commits/HEAD", token)
    if st != 200:
        sys.exit(f"ФАКТ: живой HEAD {repo} не получен: HTTP {st}")
    return data["sha"]


def read_ledger(token):
    st, data = api("GET", f"{API}/repos/{LEDGER_REPO}/contents/{LEDGER_PATH}?ref=main", token)
    if st == 404:
        return [], None
    if st != 200:
        sys.exit(f"ФАКТ: летопись не прочитана: HTTP {st}")
    return base64.b64decode(data["content"]).decode("utf-8").splitlines(), data["sha"]


def write_ledger(token, lines, file_sha, message):
    content = ("\n".join(lines) + "\n").encode("utf-8")
    payload = {"message": message, "content": base64.b64encode(content).decode()}
    if file_sha:
        payload["sha"] = file_sha
    st, resp = api("PUT", f"{API}/repos/{LEDGER_REPO}/contents/{LEDGER_PATH}", token, payload)
    print(f"ФАКТ: летопись дописана: HTTP {st} (200/201=да) commit={str(resp.get('commit', {}).get('sha'))[:7]}")
    if st not in (200, 201):
        sys.exit(3)


def main():
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        sys.exit("ФАКТ: нет GH_TOKEN — геном не бьёт вслепую")

    genome = json.loads((Path(__file__).resolve().parent.parent / "swarm.json").read_text("utf-8"))
    cells = {c["name"]: c for c in genome["cells"]}

    lines, file_sha = read_ledger(token)
    ok, reason, n = chain_verify(lines)
    print(f"ФАКТ: летопись до удара: цепь {'целая' if ok else 'СЛОМАНА'} ({reason}), конвертов {n}")
    if not ok:
        sys.exit(2)

    # НАБЛЮДАЕМОЕ: живые HEAD клеток цепи пульса
    chain_names = ["runtime-protocol", "polymath-os"]
    observed = {}
    for name in chain_names:
        repo = cells[name]["repo"].removeprefix("https://").removesuffix(".git")
        observed[name] = live_head(token, repo)
        print(f"ФАКТ: живой HEAD {name} = {observed[name][:12]}")

    pulse_no = 1 + n  # номер удара = длина летописи + 1
    env = make_envelope(
        src="cell-swarm", dst="runtime-protocol", seq=pulse_no,
        payload={"cells": observed, "tol": {"eps": 0, "deadband": 0},
                 "note": "геномный пульс: сверка пинов живыми HEAD"},
        prev_hash=tail_hash(lines), ttl_s=TTL_S)
    print(f"ФАКТ: конверт пульса #{pulse_no} слит: hash={env['hash'][:12]}… ttl={TTL_S}s")

    write_ledger(token, lines + [canonical_json(env)], file_sha,
                 f"blood: геномный пульс #{pulse_no} → runtime-protocol")

    body = {"event_type": "blood-pulse", "client_payload": {"envelope": env}}
    st, resp = api("POST", f"{API}/repos/{FIRST_CELL}/dispatches", token, body)
    print(f"ФАКТ: dispatch {FIRST_CELL}: HTTP {st} (204=кровь потекла)")
    if st != 204:
        sys.exit(4)


if __name__ == "__main__":
    main()
