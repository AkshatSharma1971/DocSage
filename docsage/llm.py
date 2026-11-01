"""Ollama client for Gemma. Every call uses a JSON schema and temperature 0."""
from __future__ import annotations

import json
import urllib.request

DEFAULT_MODEL = "gemma4:e2b"
DEFAULT_HOST = "http://localhost:11434"

SYSTEM = ("You are a precise documentation reviewer. Use ONLY the facts provided. "
          "Never invent facts, values or names. Reply with JSON that matches the schema.")

EXPLAIN_SCHEMA = {"type": "object",
                  "properties": {"explanation": {"type": "string"}, "suggested_fix": {"type": "string"}},
                  "required": ["explanation", "suggested_fix"]}
JUDGE_SCHEMA = {"type": "object",
                "properties": {"drifted": {"type": "boolean"}, "evidence": {"type": "string"},
                               "explanation": {"type": "string"}, "suggested_fix": {"type": "string"}},
                "required": ["drifted", "evidence", "explanation", "suggested_fix"]}


class OllamaClient:
    def __init__(self, model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST, timeout: int = 180):
        self.model, self.host, self.timeout = model, host.rstrip("/"), timeout

    def status(self) -> str:
        """'' if ready, otherwise a human-readable problem."""
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=5) as r:
                names = [m["name"] for m in json.load(r).get("models", [])]
        except Exception:
            return f"Ollama is not reachable at {self.host}. Start it with `ollama serve`."
        if not any(n == self.model or n.startswith(self.model + ":") or n.split(":")[0] == self.model for n in names):
            return f"Model `{self.model}` not found. Run `ollama pull {self.model}`."
        return ""

    def _chat(self, user: str, schema: dict):
        body = {"model": self.model, "stream": False, "format": schema,
                "options": {"temperature": 0},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
        req = urllib.request.Request(f"{self.host}/api/chat", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(json.load(r)["message"]["content"])
        except Exception:
            return None

    def explain(self, change, claim):
        return self._chat(
            f"Code change: {change.describe()} (in {change.path}:{change.line}).\n"
            f'Documentation sentence: "{claim.text}"\n'
            "This sentence is now outdated. Explain why in one or two sentences. Then rewrite the sentence "
            "so it is correct, changing as little as possible. suggested_fix is the full rewritten sentence.",
            EXPLAIN_SCHEMA)

    def judge(self, change, claim):
        return self._chat(
            f"Code change: {change.describe()} (in {change.path}:{change.line}).\n"
            f'Documentation sentence: "{claim.text}"\n'
            "Set drifted=true ONLY if the sentence makes a specific factual statement that this code change "
            "makes false. A sentence that merely mentions the symbol is NOT drift. If drifted, evidence must be "
            "an exact quote copied from the sentence, explanation says why, and suggested_fix is the corrected "
            "sentence. Otherwise return drifted=false with empty strings.",
            JUDGE_SCHEMA)
