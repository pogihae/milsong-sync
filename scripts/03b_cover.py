"""
03b_cover.py — songs_enriched.json에 cover_url 추가

각 곡에 대해:
  1. iTunes Search API → 커버 이미지 URL 획득 (무료, 키 불필요)
  2. 이미지 다운로드 → Vercel Blob 업로드 → blob URL 저장
  커버 없으면 cover_url = null (앱에서 ♪ 폴백)

필요:
  - milsong/.env.local 에 BLOB_READ_WRITE_TOKEN=vercel_blob_... 추가

사용:
  python scripts/03b_cover.py
  python scripts/03b_cover.py --limit 10   # 테스트
"""

import argparse
import json
import sys
import time
from pathlib import Path
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT          = Path(__file__).parent.parent
ENRICHED_FILE = ROOT / "data" / "songs_enriched.json"

ITUNES_URL = "https://itunes.apple.com/search"
BLOB_URL   = "https://blob.vercel-storage.com"
HEADERS    = {"User-Agent": "milsong/1.0 (tir2986@gmail.com)"}


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


# ── iTunes ────────────────────────────────────────────────────────────────────

def fetch_itunes_image(title: str, artist: str) -> bytes | None:
    """iTunes Search로 커버 이미지 bytes 반환. 없으면 None."""
    try:
        r = requests.get(
            ITUNES_URL,
            headers=HEADERS,
            params={"term": f"{title} {artist}", "media": "music", "country": "kr", "limit": 1},
            timeout=10,
        )
        if not r.ok:
            return None
        results = r.json().get("results") or []
        if not results:
            return None
        art_url = results[0].get("artworkUrl100", "")
        if not art_url:
            return None
        # 100x100 → 600x600
        art_url = art_url.replace("100x100bb", "600x600bb")
        img = requests.get(art_url, headers=HEADERS, timeout=15)
        return img.content if img.ok else None
    except requests.RequestException:
        return None


# ── Vercel Blob ───────────────────────────────────────────────────────────────

def upload_to_blob(song_id: str, image_bytes: bytes, token: str) -> str:
    """Vercel Blob에 업로드 → public URL 반환."""
    r = requests.put(
        f"{BLOB_URL}/covers/{song_id}.jpg",
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

    # cover_url이 null이거나 아직 없는 것만 처리 (blob URL 있으면 스킵)
    targets = [sid for sid, s in enriched.items()
               if not s.get("cover_url")]
    if args.limit:
        targets = targets[:args.limit]

    print(f"커버 처리 대상: {len(targets)}곡")

    uploaded = skipped = failed = 0

    for i, sid in enumerate(targets, 1):
        song = enriched[sid]
        img = fetch_itunes_image(song["title"], song["artist"])
        time.sleep(0.3)  # iTunes soft limit 여유

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
            print(f"  {i}/{len(targets)}  업로드 {uploaded} / 없음 {skipped} / 실패 {failed}")
            ENRICHED_FILE.write_text(
                json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    print(f"\n완료: 업로드 {uploaded} / 없음 {skipped} / 실패 {failed}")


if __name__ == "__main__":
    main()
