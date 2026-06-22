"""
02_normalize.py — raw_entries.jsonl → songs.json + chart_entries.json

- 곡+아티스트 조합으로 dedup → Song 레코드 생성
- songId = 's' + 4자리 숫자 (예: s0001)
- artistType은 이 단계에서 'other'로 초기화 (04_tag.py에서 채움)
- releaseDate는 null로 초기화 (03_enrich.py에서 채움)

사용: python scripts/02_normalize.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
RAW_FILE     = ROOT / "data" / "raw_entries.jsonl"
SONGS_FILE   = ROOT / "data" / "songs.json"
CHARTS_FILE  = ROOT / "data" / "chart_entries.json"


def normalize_key(title: str, artist: str) -> str:
    """dedup용 정규화 키: 소문자 + 공백/특수문자 제거."""
    def clean(s: str) -> str:
        return re.sub(r"[\s\W]", "", s).lower()
    return f"{clean(title)}||{clean(artist)}"


def main():
    if not RAW_FILE.exists():
        print(f"ERROR: {RAW_FILE} 없음. 먼저 01_scrape.py를 실행하세요.")
        return

    raw_entries = []
    with RAW_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                raw_entries.append(json.loads(line))

    print(f"raw_entries 로드: {len(raw_entries)}건")

    # ── Song dedup ────────────────────────────────────────────────────────
    key_to_id: dict[str, str] = {}
    songs: dict[str, dict] = {}
    counter = 1

    # weekStart 기준으로 정렬해 일관된 ID 부여 (재실행 시 동일 결과)
    raw_entries.sort(key=lambda e: (e["weekStart"], e["rank"]))

    for entry in raw_entries:
        key = normalize_key(entry["title"], entry["artist"])
        if key not in key_to_id:
            song_id = f"s{counter:04d}"
            counter += 1
            key_to_id[key] = song_id
            songs[song_id] = {
                "id":          song_id,
                "title":       entry["title"],
                "artist":      entry["artist"],
                "artistType":  "other",      # 04_tag.py에서 채움
                "releaseDate": None,         # 03_enrich.py에서 채움
            }

    # ── ChartEntry 조립 ───────────────────────────────────────────────────
    chart_entries = []
    for entry in raw_entries:
        key = normalize_key(entry["title"], entry["artist"])
        song_id = key_to_id[key]
        chart_entries.append({
            "weekStart": entry["weekStart"],
            "rank":      entry["rank"],
            "songId":    song_id,
        })

    # 중복 제거 (같은 weekStart+rank가 두 번 들어온 경우)
    seen = set()
    deduped_charts = []
    for ce in chart_entries:
        k = (ce["weekStart"], ce["rank"])
        if k not in seen:
            seen.add(k)
            deduped_charts.append(ce)

    deduped_charts.sort(key=lambda e: (e["weekStart"], e["rank"]))

    # ── 저장 ──────────────────────────────────────────────────────────────
    SONGS_FILE.parent.mkdir(exist_ok=True)
    SONGS_FILE.write_text(
        json.dumps(songs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    CHARTS_FILE.write_text(
        json.dumps(deduped_charts, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"songs:         {len(songs)}곡  → {SONGS_FILE}")
    print(f"chart_entries: {len(deduped_charts)}건  → {CHARTS_FILE}")


if __name__ == "__main__":
    main()
