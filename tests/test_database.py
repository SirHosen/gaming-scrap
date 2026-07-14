"""Tests for the SQLite scrape-history database (Phase 2): run diffing
(new / changed / removed) and active-only export."""
import os
import tempfile

import database as db
from models import Game, Mirror


def _game(title, url, size="1 GB", final="https://mediafire.com/f1"):
    return Game(
        title=title, meta_size=size, meta_genre="RPG", detail_url=url,
        source_site="switchroms", category="switch-rom", platform="Nintendo Switch",
        mirrors=[Mirror(format="NSP ROM", size=size, hoster="Mediafire",
                        redirect_url=url + "/r", final_link=final)],
    )


def test_scrape_history_diffing():
    path = tempfile.mktemp(suffix=".db")
    conn = db.connect(path)
    try:
        # ── Run 1: two brand-new games ──
        s1 = db.save_scrape(conn,
                            [_game("Alpha", "https://x/alpha"),
                             _game("Bravo", "https://x/bravo")],
                            "switchroms", mode="all")
        assert s1.new == 2
        assert s1.removed == 0

        # ── Run 2 (full scrape): Alpha changed (size differs), Charlie new,
        #    Bravo missing → removed. ──
        s2 = db.save_scrape(conn,
                            [_game("Alpha", "https://x/alpha", size="2 GB"),
                             _game("Charlie", "https://x/charlie")],
                            "switchroms", mode="all")
        assert s2.new == 1
        assert s2.changed == 1
        assert s2.removed == 1

        # ── Active-only export excludes the removed game (Bravo) ──
        games = db.export_from_db(conn, site="switchroms", active_only=True)
        assert sorted(g.title for g in games) == ["Alpha", "Charlie"]

        # ── History records both runs ──
        runs = db.recent_runs(conn, limit=10)
        assert len(runs) == 2
    finally:
        conn.close()
        if os.path.exists(path):
            os.remove(path)


def test_search_mode_does_not_mark_removed():
    path = tempfile.mktemp(suffix=".db")
    conn = db.connect(path)
    try:
        db.save_scrape(conn, [_game("Alpha", "https://x/alpha"),
                              _game("Bravo", "https://x/bravo")],
                       "switchroms", mode="all")
        # A keyword search only returns Alpha; Bravo must NOT be flagged removed.
        s = db.save_scrape(conn, [_game("Alpha", "https://x/alpha")],
                           "switchroms", mode="search")
        assert s.removed == 0
    finally:
        conn.close()
        if os.path.exists(path):
            os.remove(path)


if __name__ == "__main__":
    import sys, os as _os
    sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
