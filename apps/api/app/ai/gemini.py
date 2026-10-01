"""
Shared Gemini client for Pairza's AI-assisted mystery pipeline (generation and semantic
validation — scripts/generate_mysteries.py and scripts/validate_mystery.py). One thin
wrapper around the official `google-genai` SDK, so both scripts call the same function
instead of each owning their own API plumbing — the role `validate_mystery.py`'s old
`_call_anthropic` played before this migration.

Uses `client.aio.models.generate_content`, the SDK's real async method (not a sync call
wrapped in a thread), so this offline batch job never blocks anything sharing its event
loop — see https://googleapis.github.io/python-genai/ ("client.aio exposes all the
analogous async methods that are available on client").

No retry/backoff is implemented here on purpose: the existing pipeline already retries at
the batch level (`generate_for_category` tries up to `MAX_ATTEMPTS_PER_MYSTERY` times per
mystery, each attempt a fresh call), and duplicating that as a second, inner retry loop
would be new behavior this migration isn't meant to introduce. A single Gemini failure
here surfaces as one exception, exactly like a single Anthropic failure used to.
"""
from google import genai
from google.genai import errors as genai_errors
from google.genai import types


class GeminiConfigError(RuntimeError):
    """No API key configured — distinct from a call that reached Gemini and then failed."""


class GeminiCallError(RuntimeError):
    """Gemini was reachable but the call itself failed: a rate limit, a server error, an
    empty response, or anything else. Built only from the model name and Gemini's own
    status/message — never from the request itself, so the API key can't end up in a log
    line or a rejection reason shown in the admin panel."""


async def call_gemini(prompt: str, api_key: str, model: str) -> str:
    """
    Sends `prompt` to `model` with JSON output mode and returns the raw response text.
    Callers own interpreting that text (generation's JSON parsing, semantic validation's
    confidence/reason parsing) — this function only owns talking to Gemini.

    Every existing caller already wraps this in a broad `except Exception` (see
    `generate_one_candidate` and `validate_semantics`), so one bad call here still can't
    take down a whole generation batch — that safety net is unchanged by this migration.
    """
    if not api_key:
        raise GeminiConfigError("No GEMINI_API_KEY configured — cannot call Gemini.")

    client = genai.Client(api_key=api_key)
    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
    except genai_errors.APIError as exc:
        # exc.code and exc.status come from Gemini's own response, never from what we sent — safe to surface.
        status = getattr(exc, "status", None)
        raise GeminiCallError(f"Gemini API error calling {model}: {exc.code}{f' {status}' if status else ''}") from exc
    except Exception as exc:
        raise GeminiCallError(f"Gemini call to {model} failed: {exc}") from exc

    if not response.text:
        raise GeminiCallError(f"Gemini ({model}) returned an empty response.")

    return response.text
