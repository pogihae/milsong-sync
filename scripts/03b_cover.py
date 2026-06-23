"""
03b_cover.py — songs_enriched.json에 cover_url 추가

각 곡에 대해:
  1. MusicBrainz Recording Search → release MBID 획득
  2. Cover Art Archive → 커버 이미지 다운로드
  3. Vercel Blob 업로드 → blob URL 저장
  커버 없으면 PLACEHOLDER_URL 사용

필요:
  - milsong/.env.local 에 BLOB_READ_WRITE_TOKEN=vercel_blob_... 추가

사용:
  python scripts/03b_cover.py
  python scripts/03b_cover.py --limit 10   # 테스트
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT          = Path(__file__).parent.parent
ENRICHED_FILE = ROOT / "data" / "songs_enriched.json"

MB_SEARCH_URL = "https://musicbrainz.org/ws/2/recording"
CAA_URL       = "https://coverartarchive.org/release/{mbid}/front"
BLOB_URL      = "https://blob.vercel-storage.com"

MB_HEADERS = {
    "User-Agent": "milsong/1.0 (tir2986@gmail.com)",
    "Accept": "application/json",
}
RATE_LIMIT = 1.1


# ── 환경 ──────────────────────────────────────────────────────────────────────

def load_blob_token() -> str:
    for env_path in [
        ROOT.parent / "milsong" / ".env.local",
        ROOT / ".env",
    ]:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("BLOB_READ_WRITE_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("BLOB_READ_WRITE_TOKEN 없음. milsong/.env.local 확인")


# ── MusicBrainz ───────────────────────────────────────────────────────────────

def _clean_title(t: str) -> str:
    return re.sub(r"\s*\(feat\..*?\)", "", t, flags=re.IGNORECASE).strip()

def _clean_artist(a: str) -> str:
    m = re.search(r"\(([A-Za-z0-9][\w\s\-\.&']+)\)", a)
    return m.group(1).strip() if m else a

def _mb_query(query: str) -> list[dict]:
    try:
        r = requests.get(MB_SEARCH_URL, headers=MB_HEADERS,
                         params={"query": query, "fmt": "json", "limit": 5}, timeout=15)
    except requests.RequestException:
        return []
    if r.status_code == 429:
        wait = int(r.headers.get("Retry-After", 10))
        print(f"  MB rate limit — {wait}초 대기")
        time.sleep(wait)
        return _mb_query(query)
    return r.json().get("recordings", []) if r.ok else []

def get_release_mbid(title: str, artist: str) -> str | None:
    """MusicBrainz에서 첫 번째 매칭 release의 MBID 반환."""
    ct, ca = _clean_title(title), _clean_artist(artist)
    recs = _mb_query(f'recording:"{ct}" AND artist:"{ca}"')
    if not recs or int(recs[0].get("score", 0)) < 80:
        time.sleep(RATE_LIMIT)
        recs = _mb_query(f'"{ct}" "{ca}"')
    if not recs or int(recs[0].get("score", 0)) < 80:
        return None
    releases = recs[0].get("releases") or []
    return releases[0]["id"] if releases else None


# ── Cover Art Archive ─────────────────────────────────────────────────────────

def fetch_cover_image(mbid: str) -> bytes | None:
    """CAA에서 커버 이미지 bytes 반환. 없으면 None."""
    try:
        r = requests.get(CAA_URL.format(mbid=mbid),
                         headers={"User-Agent": MB_HEADERS["User-Agent"]},
                         allow_redirects=True, timeout=15)
        if r.ok and r.content:
            return r.content
    except requests.RequestException:
        pass
    return None


# ── Vercel Blob ───────────────────────────────────────────────────────────────

def upload_to_blob(song_id: str, image_bytes: bytes, token: str) -> str:
    """Vercel Blob에 업로드 → public URL 반환."""
    pathname = f"covers/{song_id}.jpg"
    r = requests.put(
        f"{BLOB_URL}/{pathname}",
        data=image_bytes,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "image/jpeg",
            "x-add-random-suffix": "0",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["url"]


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if not ENRICHED_FILE.exists():
        print("ERROR: songs_enriched.json 없음. 먼저 03_enrich.py 실행")
        return

    token = load_blob_token()

    enriched: dict[str, dict] = json.loads(ENRICHED_FILE.read_text(encoding="utf-8"))

    targets = [sid for sid, s in enriched.items() if s.get("cover_url") is None]
    if args.limit:
        targets = targets[:args.limit]

    print(f"커버 처리 대상: {len(targets)}곡")

    uploaded = skipped = failed = 0

    for i, sid in enumerate(targets, 1):
        song = enriched[sid]
        mbid = get_release_mbid(song["title"], song["artist"])
        time.sleep(RATE_LIMIT)

        if not mbid:
            enriched[sid]["cover_url"] = None
            skipped += 1
        else:
            img = fetch_cover_image(mbid)
            if img:
                try:
                    url = upload_to_blob(sid, img, token)
                    enriched[sid]["cover_url"] = url
                    uploaded += 1
                except Exception as e:
                    print(f"  Blob 업로드 실패 {sid}: {e}")
                    enriched[sid]["cover_url"] = None
                    failed += 1
            else:
                enriched[sid]["cover_url"] = None
                skipped += 1

        if i % 50 == 0 or i == len(targets):
            print(f"  {i}/{len(targets)}  업로드 {uploaded} / placeholder {skipped} / 실패 {failed}")
            ENRICHED_FILE.write_text(
                json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    print(f"\n완료: 업로드 {uploaded} / placeholder {skipped} / 실패 {failed}")


if __name__ == "__main__":
    main()
