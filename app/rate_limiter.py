import os
import json
import time
from typing import AsyncGenerator
from google.adk.models import Gemini, LlmRequest, LlmResponse

STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rate_limit_state.json")
MAX_RPM = 15
MAX_RPD = 200

class RateLimitExceededError(Exception):
    pass

class RateLimitedGemini(Gemini):
    
    def _load_state(self):
        if not os.path.exists(STATE_FILE):
            return {"timestamps": []}
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"timestamps": []}
            
    def _save_state(self, state):
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
            
    async def _wait_and_update_limits(self):
        import asyncio
        while True:
            state = self._load_state()
            now = time.time()
            
            # Filter timestamps to keep only the last 24 hours
            one_day_ago = now - (24 * 60 * 60)
            timestamps = [ts for ts in state.get("timestamps", []) if ts > one_day_ago]
            
            # Check daily limit
            if len(timestamps) >= MAX_RPD:
                raise RateLimitExceededError(f"Daily rate limit of {MAX_RPD} requests exceeded. Please try again tomorrow.")
                
            # Check minute limit
            one_minute_ago = now - 60
            last_minute_timestamps = [ts for ts in timestamps if ts > one_minute_ago]
            if len(last_minute_timestamps) >= MAX_RPM:
                delay = 60 - (now - last_minute_timestamps[0]) + 0.5
                print(f"[auto-contrib] Minute rate limit of {MAX_RPM} requests hit. Sleeping for {delay:.2f} seconds to respect API limits...")
                await asyncio.sleep(delay)
                continue # Re-check limits after sleeping
                
            # Record new timestamp
            timestamps.append(now)
            state["timestamps"] = timestamps
            self._save_state(state)
            break

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        
        try:
            await self._wait_and_update_limits()
        except RateLimitExceededError as e:
            raise Exception(f"Gemini daily quota exhausted: {e}. Please try again tomorrow.")

        try:
            async for response in super().generate_content_async(llm_request, stream):
                yield response
        except Exception as e:
            err_str = str(e)
            # 429 from Gemini API means quota exhausted. Groq cannot use MCP tools and
            # will hallucinate the entire workflow — fail fast with a clear message instead.
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                import re
                retry_match = re.search(r"retry.*?(\d+)[\.\d]*s", err_str, re.IGNORECASE)
                retry_hint = f" Gemini suggests retrying in {retry_match.group(1)}s." if retry_match else ""
                raise Exception(
                    f"Gemini quota exceeded (429 RESOURCE_EXHAUSTED).{retry_hint} "
                    "Please wait and try again, or upgrade to a paid Gemini API key."
                )
            raise
