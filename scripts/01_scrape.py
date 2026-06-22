"""
01_scrape.py — Circle Chart (써클차트) 주간 디지털 Top-10 수집

산출: data/raw_entries.jsonl  (한 줄 = 한 ChartEntry 후보)
캐시: data/cache/YYYY_WW.html  (재실행 시 네트워크 스킵)

사용:
  python scripts/01_scrape.py              # 전체 (2010~현재)
  python scripts/01_scrape.py --test       # 1주차만 테스트 출력
  python scripts/01_scrape.py --year 2020  # 특정 연도만
"""

import argparse
import json
import time
import os
import sys
from datetime import date, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# ── 경로 설정 ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
CACHE_DIR = ROOT / "data" / "cache"
OUTPUT_FILE = ROOT / "data" / "raw_entries.jsonl"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── 수집 범위 ──────────────────────────────────────────────────────────────
START_DATE = date(2010, 1, 3)   # 2010년 첫째 주 일요일(weekStart)
END_DATE   = date.today()

# ── 네트워크 설정 ──────────────────────────────────────────────────────────
RATE_LIMIT_SECS = 1.2           # 요청 간격 (초)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://circlechart.kr/",
}

# ── URL 생성 ───────────────────────────────────────────────────────────────
BASE_URL = "https://circlechart.kr/page_chart/onoff.circle"

def build_url(year: int, week: int) -> str:
    """
    써클차트 주간 디지털종합(S1020) URL 구성.
    week = ISO 주차 번호 (1..53).
    실제 HTML을 먼저 --test로 확인하고, 파라미터 이름/값이 다르면 여기서 수정.
    """
    return (
        f"{BASE_URL}"
        f"?serviceGbn=S1020"
        f"&termGbn=week"
        f"&hitYear={year}"
        f"&targetTime={week:02d}"
        f"&yearTime=3"
        f"&log=Y"
    )

# ── ISO 주차 순회 ──────────────────────────────────────────────────────────
def iter_weeks(start: date, end: date):
    """(year, iso_week, week_start_sunday) 순서로 yield."""
    cur = start
    while cur <= end:
        iso = cur.isocalendar()
        yield iso[0], iso[1], cur
        cur += timedelta(weeks=1)

# ── 캐시 I/O ──────────────────────────────────────────────────────────────
def cache_path(year: int, week: int) -> Path:
    return CACHE_DIR / f"{year}_{week:02d}.html"

def fetch_html(year: int, week: int) -> str:
    cp = cache_path(year, week)
    if cp.exists():
        return cp.read_text(encoding="utf-8")
    url = build_url(year, week)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    html = resp.text
    cp.write_text(html, encoding="utf-8")
    time.sleep(RATE_LIMIT_SECS)
    return html

# ── HTML 파싱 ──────────────────────────────────────────────────────────────
def parse_chart(html: str, week_start: date) -> list[dict]:
    """
    HTML에서 Top-10 추출.
    써클차트 실제 HTML 구조에 맞게 셀렉터를 조정해야 할 수 있음.
    --test 모드로 먼저 raw HTML을 확인할 것.
    """
    soup = BeautifulSoup(html, "lxml")
    entries = []

    # 써클차트 테이블 행: tbody > tr. 각 셀에 순위·제목·아티스트가 있음.
    # 실제 구조 확인 후 아래 셀렉터를 수정할 것.
    rows = soup.select("tbody#tbody_chart tr")
    if not rows:
        # 대안 셀렉터 시도
        rows = soup.select("table.chart-box tbody tr")

    for row in rows:
        rank_el    = row.select_one("td.rank, .rank-num, td:nth-child(1)")
        title_el   = row.select_one("td.song, .song-name, td.title")
        artist_el  = row.select_one("td.artist, .artist-name")

        if not (rank_el and title_el and artist_el):
            continue

        try:
            rank = int(rank_el.get_text(strip=True).replace("위", "").replace("▲","").replace("▼","").replace("-","").strip())
        except ValueError:
            continue

        if rank < 1 or rank > 10:
            continue

        entries.append({
            "weekStart": week_start.isoformat(),
            "rank":      rank,
            "title":     title_el.get_text(strip=True),
            "artist":    artist_el.get_text(strip=True),
        })

    return entries[:10]  # 최대 10개


# ── 메인 ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",  action="store_true", help="1주차만 테스트 (HTML 구조 확인용)")
    parser.add_argument("--year",  type=int, help="특정 연도만 수집")
    parser.add_argument("--debug", action="store_true", help="파싱 실패 시 HTML 일부 출력")
    args = parser.parse_args()

    weeks = list(iter_weeks(START_DATE, END_DATE))
    if args.year:
        weeks = [(y, w, ws) for y, w, ws in weeks if y == args.year]
    if args.test:
        weeks = weeks[:1]

    total = len(weeks)
    print(f"수집 대상: {total}주차")

    all_entries = []
    failed = []

    for i, (year, week, week_start) in enumerate(weeks, 1):
        try:
            html = fetch_html(year, week)
            entries = parse_chart(html, week_start)

            if args.test:
                print(f"\n[TEST] {year}년 {week:02d}주차 ({week_start}) — {len(entries)}곡 파싱됨")
                for e in entries:
                    print(f"  {e['rank']:2d}위  {e['title']}  /  {e['artist']}")
                if args.debug or len(entries) == 0:
                    print("\n--- HTML (처음 3000자) ---")
                    print(html[:3000])
                return

            if len(entries) == 0:
                failed.append((year, week, week_start))
                print(f"  WARN 파싱 0건: {year}년 {week:02d}주차 ({week_start})")
            else:
                all_entries.extend(entries)

            if i % 50 == 0 or i == total:
                print(f"  진행: {i}/{total}  누적 {len(all_entries)}건")

        except requests.HTTPError as e:
            failed.append((year, week, week_start))
            print(f"  ERROR HTTP {e.response.status_code}: {year}년 {week:02d}주차")
        except Exception as e:
            failed.append((year, week, week_start))
            print(f"  ERROR {year}년 {week:02d}주차: {e}")

    # 저장
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n완료: {len(all_entries)}건 → {OUTPUT_FILE}")
    if failed:
        print(f"실패 {len(failed)}주차: {[str(ws) for _, _, ws in failed[:10]]}{'...' if len(failed)>10 else ''}")


if __name__ == "__main__":
    main()
