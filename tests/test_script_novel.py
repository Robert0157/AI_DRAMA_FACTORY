"""Offline tests for the B-line novel renderer (no network)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.story_room import script_novel as sn  # noqa: E402


def _pkg() -> dict:
    return {
        "title": "測試劇",
        "logline": "一個測試。",
        "episode_outline": [
            {"ep": 1, "arc": 1, "title": "起始", "hook": "鉤子一",
             "summary": "少年啟程。", "cliffhanger": "門開了。"},
            {"ep": 2, "arc": 1, "title": "深化", "hook": "鉤子二",
             "summary": "真相浮現。", "cliffhanger": "燈滅了。"},
        ],
        "pilot": {"ep1": {"script_excerpt": "COLD OPEN\n\nINT. 房間 - 夜\n\n（鏡頭推進）……"}},
        "arcs": [{"arc": "第二弧：雙神聯動", "episodes": "15-28", "summary": "測試弧。"}],
    }


def test_cn_numbers():
    assert sn._cn_number(1) == "一"
    assert sn._cn_number(10) == "十"
    assert sn._cn_number(11) == "十一"
    assert sn._cn_number(56) == "五十六"


def test_build_novel_deterministic(tmp_path):
    md, stats = sn.build_novel(_pkg(), series_id="s1", cache_dir=tmp_path, llm=False)
    assert "《測試劇》劇本小說版" in md
    assert "第一集《起始》" in md and "第二集《深化》" in md
    assert "第二弧：雙神聯動" in md  # prose-style arc labels must pass through
    assert stats["episodes"] == 2 and stats["llm"] == 0


def test_cache_used_when_hash_matches(tmp_path):
    pkg = _pkg()
    row = pkg["episode_outline"][0]
    excerpt = sn._ep_excerpt(pkg, 1)
    h = sn._src_hash(pkg, row, excerpt)
    (tmp_path / "ep_01.md").write_text(
        f"<!-- src:{h} | model:x | 2026 -->\n\n快取正文。", encoding="utf-8")
    md, stats = sn.build_novel(pkg, series_id="s1", cache_dir=tmp_path, llm=False)
    assert "快取正文。" in md and stats["llm"] == 1


def test_stale_cache_reused_offline(tmp_path):
    (tmp_path / "ep_01.md").write_text(
        "<!-- src:deadbeef | model:x | 2026 -->\n\n舊正文。", encoding="utf-8")
    md, stats = sn.build_novel(_pkg(), series_id="s1", cache_dir=tmp_path, llm=False)
    # Source changed but regeneration is off: keep the novel prose, never downgrade.
    assert "舊正文。" in md and stats["stale"] == 1


def test_force_ignores_caches(tmp_path):
    (tmp_path / "ep_01.md").write_text(
        "<!-- src:deadbeef | model:x | 2026 -->\n\n舊正文。", encoding="utf-8")
    md, stats = sn.build_novel(_pkg(), series_id="s1", cache_dir=tmp_path, llm=False, force=True)
    assert "舊正文。" not in md and stats["fallback"] == 2
