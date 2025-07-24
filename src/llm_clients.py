import os
import json
import asyncio
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
import requests
from logger import log
from validators import AIDecision
from config import GEMINI_API_KEYS, PERPLEXITY_API_TOKEN, LLM_PROVIDER
from collections import deque

# --- Default fail-safe decision ---
FAIL_SAFE_DECISION = AIDecision(decision="HOLD", confidence=1, reasoning="Failsafe triggered due to an internal error.")

class LLMClient:
    """
    Base class for LLM clients.
    """
    async def get_market_analysis(self, prompt: str) -> AIDecision:
        raise NotImplementedError

class GeminiClient(LLMClient):
    """
    LLM client for Gemini.
    """
    def __init__(self, api_keys: list):
        if not api_keys:
            raise ValueError("No Gemini API keys provided for initialization.")
        self.keys = deque(api_keys)
        self.current_key = self.keys[0]
        self.model = None
        self._configure_model()

    def _configure_model(self):
        """Configures the Gemini model with the current key."""
        try:
            log.info(f"Configuring Gemini with a new API key.")
            genai.configure(api_key=self.current_key)
            generation_config = genai.GenerationConfig(response_mime_type="application/json")
            self.model = genai.GenerativeModel(
                'gemini-1.5-flash',
                generation_config=generation_config
            )
            log.info("Gemini model configured successfully.")
        except Exception as e:
            log.critical(f"Failed to configure Gemini API with key ending in '...{self.current_key[-4:]}': {e}")
            self.model = None

    def get_model(self):
        """Returns the currently configured model."""
        return self.model

    def rotate_key(self):
        """
        Rotates to the next key in the deque.
        Returns True if a new key is available, False otherwise.
        """
        log.warning(f"API key ending in '...{self.current_key[-4:]}' appears to be exhausted. Rotating to the next key.")
        self.keys.rotate(-1) # Move the current key to the end
        new_key = self.keys[0]
        
        if new_key == self.current_key:
            log.error("All available Gemini API keys have been exhausted.")
            return False
            
        self.current_key = new_key
        self._configure_model()
        return True

    async def get_market_analysis(self, prompt: str) -> AIDecision:
        """
        Sends a prompt to the Gemini API, handling key rotation on rate limit errors.
        """
        max_retries = len(self.keys)
        for attempt in range(max_retries):
            model = self.get_model()
            if not model:
                if not self.rotate_key():
                    log.error("No valid Gemini model available after rotation.")
                    return FAIL_SAFE_DECISION
                continue

            try:
                # Run the synchronous SDK call in a separate thread
                response = await asyncio.to_thread(model.generate_content, prompt)
                cleaned_json_str = response.text.strip().replace("```json", "").replace("```", "")
                decision_dict = json.loads(cleaned_json_str)
                return AIDecision.parse_obj(decision_dict)

            except google_exceptions.ResourceExhausted as e:
                log.warning(f"Rate limit hit on attempt {attempt + 1}/{max_retries}. Rotating key. Details: {e}")
                if not self.rotate_key():
                    log.error("All keys exhausted; cannot retry.")
                    return FAIL_SAFE_DECISION
            except Exception as e:
                log.error(f"An unexpected error occurred while contacting the Gemini API: {e}")
                return FAIL_SAFE_DECISION
        
        log.error("All API keys failed or were rate-limited. Returning failsafe decision.")
        return FAIL_SAFE_DECISION

class PerplexityClient(LLMClient):
    """
    LLM client for Perplexity.
    """
    def __init__(self, api_token: str):
        if not api_token:
            raise ValueError("No Perplexity API token provided for initialization.")
        self.api_token = api_token
        self.api_url = "https://api.perplexity.ai/chat/completions"

    async def get_market_analysis(self, prompt: str) -> AIDecision:
        """
        Sends a prompt to the Perplexity API asynchronously.
        """
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3-sonar-large-32k-chat",
            "messages": [
                {"role": "system", "content": "You are an AI trading analyst. Respond in JSON format."},
                {"role": "user", "content": prompt}
            ]
        }
        try:
            # Run the synchronous requests.post call in a separate thread
            response = await asyncio.to_thread(
                requests.post, self.api_url, headers=headers, json=payload, timeout=30
            )
            response.raise_for_status()
            decision_dict = response.json()['choices'][0]['message']['content']
            return AIDecision.parse_obj(json.loads(decision_dict))
        except requests.exceptions.RequestException as e:
            log.error(f"An error occurred while contacting the Perplexity API: {e}")
            return FAIL_SAFE_DECISION
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            log.error(f"Failed to parse response from Perplexity API: {e}")
            return FAIL_SAFE_DECISION

def get_llm_client() -> LLMClient:
    """
    Returns the appropriate LLM client based on the configuration.
    """
    if LLM_PROVIDER == "gemini":
        return GeminiClient(GEMINI_API_KEYS)
    elif LLM_PROVIDER == "perplexity":
        return PerplexityClient(PERPLEXITY_API_TOKEN)
    else:
        raise ValueError(f"Invalid LLM provider: {LLM_PROVIDER}")
