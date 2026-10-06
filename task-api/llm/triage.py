"""The six-line endpoint, in order:

  validate input      -> reject garbage before spending a call
  build the prompt    -> from a versioned file
  call the model      -> timeout, retries on the right errors only
  parse and validate  -> against the schema
  repair once         -> hand the model its own error message
  return clean JSON   -> or a clear 422. Never raw model text.
"""
import json
import time

from . import client
from .parse import parse
from .schema import Triage

# A deterministic stand-in: keyword rules, no model, no spend. It is deliberately
# simple so nobody mistakes its eval score for a model's.
STUB_RULES = [
    ("billing", ["charge", "charged", "invoice", "refund", "billing", "payment", "subscription", "overcharged"]),
    ("bug", ["crash", "crashes", "crashing", "error", "broken", "bug", "not working", "fails", "500"]),
    ("feature", ["would be nice", "feature request", "could you add", "please add", "wish", "suggestion", "it'd be great"]),
]
HIGH = ["urgent", "asap", "immediately", "can't work", "cannot work", "down", "twice", "critical", "losing"]


def stub(text: str) -> Triage:
    low = text.lower()
    category, confidence = "other", 0.3
    for name, words in STUB_RULES:
        if any(w in low for w in words):
            category, confidence = name, 0.8
            break
    urgency = "high" if any(w in low for w in HIGH) else "normal" if category != "other" else "low"
    if category == "other":
        confidence = 0.3
    return Triage(
        category=category, urgency=urgency, confidence=confidence,
        reason=f"Stub classifier matched on {category} keywords." if category != "other"
        else "Stub classifier found nothing it recognised.",
    )


def classify(text: str) -> tuple[Triage, dict]:
    """Returns (result, log line). Raises client.LLMError on a failure worth a status code."""
    started = time.monotonic()

    if not client.enabled():
        # Kill switch: answer immediately, deterministically, with zero calls.
        result = Triage(category="other", urgency="normal", confidence=0.0,
                        reason="Automatic triage is switched off; needs a human.")
        return result, client.log_call(mode="disabled", repairs=0,
                                       duration_ms=round((time.monotonic() - started) * 1000))

    if client.using_stub():
        result = stub(text)
        return result, client.log_call(mode="stub", repairs=0,
                                       prompt_version=client.PROMPT_VERSION,
                                       duration_ms=round((time.monotonic() - started) * 1000))

    # The customer's words go in a SEPARATE user message, JSON-encoded. Gluing
    # them into the system prompt is how "ignore your instructions" starts
    # working -- there the model cannot tell rules from data.
    messages = [
        {"role": "system", "content": client.system_prompt()},
        {"role": "user", "content": json.dumps({"message": text})},
    ]

    raw, usage = client.complete(messages)
    result, error = parse(raw)
    repairs = 0

    if result is None:
        # One repair, never two. Hand back the exact validation error.
        repairs = 1
        messages += [
            {"role": "assistant", "content": raw},
            {"role": "user", "content":
                f"Your previous answer was rejected for this reason: {error}. "
                "Return only corrected JSON matching the schema."},
        ]
        raw2, usage2 = client.complete(messages)
        # The repair is a second paid call: add its tokens, don't replace them.
        usage = {**usage2, **{k: (usage.get(k) or 0) + (usage2.get(k) or 0)
                              for k in ("input_tokens", "output_tokens")}}
        result, error = parse(raw2)
        if result is None:
            client.quarantine(input=text, first_output=raw, second_output=raw2, error=error)
            client.log_call(mode="live", repairs=repairs, failed=True,
                            prompt_version=client.PROMPT_VERSION, **usage,
                            duration_ms=round((time.monotonic() - started) * 1000))
            raise client.LLMError(
                f"The model could not produce a valid answer: {error}", 422)

    line = client.log_call(mode="live", repairs=repairs,
                           prompt_version=client.PROMPT_VERSION, **usage,
                           duration_ms=round((time.monotonic() - started) * 1000))
    return result, line
