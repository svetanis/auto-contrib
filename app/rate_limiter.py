import asyncio
import re
import time
from typing import AsyncGenerator
from google.adk.models import Gemini, LlmRequest, LlmResponse

MAX_RPM = 15

# Candidate fallback models, tried in order when the PRIMARY model is overloaded
# ("high demand"). These are sibling flash models that draw from a different
# capacity pool than gemini-2.5-flash, so an overload on the primary doesn't
# imply an overload here. All are plain generate_content models — no interactions
# API, no auto-provisioned tools — so they stay fully inside the policy gate.
#
# NB: antigravity-preview-05-2026 was evaluated and rejected as a fallback: it is
# reachable only via the stateful Interactions API and brings ungated Search +
# sandbox tools, which would bypass auto-contrib's HITL/policy design.
#
# The list is tried at call time; whichever the active backend (Vertex or AI
# Studio) accepts is cached and reused.
FALLBACK_MODELS = ("gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-2.0-flash")

_timestamps: list[float] = []

# Signals that the primary model is transiently overloaded (not a quota error).
_OVERLOAD_SIGNALS = ("503", "UNAVAILABLE", "overloaded", "high demand", "capacity")


class RateLimitedGemini(Gemini):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cache of the fallback model name that the API actually accepted, so we
        # don't re-probe candidates on every subsequent overload.
        self._fallback_name: str | None = None

    async def _stream_fallback(
        self, llm_request: LlmRequest, stream: bool
    ) -> AsyncGenerator[LlmResponse, None]:
        """Streams from the first fallback model the API accepts.

        The model name is only validated at call time (constructing a Gemini
        object never fails), so we try each candidate for real and remember the
        one that works. If none work, the last error propagates to the caller.
        """
        candidates = [self._fallback_name] if self._fallback_name else list(FALLBACK_MODELS)
        last_err: Exception | None = None
        for name in candidates:
            yielded = False
            try:
                model = Gemini(model=name)
                # ADK sends model=llm_request.model (NOT the Gemini object's own
                # name), and the flow set that to the overloaded primary. Point
                # the request at the fallback, or we'd just re-hit the primary.
                llm_request.model = name
                async for response in model.generate_content_async(llm_request, stream):
                    yielded = True
                    yield response
                self._fallback_name = name  # remember what worked
                return
            except Exception as e:
                # Only safe to try the next candidate if nothing was emitted yet;
                # otherwise we'd duplicate a partially streamed turn.
                if yielded:
                    raise
                last_err = e
                continue
        raise Exception(
            f"Primary model overloaded and no fallback ({', '.join(FALLBACK_MODELS)}) "
            f"was reachable: {last_err}. Please wait and retry."
        )

    async def _wait_for_rpm(self):
        while True:
            now = time.time()
            one_minute_ago = now - 60
            recent = [ts for ts in _timestamps if ts > one_minute_ago]
            if len(recent) < MAX_RPM:
                _timestamps.clear()
                _timestamps.extend(recent)
                _timestamps.append(now)
                break
            delay = 60 - (now - recent[0]) + 0.5
            print(f"[auto-contrib] RPM limit ({MAX_RPM}/min) reached. Waiting {delay:.1f}s...")
            await asyncio.sleep(delay)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        await self._wait_for_rpm()
        primary_yielded = False
        try:
            async for response in super().generate_content_async(llm_request, stream):
                primary_yielded = True
                yield response
        except Exception as e:
            err_str = str(e)
            # If the primary already emitted part of this turn, restarting on the
            # fallback would duplicate it — so only recover on a clean failure.
            if primary_yielded:
                raise

            is_quota = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
            is_overload = any(sig in err_str for sig in _OVERLOAD_SIGNALS)

            # For BOTH quota (429) and overload (503), try the sibling fallback
            # models. On the AI Studio free tier each model has its OWN RPM/TPM
            # quota, so a 429 on gemini-2.5-flash does not mean flash-lite is also
            # exhausted — the fallback frequently recovers a run that would
            # otherwise die mid-trajectory.
            if is_quota or is_overload:
                reason = "quota-limited (429)" if is_quota else "overloaded"
                target = self._fallback_name or " / ".join(FALLBACK_MODELS)
                print(f"[auto-contrib] Primary model ({self.model}) {reason} — "
                      f"falling back to {target} (separate quota/capacity pool)...")
                try:
                    async for response in self._stream_fallback(llm_request, stream):
                        yield response
                    return
                except Exception:
                    # Every fallback also failed. For quota, surface the actionable
                    # message with Gemini's own retry hint; for overload, propagate
                    # the fallback's own error.
                    if is_quota:
                        retry_match = re.search(r"retry.*?(\d+)[\.\d]*s", err_str, re.IGNORECASE)
                        retry_hint = f" Gemini suggests retrying in {retry_match.group(1)}s." if retry_match else ""
                        raise Exception(
                            f"Gemini quota exceeded (429 RESOURCE_EXHAUSTED) on the primary and all "
                            f"fallback models.{retry_hint} Please wait and try again, or upgrade to a "
                            "paid Gemini API key."
                        )
                    raise
            raise
