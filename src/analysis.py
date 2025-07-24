from llm_clients import get_llm_client, LLMClient, FAIL_SAFE_DECISION
from validators import AIDecision
from logger import log

# --- Global instance of the LLM Client ---
llm_client: LLMClient = None

def initialize_llm_client():
    """
    Initializes the LLM client based on the configuration.
    This function must be called once at startup.
    """
    global llm_client
    try:
        llm_client = get_llm_client()
    except ValueError as e:
        log.critical(e)
        raise

async def get_market_analysis(prompt: str) -> AIDecision:
    """
    Sends a prompt to the configured LLM API asynchronously.
    """
    global llm_client
    if not llm_client:
        log.error("LLM Client is not initialized. Returning failsafe HOLD decision.")
        return FAIL_SAFE_DECISION

    return await llm_client.get_market_analysis(prompt)
