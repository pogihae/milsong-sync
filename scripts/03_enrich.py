"""
03_enrich.py — Spotify Search API로 releaseDate 채우기

songs.json의 각 Song에 대해 title+artist로 Spotify 검색 → releaseDate 매칭.
매칭 실패 시 releaseDate = null 유지 (스코어링에서 신선도 보너스 스킵됨).

사전 조건:
  .env 파일에 SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET 설정

사용:
  python scripts/03_enrich.py          # 전체
  python scripts/03_enrich.py --limit 50   # 처음 50곡만 (테스트)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

SONGS_FILE    = ROOT / "data" / "songs.json"
ENRICHED_FILE = ROOT / "data" / "songs_enriched.json"

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
RATE_LIMIT_SECS = 0.2   # Spotify는 초당 5~10 요청 허용


def get_spotify_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(
        SPOTIFY_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def search_release_date(token: str, title: str, artist: str) -> str | None:
    """Spotify에서 곡 검색 → releaseDate('YYYY-MM-DD') 반환. 실패 시 None."""
    query = f"track:{title} artist:{artist}"
    resp = requests.get(
        SPOTIFY_SEARCH_URL,
        headers={"Authorization": f"Bearer {token}"},
        params={"q": query, "type": "track", "market": "KR", "limit": 1},
        timeout=10,
    )
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 5))
        print(f"  Rate limit — {retry_after}초 대기")
        time.sleep(retry_after)
        return search_release_date(token, title, artist)
    if not resp.ok:
        return None

    items = resp.json().get("tracks", {}).get("items", [])
    if not items:
        return None

    rd = items[0].get("album", {}).get("release_date", "")
    if not rd:
        return None
    # Spotify는 'YYYY', 'YYYY-MM', 'YYYY-MM-DD' 형식을 모두 반환할 수 있음
    if len(rd) == 4:
        return f"{rd}-01-01"
    if len(rd) == 7:
        return f"{rd}-01"
    return rd  # 이미 YYYY-MM-DD


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="처음 N곡만 처리 (테스트용)")
    args = parser.parse_args()

    client_id     = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("ERROR: .env에 SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET 필요")
        return

    if not SONGS_FILE.exists():
        print(f"ERROR: {SONGS_FILE} 없음. 먼저 02_normalize.py 실행")
        return

    songs: dict[str, dict] = json.loads(SONGS_FILE.read_text(encoding="utf-8"))

    # 이미 enriched 파일이 있으면 거기서 이어받아 이미 채워진 건 스킵
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

    token = get_spotify_token(client_id, client_secret)
    matched = 0
    token_refresh_counter = 0

    for i, sid in enumerate(ids_to_process, 1):
        song = enriched[sid]
        rd = search_release_date(token, song["title"], song["artist"])
        if rd:
            enriched[sid]["releaseDate"] = rd
            matched += 1

        time.sleep(RATE_LIMIT_SECS)
        token_refresh_counter += 1
        # Spotify 토큰은 60분 유효. 2000건마다 갱신.
        if token_refresh_counter >= 2000:
            token = get_spotify_token(client_id, client_secret)
            token_refresh_counter = 0

        if i % 100 == 0 or i == len(ids_to_process):
            print(f"  {i}/{len(ids_to_process)}  매칭됨 {matched}건")
            # 중간 저장 (재실행 시 이어받기 가능)
            ENRICHED_FILE.write_text(
                json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    ENRICHED_FILE.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    unmatched = len(ids_to_process) - matched
    print(f"\n완료: 매칭 {matched}건 / 미매칭 {unmatched}건 → {ENRICHED_FILE}")


if __name__ == "__main__":
    main()
