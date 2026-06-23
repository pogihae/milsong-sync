"""
03_enrich.py — MusicBrainz Recording Search API로 releaseDate 채우기

songs.json의 각 Song에 대해 title+artist로 MusicBrainz 검색 → releaseDate 매칭.
score >= 80인 결과만 채움. 매칭 실패 시 releaseDate = null 유지.

사용:
  python scripts/03_enrich.py          # 전체
  python scripts/03_enrich.py --limit 50   # 처음 50곡만 (테스트)
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent

SONGS_FILE    = ROOT / "data" / "songs.json"
ENRICHED_FILE = ROOT / "data" / "songs_enriched.json"

MB_SEARCH_URL = "https://musicbrainz.org/ws/2/recording"
HEADERS = {
    "User-Agent": "milsong/1.0 (tir2986@gmail.com)",
    "Accept": "application/json",
}
RATE_LIMIT_SECS = 1.1   # MusicBrainz 정책: 1 req/sec
SCORE_THRESHOLD = 80


def clean_title(title: str) -> str:
    """Feat. 괄호 제거: '사랑 (Feat. 박효신)' → '사랑'"""
    return re.sub(r"\s*\(feat\..*?\)", "", title, flags=re.IGNORECASE).strip()


def extract_artist(artist: str) -> str:
    """괄호 안 영문명 우선 반환: '티아라 (T-ara)' → 'T-ara', '이승기' → '이승기'"""
    m = re.search(r"\(([A-Za-z0-9][\w\s\-\.&']+)\)", artist)
    if m:
        return m.group(1).strip()
    return artist


def _query_mb(query: str) -> list[dict]:
    """MusicBrainz Recording Search 실행 → recordings 리스트 반환."""
    try:
        resp = requests.get(
            MB_SEARCH_URL,
            headers=HEADERS,
            params={"query": query, "fmt": "json", "limit": 5},
            timeout=15,
        )
    except requests.RequestException:
        return []

    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 10))
        print(f"  Rate limit — {retry_after}초 대기")
        time.sleep(retry_after)
        return _query_mb(query)

    if not resp.ok:
        return []

    return resp.json().get("recordings", [])


def _extract_date(recording: dict) -> str:
    """recording에서 가장 이른 releaseDate 추출."""
    rg = recording.get("release-group") or {}
    rd = rg.get("first-release-date", "")
    if not rd:
        dates = [
            r.get("date", "")
            for r in (recording.get("releases") or [])
            if r.get("date")
        ]
        rd = min(dates) if dates else ""
    return rd


def search_release_date(title: str, artist: str) -> str | None:
    """MusicBrainz에서 곡 검색 → releaseDate('YYYY-MM-DD') 반환. 실패 시 None."""
    clean_t = clean_title(title)
    clean_a = extract_artist(artist)

    # 1차: 필드 한정 쿼리 (정확도 우선)
    recordings = _query_mb(f'recording:"{clean_t}" AND artist:"{clean_a}"')

    # 2차 폴백: 필드 없이 단순 쿼리
    if not recordings or int(recordings[0].get("score", 0)) < SCORE_THRESHOLD:
        time.sleep(RATE_LIMIT_SECS)
        recordings = _query_mb(f'"{clean_t}" "{clean_a}"')

    if not recordings:
        return None

    best = recordings[0]
    if int(best.get("score", 0)) < SCORE_THRESHOLD:
        return None

    rd = _extract_date(best)
    if not rd:
        return None

    # 정규화: YYYY → YYYY-01-01, YYYY-MM → YYYY-MM-01
    if len(rd) == 4:
        return f"{rd}-01-01"
    if len(rd) == 7:
        return f"{rd}-01"
    return rd  # 이미 YYYY-MM-DD


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="처음 N곡만 처리 (테스트용)")
    args = parser.parse_args()

    if not SONGS_FILE.exists():
        print(f"ERROR: {SONGS_FILE} 없음. 먼저 02_normalize.py 실행")
        return

    songs: dict[str, dict] = json.loads(SONGS_FILE.read_text(encoding="utf-8"))

    if ENRICHED_FILE.exists():
        enriched: dict[str, dict] = json.loads(ENRICHED_FILE.read_text(encoding="utf-8"))
    else:
        enriched = {sid: dict(s) for sid, s in songs.items()}

    ids_to_process = [
        sid for sid, s in enriched.items() if s.get("releaseDate") is None
    ]
    if args.limit:
        ids_to_process = ids_to_process[:args.limit]

    print(f"처리 대상: {len(ids_to_process)}곡 (전체 {len(enriched)}곡 중 미채움)")
    print(f"예상 소요: 약 {len(ids_to_process) * RATE_LIMIT_SECS * 2 / 60:.0f}분 (폴백 포함 최대)")

    matched = 0

    for i, sid in enumerate(ids_to_process, 1):
        song = enriched[sid]
        rd = search_release_date(song["title"], song["artist"])
        if rd:
            enriched[sid]["releaseDate"] = rd
            matched += 1

        time.sleep(RATE_LIMIT_SECS)

        if i % 100 == 0 or i == len(ids_to_process):
            print(f"  {i}/{len(ids_to_process)}  매칭됨 {matched}건")
            ENRICHED_FILE.write_text(
                json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    unmatched = len(ids_to_process) - matched
    print(f"\n완료: 매칭 {matched}건 / 미매칭 {unmatched}건 → {ENRICHED_FILE}")


if __name__ == "__main__":
    main()
