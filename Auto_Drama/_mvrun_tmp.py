# Temporary MV runner (delete after run) - relaunch of the full 175s long-take
# episode after the CEO topped up the ModelArk account.
import sys

sys.path.insert(0, r"F:\AI_DRAMA_FACTORY\Auto_Drama")
from auto_drama.cli import main  # noqa: E402

rc = main([
    "music-drama",
    "--draft",
    r"F:\AI_DRAMA_FACTORY\assets\audio\ceo_approved_beats\lofi\Drama"
    r"\RnBPower_CrownOfEchoes_draft_v2_ep01_full175s.json",
    "--execute",
    "--out-root",
    r"F:\AI_DRAMA_FACTORY\Auto_Drama\output\episodes\mv",
])
print("MUSIC_DRAMA_EXIT", rc)
sys.exit(rc)
