"""Deterministic similarity between a stored fingerprint and a live element. Zero AI, zero tokens."""
from difflib import SequenceMatcher

WEIGHTS = {
    "tag": 10, "text": 15, "label": 10, "placeholder": 8, "name": 6, "type": 6,
    "href": 6, "role": 5, "cls": 7, "path": 12, "context": 8, "neighbors": 7,
}  # sums to 100

# Features that say *which* element this is. A candidate that disagrees on these
# is probably a look-alike, however well the layout features match.
DISCRIMINATORS = ("text", "label", "placeholder", "name", "href", "context")

MIN_EVIDENCE = 40   # applicable weight below which a high score is not trustworthy
EVIDENCE_CAP = 69.0  # such matches can never reach the review threshold


def _features(fp):
    return {
        "tag": fp.get("tag", ""), "text": fp.get("text", ""), "label": fp.get("label", ""),
        "placeholder": fp.get("placeholder", ""), "name": fp.get("name", ""),
        "type": fp.get("type", ""), "href": fp.get("href", ""), "role": fp.get("role", ""),
        "cls": fp.get("cls", ""), "path": tuple(fp.get("path", ())),
        "context": fp.get("ctx", ""),
        "neighbors": (fp.get("prev", ""), fp.get("next", "")),
    }


def _present(value):
    return any(value) if isinstance(value, tuple) else bool(value)


def _fuzzy(a, b):
    # squared so near-misses ("Profile" vs "Billing") are punished more than typos
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() ** 2


def _similarity(feature, old, new):
    if feature == "cls":
        a, b = set(old.split()), set(new.split())
        return len(a & b) / len(a | b)
    if feature == "path":
        return SequenceMatcher(None, old, new).ratio()
    if feature == "neighbors":
        pairs = [(a, b) for a, b in zip(old, new) if a]
        return sum(_fuzzy(a, b) for a, b in pairs) / len(pairs)
    if feature in ("text", "label", "context"):
        return _fuzzy(old, new)
    return 1.0 if old == new else 0.0


def score(old_fp, candidate):
    """Score one candidate against a stored fingerprint, or None if it cannot be the same element."""
    old, new = _features(old_fp), _features(candidate)
    if old["tag"] != new["tag"]:
        return None
    if old["type"] and old["type"] != new["type"]:
        return None

    earned = applicable = 0.0
    features, misses = {}, 0
    for feature, weight in WEIGHTS.items():
        if not _present(old[feature]):
            continue
        sim = _similarity(feature, old[feature], new[feature])
        features[feature] = round(sim, 2)
        applicable += weight
        earned += weight * sim
        if feature in DISCRIMINATORS and sim < 0.5:
            misses += 1

    confidence = 100.0 * earned / applicable
    if applicable < MIN_EVIDENCE:
        confidence = min(confidence, EVIDENCE_CAP)
    return {"score": round(confidence, 1), "misses": misses, "features": features}


def rank(old_fp, candidates):
    """Candidates that could match, best first. Each result carries the candidate dict under 'fp'."""
    ranked = []
    for candidate in candidates:
        result = score(old_fp, candidate)
        if result:
            ranked.append({"id": candidate["id"], **result, "fp": candidate})
    ranked.sort(key=lambda r: -r["score"])
    return ranked
