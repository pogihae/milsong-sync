"""
04_tag.py — artistType 태깅

전략:
1. known_girl_groups.txt에 아티스트명이 포함되면 → girl_group
2. known_boy_groups.txt에 포함되면 → boy_group
3. 나머지는 → other (v1 스코어링에는 무해)

v1에서 스코어에 영향을 주는 값은 girl_group뿐이므로
known_girl_groups.txt를 최우선으로 정확히 관리할 것.

사용: python scripts/04_tag.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR   = Path(__file__).parent
ENRICHED_FILE = ROOT / "data" / "songs_enriched.json"
TAGGED_FILE   = ROOT / "data" / "songs_tagged.json"
GG_FILE       = SCRIPTS_DIR / "known_girl_groups.txt"
BG_FILE       = SCRIPTS_DIR / "known_boy_groups.txt"


def load_name_set(path: Path) -> set[str]:
    if not path.exists():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.strip().lower() for line in lines if line.strip() and not line.startswith("#")}


def classify(artist: str, girl_groups: set[str], boy_groups: set[str]) -> str:
    a_lower = artist.lower()
    if any(gg in a_lower for gg in girl_groups):
        return "girl_group"
    if any(bg in a_lower for bg in boy_groups):
        return "boy_group"
    return "other"


def main():
    src_file = ENRICHED_FILE if ENRICHED_FILE.exists() else ROOT / "data" / "songs.json"
    if not src_file.exists():
        print(f"ERROR: {src_file} 없음. 먼저 02_normalize.py 실행")
        return

    songs: dict[str, dict] = json.loads(src_file.read_text(encoding="utf-8"))
    girl_groups = load_name_set(GG_FILE)
    boy_groups  = load_name_set(BG_FILE)

    print(f"걸그룹 목록: {len(girl_groups)}개  보이그룹 목록: {len(boy_groups)}개")

    tagged = {}
    counts = {"girl_group": 0, "boy_group": 0, "other": 0}
    for sid, song in songs.items():
        artist_type = classify(song["artist"], girl_groups, boy_groups)
        tagged[sid] = {**song, "artistType": artist_type}
        counts[artist_type] = counts.get(artist_type, 0) + 1

    TAGGED_FILE.write_text(
        json.dumps(tagged, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"태깅 완료: {counts}")
    print(f"→ {TAGGED_FILE}")
    print(f"\n※ girl_group 미분류가 많으면 known_girl_groups.txt에 추가하세요.")


if __name__ == "__main__":
    main()
