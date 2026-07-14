#!/usr/bin/env python3
"""
Offline tests for webapp.py (Phase 5 web dashboard).

These exercise the pure data-payload functions against a temporary SQLite
database, the request -> params builders, and the JobRunner concurrency guard.
No sockets and no network are used, so the suite runs fully offline.

Run directly:
    PYTHONPATH=.:tests python3 tests/test_webapp.py
"""

import os
import sys
import tempfile
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import database as db
import webapp
from models import Game, Mirror


def _seed(conn):
    """Insert two games (one healthy, one with a dead mirror) + link checks."""
    mario = Game(
        title="Super Mario Odyssey",
        detail_url="https://example.test/mario",
        source_site="switchroms",
        category="switch-rom",
        platform="Nintendo Switch",
        meta_size="5 GB",
        meta_genre="Platformer",
    )
    mario.mirrors = [Mirror(
        format="NSP", size="5 GB", hoster="MediaFire",
        redirect_url="https://short.test/1", final_link="https://dl.test/mario.nsp",
    )]
    zelda = Game(
        title="The Legend of Zelda TotK",
        detail_url="https://example.test/zelda",
        source_site="switchroms",
        category="switch-rom",
        platform="Nintendo Switch",
    )
    zelda.mirrors = [Mirror(
        format="XCI", size="16 GB", hoster="1Fichier",
        redirect_url="", final_link="https://dl.test/zelda.xci",
    )]
    db.save_scrape(conn, [mario, zelda], "switchroms", mode="scrape")
    db.record_link_checks(conn, [
        {"url": "https://dl.test/mario.nsp", "hoster": "MediaFire",
         "link_type": "final", "resolved_link": "https://dl.test/mario.nsp",
         "status": "ACTIVE", "http_code": 200, "detail": "ok"},
        {"url": "https://dl.test/zelda.xci", "hoster": "1Fichier",
         "link_type": "final", "resolved_link": "https://dl.test/zelda.xci",
         "status": "DEAD", "http_code": 404, "detail": "not found"},
    ])


def _fresh_conn():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = db.connect(path)
    return conn, path


def test_stats_payload():
    conn, path = _fresh_conn()
    try:
        _seed(conn)
        s = webapp.stats_payload(conn)
        assert s["games_active"] == 2, s
        assert s["mirrors_active"] == 2, s
        assert s["links"]["total"] == 2, s
        assert s["links"]["active"] == 1, s
        assert s["links"]["dead"] == 1, s
        assert s["runs_total"] >= 1, s
        assert any(b["site"] == "switchroms" and b["count"] == 2 for b in s["by_site"]), s
        assert s["last_run"] is not None, s
    finally:
        conn.close()
        os.remove(path)
    print("  [ok] stats_payload")


def test_games_payload():
    conn, path = _fresh_conn()
    try:
        _seed(conn)
        games = webapp.games_payload(conn)
        assert len(games) == 2, len(games)
        by_title = {g["title"]: g for g in games}

        mario = by_title["Super Mario Odyssey"]
        assert mario["active_mirrors"] == 1, mario
        assert mario["dead_mirrors"] == 0, mario
        assert mario["mirror_count"] == 1, mario
        assert mario["mirrors"][0]["link_status"] == "ACTIVE", mario

        zelda = by_title["The Legend of Zelda TotK"]
        assert zelda["dead_mirrors"] == 1, zelda
        assert zelda["mirrors"][0]["link_status"] == "DEAD", zelda

        # search filter
        only_mario = webapp.games_payload(conn, search="mario")
        assert len(only_mario) == 1 and only_mario[0]["title"] == "Super Mario Odyssey", only_mario

        # site filter (unknown site -> empty)
        assert webapp.games_payload(conn, site="does-not-exist") == []
    finally:
        conn.close()
        os.remove(path)
    print("  [ok] games_payload")


def test_dead_links_payload():
    conn, path = _fresh_conn()
    try:
        _seed(conn)
        dead = webapp.dead_links_payload(conn)
        assert len(dead) == 1, dead
        assert dead[0]["url"] == "https://dl.test/zelda.xci", dead
        assert str(dead[0]["http_code"]) == "404", dead
    finally:
        conn.close()
        os.remove(path)
    print("  [ok] dead_links_payload")


def test_runs_payload():
    conn, path = _fresh_conn()
    try:
        _seed(conn)
        runs = webapp.runs_payload(conn)
        assert len(runs) >= 1, runs
        assert runs[0]["site"] == "switchroms", runs[0]
        assert runs[0]["games_found"] == 2, runs[0]
    finally:
        conn.close()
        os.remove(path)
    print("  [ok] runs_payload")


def test_sites_payload():
    sites = webapp.sites_payload()
    assert any(s["name"] == "switchroms" for s in sites), sites
    print("  [ok] sites_payload")


def test_param_builders():
    sp = webapp.scrape_params_from(
        {"site": "switchroms", "all": True, "search": "  mario  "}, "/tmp/x.db")
    assert sp["scrape_all"] is True, sp
    assert sp["search"] == "mario", sp
    assert sp["db_path"] == "/tmp/x.db", sp
    assert sp["output"] == "both", sp
    assert sp["workers"] == 5, sp

    empty = webapp.scrape_params_from({}, None)
    assert empty["site"] == "switchroms", empty
    assert empty["search"] is None, empty
    assert empty["scrape_all"] is False, empty

    cp = webapp.check_params_from({"workers": 20}, "/tmp/x.db")
    assert cp["workers"] == 20, cp
    assert cp["db_path"] == "/tmp/x.db", cp
    assert cp["csv_path"], cp  # a default csv path is filled in
    print("  [ok] param builders")


def test_jobrunner_single_flight():
    jobs = webapp.JobRunner()
    assert jobs.status()["status"] == "idle"

    gate = threading.Event()
    started = threading.Event()

    def target(params):
        started.set()
        gate.wait(5)
        return {"active": 3, "dead": 1, "newly_dead": 0}

    jid = jobs.start("check", target, {})
    assert jid is not None
    assert started.wait(2), "job did not start"
    assert jobs.is_running(), "job should be running"

    # a second job must be rejected while one is running
    assert jobs.start("scrape", target, {}) is None, "second job should be rejected"

    gate.set()
    for _ in range(60):
        if jobs.status(jid).get("status") == "done":
            break
        time.sleep(0.05)
    st = jobs.status(jid)
    assert st["status"] == "done", st
    assert "3 active" in st["detail"], st["detail"]
    print("  [ok] JobRunner single-flight + status")


def test_jobrunner_error():
    jobs = webapp.JobRunner()

    def boom(params):
        raise RuntimeError("kaboom")

    jid = jobs.start("scrape", boom, {})
    for _ in range(60):
        if jobs.status(jid).get("status") in ("done", "error"):
            break
        time.sleep(0.05)
    st = jobs.status(jid)
    assert st["status"] == "error", st
    assert "kaboom" in st["detail"], st
    print("  [ok] JobRunner error handling")


def run():
    tests = [
        test_stats_payload,
        test_games_payload,
        test_dead_links_payload,
        test_runs_payload,
        test_sites_payload,
        test_param_builders,
        test_jobrunner_single_flight,
        test_jobrunner_error,
    ]
    print("Running webapp tests...")
    for t in tests:
        t()
    print("All %d webapp tests passed." % len(tests))


if __name__ == "__main__":
    run()
