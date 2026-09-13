"""Generation preflight tests use mocks only; no Seedance or LLM calls."""
from unittest.mock import Mock

import pytest

from Auto_Drama.auto_drama import lmd_video_chain as chain


@pytest.mark.parametrize("prompt,urls", [
    ("", ["reference.png"]),
    ("no reference token", ["reference.png"]),
    ("@图片0", ["reference.png"]),
    ("@图片2", ["reference.png"]),
    ("@圖片1", []),
])
def test_prompt_must_be_prepared_before_generation(prompt, urls):
    client = Mock()
    client.get_omni_reference_plan.return_value = {"urls": [{"url": url} for url in urls]}
    client.get_storyboard.return_value = {"universal_segment_text": prompt}
    with pytest.raises(chain.LmdChainError):
        chain._prepare_locked_shots(client, [{"storyboard_id": 1}])
    client.generate_universal_segment.assert_not_called()
    client.generate_video.assert_not_called()


def test_valid_prompt_is_preserved():
    client = Mock()
    client.get_omni_reference_plan.return_value = {"urls": [{"url": "reference.png"}]}
    client.get_storyboard.return_value = {"universal_segment_text": "@圖片1 walks into the room"}
    prepared = chain._prepare_locked_shots(client, [{"storyboard_id": 1}])
    assert prepared[1] == {"prompt": "@圖片1 walks into the room", "reference_image_urls": ["reference.png"]}


def test_invalid_later_shot_blocks_all_generation(tmp_path):
    client = Mock()
    client.list_storyboards.return_value = {"drama_id": 1, "storyboards": [
        {"id": 1, "storyboard_number": 1, "duration": 5},
        {"id": 2, "storyboard_number": 2, "duration": 5},
    ]}
    client.get_drama.return_value = {"characters": []}
    client.preflight_reference_assets.return_value = {"can_proceed": True, "checked_storyboards": 2}
    client.get_omni_reference_plan.return_value = {"urls": [{"url": "reference.png"}]}
    client.get_storyboard.side_effect = lambda sid: {"universal_segment_text": "@图片1 walks" if sid == 1 else ""}
    with pytest.raises(chain.LmdChainError):
        chain.run_episode_lmd(client, episode_id=1, out_root=tmp_path, generate_universal=True)
    client.generate_universal_segment.assert_not_called()
    client.generate_video.assert_not_called()
    client.update_storyboard.assert_not_called()