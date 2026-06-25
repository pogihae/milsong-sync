"""
06_seed_sqlite.py — chart-data.json → SQLite DB

산출: output/milsong.db

사용: python scripts/06_seed_sqlite.py
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT        = Path(__file__).parent.parent
SOURCE_FILE = ROOT / "output" / "chart-data.json"
DB_FILE     = ROOT / "output" / "milsong.db"


DDL = """
CREATE TABLE IF NOT EXISTS songs (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    artist       TEXT NOT NULL,
    artist_type  TEXT NOT NULL,
    release_date TEXT,
    cover_url    TEXT
);

CREATE TABLE IF NOT EXISTS chart_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT    NOT NULL,
    rank       INTEGER NOT NULL,
    song_id    TEXT    NOT NULL REFERENCES songs(id)
);

CREATE INDEX IF NOT EXISTS idx_chart_week ON chart_entries(week_start);
CREATE INDEX IF NOT EXISTS idx_chart_song ON chart_entries(song_id);

CREATE TABLE IF NOT EXISTS coverage (
    first_week TEXT NOT NULL,
    last_week  TEXT NOT NULL
);
"""


def main():
    if not SOURCE_FILE.exists():
        print(f"ERROR: {SOURCE_FILE} 없음. 먼저 05_build.py 실행")
        return

    data = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))

    if DB_FILE.exists():
        DB_FILE.unlink()
        print(f"기존 DB 삭제")

    con = sqlite3.connect(DB_FILE)
    con.executescript(DDL)

    # songs
    songs = list(data["songs"].values())
    con.executemany(
        "INSERT INTO songs VALUES (?, ?, ?, ?, ?, ?)",
        [(s["id"], s["title"], s["artist"], s["artistType"], s.get("releaseDate"), s.get("cover_url")) for s in songs],
    )
    print(f"songs INSERT: {len(songs)}건")

    # chart_entries
    charts = data["charts"]
    con.executemany(
        "INSERT INTO chart_entries (week_start, rank, song_id) VALUES (?, ?, ?)",
        [(c["weekStart"], c["rank"], c["songId"]) for c in charts],
    )
    print(f"chart_entries INSERT: {len(charts)}건")

    # coverage
    cov = data["coverage"]
    con.execute("INSERT INTO coverage VALUES (?, ?)", (cov["firstWeek"], cov["lastWeek"]))

    con.commit()

    # 검증 쿼리
    print("\n--- 검증 ---")
    print("songs 수:        ", con.execute("SELECT COUNT(*) FROM songs").fetchone()[0])
    print("chart_entries 수:", con.execute("SELECT COUNT(*) FROM chart_entries").fetchone()[0])
    print("coverage:        ", con.execute("SELECT * FROM coverage").fetchone())
    print("\n2019-05-05 Top5:")
    rows = con.execute("""
        SELECT ce.rank, s.title, s.artist
        FROM chart_entries ce
        JOIN songs s ON s.id = ce.song_id
        WHERE ce.week_start = '2019-05-05'
        ORDER BY ce.rank
        LIMIT 5
    """).fetchall()
    for rank, title, artist in rows:
        print(f"  {rank}위  {title}  /  {artist}")

    con.close()
    size_kb = DB_FILE.stat().st_size // 1024
    print(f"\n→ {DB_FILE}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
