"""Diversity engine: build n structurally-distinct variant plans for a topic.

A plan = (hook, twist, emotion arc, ending, pov). Plans inside one batch never
share a hook or twist, and (arc, ending) pairs are unique - this is the core
anti-homogeneity mechanism for P3 experiments.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from .hooks import get_hook, pick_hooks
from .twists import get_twist, pick_twists

EMOTION_ARCS: tuple[str, ...] = (
    "遞進升華",   # steadily rising
    "懸崖回落",   # build then sudden drop
    "迴圈重複",   # repeating cycle
    "雙線交錯",   # intercut two threads
    "倒敘拼圖",   # reverse-order puzzle
)

ENDINGS: tuple[str, ...] = (
    "釋然收束",
    "餘韻遺憾",
    "開放懸念",
    "反轉落地",
    "循環回歸",
)

POVS: tuple[str, ...] = ("主角視角", "物件視角", "旁觀者視角")


@dataclass(frozen=True)
class StructurePlan:
    variant: int
    hook_id: str
    twist_id: str
    arc: str
    ending: str
    pov: str

    def signature(self) -> str:
        return f"{self.hook_id}+{self.twist_id}+{self.arc}+{self.ending}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["hook_name"] = get_hook(self.hook_id).name
        d["twist_name"] = get_twist(self.twist_id).name
        d["twist_requirement"] = get_twist(self.twist_id).requirement
        return d


def make_variant_plans(
    topic: str,
    n: int = 5,
    seed: int | None = None,
    exclude_signatures: tuple[str, ...] = (),
) -> list[StructurePlan]:
    """Return n distinct plans; raise when the space cannot satisfy uniqueness."""
    if n > len(EMOTION_ARCS) * len(ENDINGS):
        raise ValueError("n too large: arc x ending space exhausted")

    rng = random.Random(seed if seed is not None else hash(topic) & 0xFFFF)
    hooks = pick_hooks(n, seed=rng.randint(0, 10**9))
    twists = pick_twists(n, seed=rng.randint(0, 10**9))

    pairs = [(a, e) for a in EMOTION_ARCS for e in ENDINGS]
    rng.shuffle(pairs)
    used_sig = set(exclude_signatures)
    plans: list[StructurePlan] = []
    for i in range(n):
        arc, ending = pairs[i]
        pov = POVS[i % len(POVS)]
        plan = StructurePlan(i + 1, hooks[i].id, twists[i].id, arc, ending, pov)
        if plan.signature() in used_sig:
            raise ValueError(f"signature collision after shuffle: {plan.signature()}")
        used_sig.add(plan.signature())
        plans.append(plan)
    return plans


def plans_to_dicts(plans: list[StructurePlan]) -> list[dict]:
    return [p.to_dict() for p in plans]
