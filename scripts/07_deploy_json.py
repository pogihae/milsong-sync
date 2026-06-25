"""
07_deploy_json.py — output/chart-data.json → milsong/data/chart-data.json 복사

앱이 JSON 모드로 동작할 때 사용. DB 모드 전환 후에는 불필요.

사용: python scripts/07_deploy_json.py
"""

import json
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT   = Path(__file__).parent.parent
SRC    = ROOT / "output" / "chart-data.json"
DST    = ROOT.parent / "milsong" / "data" / "chart-data.json"


def main():
    if not SRC.exists():
        print(f"ERROR: {SRC} 없음. 먼저 05_build.py 실행")
        return

    DST.parent.mkdir(exist_ok=True)
    shutil.copy2(SRC, DST)

    data = json.loads(DST.read_text(encoding="utf-8"))
    songs_with_cover = sum(1 for s in data["songs"].values() if s.get("cover_url"))
    print(f"복사 완료: songs {len(data['songs'])}곡 (커버 {songs_with_cover}곡)")
    print(f"coverage: {data['coverage']['firstWeek']} ~ {data['coverage']['lastWeek']}")
    print(f"→ {DST}")


if __name__ == "__main__":
    main()
