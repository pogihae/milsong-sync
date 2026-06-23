"""
06_seed_neon.py — chart-data.json → Neon(Vercel Postgres)

DATABASE_URL_UNPOOLED를 milsong/.env.local 또는 .env에서 읽음.
테이블이 이미 있으면 DROP 후 재생성.

사용: python scripts/06_seed_neon.py
"""

import json
import sys
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values

sys.stdout.reconfigure(encoding="utf-8")

ROOT        = Path(__file__).parent.parent
SOURCE_FILE = ROOT / "output" / "chart-data.json"

# DATABASE_URL 우선순위: milsong/.env.local → .env
def load_db_url() -> str:
    for env_path in [
        ROOT.parent / "milsong" / ".env.local",
        ROOT / ".env",
    ]:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL_UNPOOLED="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("DATABASE_URL_UNPOOLED를 찾을 수 없음. milsong/.env.local 또는 .env 확인")


DDL = """
DROP TABLE IF EXISTS chart_entries CASCADE;
DROP TABLE IF EXISTS songs CASCADE;
DROP TABLE IF EXISTS coverage CASCADE;

CREATE TABLE songs (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    artist       TEXT NOT NULL,
    artist_type  TEXT NOT NULL,
    release_date TEXT,
    cover_url    TEXT
);

CREATE TABLE chart_entries (
    id         SERIAL PRIMARY KEY,
    week_start TEXT    NOT NULL,
    rank       INTEGER NOT NULL,
    song_id    TEXT    NOT NULL REFERENCES songs(id)
);

CREATE INDEX idx_chart_week ON chart_entries(week_start);
CREATE INDEX idx_chart_song ON chart_entries(song_id);

CREATE TABLE coverage (
    first_week TEXT NOT NULL,
    last_week  TEXT NOT NULL
);
"""


def main():
    if not SOURCE_FILE.exists():
        print(f"ERROR: {SOURCE_FILE} 없음. 먼저 05_build.py 실행")
        return

    db_url = load_db_url()
    print(f"DB: {db_url[:40]}...")

    data = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    songs  = list(data["songs"].values())
    charts = data["charts"]
    cov    = data["coverage"]

    con = psycopg2.connect(db_url)
    cur = con.cursor()

    print("테이블 생성 중...")
    cur.execute(DDL)

    print(f"songs INSERT: {len(songs)}건...")
    execute_values(cur,
        "INSERT INTO songs (id, title, artist, artist_type, release_date, cover_url) VALUES %s",
        [(s["id"], s["title"], s["artist"], s["artistType"], s.get("releaseDate"), s.get("cover_url")) for s in songs],
        page_size=500,
    )

    print(f"chart_entries INSERT: {len(charts)}건...")
    execute_values(cur,
        "INSERT INTO chart_entries (week_start, rank, song_id) VALUES %s",
        [(c["weekStart"], c["rank"], c["songId"]) for c in charts],
        page_size=1000,
    )

    cur.execute("INSERT INTO coverage (first_week, last_week) VALUES (%s, %s)",
                (cov["firstWeek"], cov["lastWeek"]))

    con.commit()

    # 검증
    print("\n--- 검증 ---")
    cur.execute("SELECT COUNT(*) FROM songs");        print("songs:        ", cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM chart_entries"); print("chart_entries:", cur.fetchone()[0])
    cur.execute("SELECT * FROM coverage");             print("coverage:     ", cur.fetchone())
    cur.execute("""
        SELECT ce.rank, s.title, s.artist
        FROM chart_entries ce JOIN songs s ON s.id = ce.song_id
        WHERE ce.week_start = '2019-05-05'
        ORDER BY ce.rank LIMIT 5
    """)
    print("\n2019-05-05 Top5:")
    for rank, title, artist in cur.fetchall():
        print(f"  {rank}위  {title}  /  {artist}")

    cur.close()
    con.close()
    print("\n완료")


if __name__ == "__main__":
    main()
