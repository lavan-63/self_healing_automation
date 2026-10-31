"""Optional tie-breaker. Called only when scoring is ambiguous, with at most 3 tiny candidates.

Runs against a local Ollama server, so it is free and nothing leaves the machine.
"""
import json
import urllib.error
import urllib.request

_KEEP = ("tag", "type", "text", "label", "placeholder", "name", "href", "ctx", "prev", "next")

SYSTEM = (
    "You match a UI element whose id attribute was renamed to its new id. "
    "Only the id changed, so every other attribute should still agree. "
    "Reply with JSON only."
)


def brief(fp):
    """Non-empty identifying fields, truncated. This is what keeps the prompt small."""
    return {k: fp[k][:40] for k in _KEEP if fp.get(k)}


def parse_choice(text, valid_ids):
    """Accept only a JSON reply naming one of the offered ids; anything else means 'no answer'."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    choice = data.get("choice") if isinstance(data, dict) else None
    if choice not in valid_ids:
        return None
    return {"choice": choice, "reason": str(data.get("reason", ""))[:120]}


class OllamaTiebreaker:
    def __init__(self, model="qwen2.5:1.5b", host="http://localhost:11434", timeout=60):
        self.model, self.host, self.timeout = model, host.rstrip("/"), timeout
        self.stats = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        self.last_error = None

    @property
    def tokens(self):
        return self.stats["prompt_tokens"] + self.stats["completion_tokens"]

    def choose(self, target_fp, candidates):
        user = json.dumps({
            "target": brief(target_fp),
            "candidates": [{"id": c["id"], **brief(c["fp"])} for c in candidates],
            "reply": {"choice": "<candidate id or null>", "reason": "<max 15 words>"},
        }, separators=(",", ":"))
        body = {
            "model": self.model, "stream": False, "format": "json", "keep_alive": "5m",
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            "options": {"temperature": 0, "num_predict": 80, "num_ctx": 1024},
        }
        request = urllib.request.Request(
            f"{self.host}/api/chat", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                reply = json.loads(response.read())
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self.last_error = str(exc)
            return None
        self.stats["calls"] += 1
        self.stats["prompt_tokens"] += reply.get("prompt_eval_count", 0)
        self.stats["completion_tokens"] += reply.get("eval_count", 0)
        return parse_choice(reply.get("message", {}).get("content", ""), {c["id"] for c in candidates})
