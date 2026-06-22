"""
05_build.py — 최종 chart-data.json 조립

입력:  data/songs_tagged.json + data/chart_entries.json
출력:  output/chart-data.json  (spec §3 Dataset 스키마)

사용: python scripts/05_build.py
"""

import json
from pathlib import Path

ROOT         = Path(__file__).parent.parent
TAGGED_FILE  = ROOT / "data" / "songs_tagged.json"
CHARTS_FILE  = ROOT / "data" / "chart_entries.json"
OUTPUT_FILE  = ROOT / "output" / "chart-data.json"


def main():
    if not TAGGED_FILE.exists():
        print(f"ERROR: {TAGGED_FILE} 없음. 먼저 04_tag.py 실행")
        return
    if not CHARTS_FILE.exists():
        print(f"ERROR: {CHARTS_FILE} 없음. 먼저 02_normalize.py 실행")
        return

    songs: dict[str, dict] = json.loads(TAGGED_FILE.read_text(encoding="utf-8"))
    charts: list[dict]     = json.loads(CHARTS_FILE.read_text(encoding="utf-8"))

    # releaseDate=None인 Song에서 null → 스코어러가 신선도 스킵 처리하므로 그대로 유지

    # coverage 계산
    week_starts = sorted({ce["weekStart"] for ce in charts})
    if not week_starts:
        print("ERROR: chart_entries가 비어 있음")
        return

    coverage = {
        "firstWeek": week_starts[0],
        "lastWeek":  week_starts[-1],
    }

    # Dataset 조립 (spec §3.1)
    dataset = {
        "coverage": coverage,
        "songs":    songs,
        "charts":   charts,
    }

    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    size_mb = OUTPUT_FILE.stat().st_size / 1_000_000
    print(f"완료: songs {len(songs)}곡 / charts {len(charts)}건")
    print(f"coverage: {coverage['firstWeek']} ~ {coverage['lastWeek']}")
    print(f"→ {OUTPUT_FILE}  ({size_mb:.1f} MB)")
    print(f"\n다음 단계: output/chart-data.json → milsong/data/chart-data.json 으로 복사")


if __name__ == "__main__":
    main()
