"""Turns a ranked candidate list into an action. Pure function, no browser, no AI."""
from dataclasses import dataclass, field


@dataclass
class Policy:
    auto: float = 90.0         # at or above (and clean): update the repository automatically
    review: float = 70.0       # at or above: heal for this run, queue for human approval
    margin: float = 10.0       # best must beat the runner-up by this much
    llm_floor: float = 50.0    # candidates below this are never shown to the LLM
    llm_top_k: int = 3
    deny: tuple = ("delete", "remove", "pay", "purchase")  # never auto-heal these


@dataclass
class Decision:
    action: str                # auto | pending | llm | fail
    candidate: dict = None
    reason: str = ""
    shortlist: list = field(default_factory=list)


def decide(ranked, name, policy):
    if not ranked:
        return Decision("fail", reason="no candidate with a compatible tag/type")

    best = ranked[0]
    runner_up = ranked[1]["score"] if len(ranked) > 1 else 0.0
    gap = best["score"] - runner_up
    detail = f"score {best['score']}, runner-up {runner_up}, discriminator misses {best['misses']}"
    denied = any(word in name.lower() for word in policy.deny)

    if gap >= policy.margin and best["misses"] <= 1 and best["score"] >= policy.review:
        if best["score"] >= policy.auto and best["misses"] == 0 and not denied:
            return Decision("auto", best, detail, ranked[:1])
        why = "on the deny-list" if denied else ("discriminator mismatch" if best["misses"] else "below auto threshold")
        return Decision("pending", best, f"{detail}; needs approval ({why})", ranked[:1])

    shortlist = [c for c in ranked[: policy.llm_top_k] if c["score"] >= policy.llm_floor]
    if shortlist:
        return Decision("llm", None, f"ambiguous: {detail}", shortlist)
    return Decision("fail", None, f"best candidate too weak: {detail}", ranked[:3])
