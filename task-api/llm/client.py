"""Everything that makes an LLM call survivable in production.

A model is a slow, clever, sometimes wrong external API. Four properties, four
answers in this file:

  slow                  -> an explicit timeout (the SDK default is TEN MINUTES)
  non-deterministic     -> temperature 0, and the caller validates the shape
  costs money and quota -> a cost log, a kill switch, and a stub mode
  confidently wrong     -> one repair attempt, then give up cleanly
"""
import json
import os
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT_VERSION = "triage-v1"
PROMPT_PATH = ROOT / "prompts" / f"{PROMPT_VERSION}.md"
LOG_DIR = ROOT / "logs"

TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "30"))   # seconds, never the default
MAX_RETRIES = 2
RETRYABLE = {408, 409, 429, 500, 502, 503, 504}        # a bad moment
NEVER_RETRY = {400, 401, 403, 404, 422}                # a bad request


class LLMError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class LLMTimeout(LLMError):
    def __init__(self, message):
        super().__init__(message, status=504)


def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def enabled() -> bool:
    """The kill switch. One env var stops every call without a deploy."""
    return os.environ.get("LLM_ENABLED", "true").lower() not in {"false", "0", "no"}


def using_stub() -> bool:
    return os.environ.get("LLM_STUB") == "1"


def log_call(**fields):
    """One structured line per call. Without this you cannot answer 'why is the
    bill like that' or 'which prompt version produced yesterday's numbers'."""
    LOG_DIR.mkdir(exist_ok=True)
    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **fields}
    with (LOG_DIR / "llm-calls.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")
    return line


def quarantine(**fields):
    """Output that failed validation twice, kept so it can be read later."""
    LOG_DIR.mkdir(exist_ok=True)
    with (LOG_DIR / "quarantine.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "prompt_version": PROMPT_VERSION, **fields}) + "\n")


def _status_of(exc) -> int | None:
    return getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None)


def retry_after_seconds(exc) -> float | None:
    """The server's own 'wait this long' instruction, if it sent one.

    Retry-After comes in two shapes: a number of seconds ("20") or an HTTP date
    ("Wed, 21 Oct 2026 07:28:00 GMT"). Handling only the number is a real bug.
    The headers are an httpx.Headers object, not a dict, so ask with .get().
    """
    headers = getattr(getattr(exc, "response", None), "headers", None)
    value = headers.get("retry-after") if headers is not None else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def complete(messages: list[dict]) -> tuple[str, dict]:
    """Send messages, return (reply text, usage). Retries only what is worth retrying."""
    import openai

    client = openai.OpenAI(
        base_url=os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.environ.get("LLM_API_KEY", ""),
        timeout=TIMEOUT,
        max_retries=0,  # the SDK retries twice by default; this file decides instead
    )
    model = os.environ.get("LLM_MODEL", "openrouter/free")
    # Reasoning models (qwen3.5 on Ollama) think before answering. For a four-field
    # label that costs ~7s and ~100 tokens per call for no better answer, so
    # LLM_REASONING_EFFORT=none switches it off. Unset = send nothing, because not
    # every provider accepts the field.
    effort = os.environ.get("LLM_REASONING_EFFORT")
    extra = {"reasoning_effort": effort} if effort else None

    for attempt in range(MAX_RETRIES + 1):
        try:
            res = client.chat.completions.create(
                model=model, messages=messages, temperature=0, timeout=TIMEOUT,
                extra_body=extra)
            usage = getattr(res, "usage", None)
            return res.choices[0].message.content or "", {
                "model": model,
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
            }
        except Exception as exc:
            status = _status_of(exc)
            is_timeout = "timeout" in type(exc).__name__.lower()
            if is_timeout and attempt == MAX_RETRIES:
                raise LLMTimeout(f"Model did not answer within {TIMEOUT:.0f}s") from exc
            # A 401 will be a 401 on the third try too, and on OpenRouter's free
            # tier every failed call still costs one of the day's 50.
            if status in NEVER_RETRY:
                raise LLMError(f"Provider refused the request (HTTP {status})", 502) from exc
            if not is_timeout and status not in RETRYABLE:
                raise LLMError(f"Model call failed: {type(exc).__name__}", 502) from exc
            if attempt == MAX_RETRIES:
                raise LLMError(f"Model call failed after {attempt + 1} attempts", 502) from exc
            # Exponential backoff with jitter: 1s, 2s, plus a random fraction so a
            # hundred clients that failed together don't all come back together.
            wait = (2 ** attempt) + random.random()
            told = retry_after_seconds(exc)
            if told is not None:
                wait = told  # the server knows its own limits better than our guess
            time.sleep(wait)
    raise LLMError("unreachable")
