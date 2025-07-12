import os
import google.generativeai as genai
from logger import log

# --- Model variable, to be initialized later ---
model = None

def initialize_gemini(api_key: str):
    """
    Initializes the Gemini model with the provided API key.
    This function must be called once at startup.
    """
    global model
    if not api_key or "YOUR_API_KEY" in api_key:
        raise ValueError("A valid Gemini API key was not provided for initialization.")
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        log.info("Gemini model initialized successfully.")
    except Exception as e:
        log.critical(f"Failed to configure Gemini API: {e}")
        raise

def get_market_analysis(prompt: str) -> str:
    """
    Sends a prompt to the Gemini API and returns the response.
    """
    global model
    if not model:
        log.error("Gemini model is not initialized. Returning HOLD.")
        return "HOLD"

    try:
        response = model.generate_content(prompt)
        # Basic validation to ensure we get one of the expected words
        decision = response.text.strip().upper()
        if decision in ["BUY", "SELL", "HOLD"]:
            return decision
        else:
            log.warning(f"LLM returned an unexpected decision: '{decision}'. Defaulting to HOLD.")
            return "HOLD"
    except Exception as e:
        log.error(f"An error occurred while contacting the Gemini API: {e}")
        # Fail-safe: If the API fails, we default to a neutral stance.
        return "HOLD"

if __name__ == '__main__':
    # Example usage:
    # This part will now require manual key input for direct execution
    try:
        from dotenv import load_dotenv
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dotenv_path = os.path.join(project_root, '.env')
        load_dotenv(dotenv_path=dotenv_path)
        
        initialize_gemini(os.getenv("GEMINI_API_KEY"))

        example_prompt = "Based on high volume and a recent breakout, should I BUY, SELL, or HOLD RELIANCE?"
        print(f"Asking Gemini: {example_prompt}")
        analysis = get_market_analysis(example_prompt)
        print("\n--- Gemini's Analysis ---")
        print(analysis)
        print("--------------------------")
    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")