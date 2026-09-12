"""Story Room v2 - story-first drafting layer for music-driven MV episodes.

Pipeline position:
    topic bank -> logline -> beat sheet -> shot mapping -> critic review

Hard rules:
- This package NEVER calls any video-generation API (Seedance or otherwise).
  It only produces text/JSON drafts for CEO review.
- Output drafts are scaffolds: every unknown field is marked "TODO(CEO)" so the
  pipeline can never silently proceed with missing decisions.
"""
from . import agents, critic_dims, llm_text
from .agents import critique, run_adversarial, score
from .topics import TOPICS, TOP10_NAMES, Topic, get_topic, top10
from .beats import Act, Beat, BeatSheet, build_scaffold, sheet_from_dict
from .map_shots import build_draft, map_to_shots, split_durations
from .critic import format_report, review
from .diversity import ENDINGS, EMOTION_ARCS, StructurePlan, make_variant_plans, plans_to_dicts
from .hooks import HOOKS, Hook, all_hooks, get_hook, pick_hooks
from .twists import TWISTS, Twist, all_twists, get_twist, pick_twists

__all__ = [
    "TOPICS",
    "TOP10_NAMES",
    "Topic",
    "get_topic",
    "top10",
    "Act",
    "Beat",
    "BeatSheet",
    "build_scaffold",
    "sheet_from_dict",
    "build_draft",
    "map_to_shots",
    "split_durations",
    "review",
    "format_report",
    "HOOKS",
    "Hook",
    "all_hooks",
    "get_hook",
    "pick_hooks",
    "TWISTS",
    "Twist",
    "all_twists",
    "get_twist",
    "pick_twists",
    "StructurePlan",
    "make_variant_plans",
    "plans_to_dicts",
    "EMOTION_ARCS",
    "ENDINGS",
    "run_adversarial",
    "critique",
    "score",
]
