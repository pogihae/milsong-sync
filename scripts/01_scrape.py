"""
01_scrape.py — Circle Chart 주간 디지털종합 Top-10 수집

API:   POST https://circlechart.kr/data/api/chart/onoff
캐시:  data/cache/YYYY_WW.json  (재실행 시 스킵)
산출:  data/raw_entries.jsonl

주차 규칙:
  - 주는 일요일 시작
  - hitYear=Y, targetTime=WW  (Y의 1월 1일을 포함하는 주 = 01)
  - 예: hitYear=2010, targetTime=01 → 2009-12-27~2010-01-02

사용:
  python scripts/01_scrape.py              # 전체 (2010~현재)
  python scripts/01_scrape.py --test       # 1주차만 출력 (구조 확인)
  python scripts/01_scrape.py --year 2020  # 특정 연도만
"""

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT        = Path(__file__).parent.parent
CACHE_DIR   = ROOT / "data" / "cache"
OUTPUT_FILE = ROOT / "data" / "raw_entries.jsonl"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

API_URL     = "https://circlechart.kr/data/api/chart/onoff"
SERVICE_GBN = "ALL"   # 디지털종합
RATE_LIMIT  = 1.2     # 초당 요청 간격 (ToS 준수)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://circlechart.kr/page_chart/onoff.circle",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
}

START_YEAR = 2010
END_DATE   = date.today()


# ── 주차-날짜 변환 ─────────────────────────────────────────────────────────

def year_week1_start(year: int) -> date:
    """year의 1주차 시작일(일요일). Jan 1을 포함하는 직전 일요일."""
    jan1 = date(year, 1, 1)
    # Python weekday: Mon=0 ... Sun=6
    # 직전 일요일까지의 offset
    offset = (jan1.weekday() + 1) % 7
    return jan1 - timedelta(days=offset)


def iter_chart_weeks(start_year: int, end: date):
    """(circle_year, week_num, week_start_sunday) 순서로 yield."""
    for year in range(start_year, end.year + 2):
        w1 = year_week1_start(year)
        w1_next = year_week1_start(year + 1)
        n_weeks = (w1_next - w1).days // 7
        for wk in range(1, n_weeks + 1):
            ws = w1 + timedelta(weeks=wk - 1)
            if ws > end:
                return
            yield year, wk, ws


# ── 캐시 & API ────────────────────────────────────────────────────────────

def cache_path(year: int, week: int) -> Path:
    return CACHE_DIR / f"{year}_{week:02d}.json"


def fetch_chart(year: int, week: int) -> dict:
    cp = cache_path(year, week)
    if cp.exists():
        return json.loads(cp.read_text(encoding="utf-8"))

    payload = {
        "nationGbn":  "T",
        "serviceGbn": SERVICE_GBN,
        "termGbn":    "week",
        "hitYear":    str(year),
        "targetTime": f"{week:02d}",
        "yearTime":   "3",
        "curUrl":     "",
    }
    resp = requests.post(API_URL, data=payload, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(RATE_LIMIT)
    return data


# ── 파싱 ──────────────────────────────────────────────────────────────────

def parse_chart(data: dict, week_start: date) -> list[dict]:
    if data.get("ResultStatus") != "OK":
        return []

    raw = data.get("List", {})
    # List는 {'0': {...}, '1': {...}, ...} 형태의 dict
    if isinstance(raw, dict):
        items = list(raw.values())
    else:
        items = raw  # 혹시 list 형태일 경우 대비

    entries = []
    for item in items:
        try:
            rank = int(item.get("SERVICE_RANKING", 0))
        except (ValueError, TypeError):
            continue
        if rank < 1 or rank > 10:
            continue
        title  = str(item.get("SONG_NAME",   "")).strip()
        artist = str(item.get("ARTIST_NAME", "")).strip()
        if not title or not artist:
            continue
        entries.append({
            "weekStart": week_start.isoformat(),
            "rank":      rank,
            "title":     title,
            "artist":    artist,
        })

    return sorted(entries, key=lambda e: e["rank"])[:10]


# ── 메인 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",  action="store_true", help="1주차만 출력")
    parser.add_argument("--year",  type=int, help="특정 연도만 수집")
    parser.add_argument("--month", type=int, help="특정 월만 수집 (--year와 함께)")
    parser.add_argument("--debug", action="store_true", help="raw JSON 출력")
    args = parser.parse_args()

    weeks = list(iter_chart_weeks(START_YEAR, END_DATE))
    if args.year:
        weeks = [(y, w, ws) for y, w, ws in weeks if y == args.year]
    if args.month:
        weeks = [(y, w, ws) for y, w, ws in weeks if ws.month == args.month]
    if args.test:
        weeks = weeks[:1]

    print(f"수집 대상: {len(weeks)}주차  ({weeks[0][2]} ~ {weeks[-1][2]})")

    all_entries: list[dict] = []
    failed: list[tuple] = []

    for i, (year, week, week_start) in enumerate(weeks, 1):
        try:
            data    = fetch_chart(year, week)
            entries = parse_chart(data, week_start)

            if args.test:
                print(f"\n[TEST] {year}년 {week:02d}주차 ({week_start}) - {len(entries)}곡")
                for e in entries:
                    print(f"  {e['rank']:2d}위  {e['title']}  /  {e['artist']}")
                if args.debug:
                    print("\n--- raw JSON (처음 1000자) ---")
                    print(json.dumps(data, ensure_ascii=False)[:1000])
                return

            if not entries:
                status = data.get("ResultStatus", "?")
                if status != "OK":
                    # 아직 집계 안 된 미래 주차 등 → 조용히 스킵
                    print(f"  SKIP {year}년 {week:02d}주차 ({week_start}) - {status}")
                else:
                    failed.append((year, week, week_start))
                    print(f"  WARN 0건: {year}년 {week:02d}주차 ({week_start})")
            else:
                all_entries.extend(entries)

            if i % 50 == 0 or i == len(weeks):
                print(f"  진행: {i}/{len(weeks)}  누적 {len(all_entries)}건")

        except requests.HTTPError as e:
            failed.append((year, week, week_start))
            print(f"  ERROR HTTP {e.response.status_code}: {year}년 {week:02d}주차")
        except Exception as e:
            failed.append((year, week, week_start))
            print(f"  ERROR {year}년 {week:02d}주차: {e}")

    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n완료: {len(all_entries)}건 -> {OUTPUT_FILE}")
    if failed:
        print(f"파싱 실패 {len(failed)}주차: "
              f"{[str(ws) for _, _, ws in failed[:10]]}"
              f"{'...' if len(failed) > 10 else ''}")


if __name__ == "__main__":
    main()
