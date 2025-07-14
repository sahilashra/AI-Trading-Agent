import os
import json
import google.generativeai as genai
from logger import log
from validators import AIDecision, DataValidationError

# --- Model variable, to be initialized later ---
model = None
# --- Default fail-safe decision ---
FAIL_SAFE_DECISION = AIDecision(decision="HOLD", confidence=1, reasoning="Failsafe triggered due to an internal error.")

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
        # Configure the model to output JSON
        generation_config = genai.GenerationConfig(response_mime_type="application/json")
        model = genai.GenerativeModel(
            'gemini-1.5-flash',
            generation_config=generation_config
        )
        log.info("Gemini model initialized successfully for JSON output.")
    except Exception as e:
        log.critical(f"Failed to configure Gemini API: {e}")
        raise

def get_market_analysis(prompt: str) -> AIDecision:
    """
    Sends a prompt to the Gemini API and returns a validated AIDecision object.
    """
    global model
    if not model:
        log.error("Gemini model is not initialized. Returning failsafe HOLD decision.")
        return FAIL_SAFE_DECISION

    try:
        response = model.generate_content(prompt)
        # Clean the response to ensure it's valid JSON
        cleaned_json_str = response.text.strip().replace("```json", "").replace("```", "")
        
        # Parse the JSON string into a Python dictionary
        decision_dict = json.loads(cleaned_json_str)
        
        # Validate the dictionary using the Pydantic model
        validated_decision = AIDecision.parse_obj(decision_dict)
        return validated_decision

    except json.JSONDecodeError as e:
        log.error(f"Failed to decode JSON from LLM response: {e}\nRaw response: '{response.text}'")
        return FAIL_SAFE_DECISION
    except DataValidationError as e: # Catching our custom validation error
        log.error(f"AI decision validation failed: {e}\nRaw response: '{response.text}'")
        return FAIL_SAFE_DECISION
    except Exception as e:
        log.error(f"An error occurred while contacting the Gemini API: {e}")
        return FAIL_SAFE_DECISION

if __name__ == '__main__':
    # Example usage:
    try:
        from dotenv import load_dotenv
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dotenv_path = os.path.join(project_root, '.env')
        load_dotenv(dotenv_path=dotenv_path)
        
        initialize_gemini(os.getenv("GEMINI_API_KEY"))

        example_prompt = """
        Analyze the stock based on the provided data and strategy.
        Respond in JSON format with three keys: "decision" (BUY, SELL, or HOLD),
        "confidence" (an integer from 1 to 10), and "reasoning" (a brief explanation).

        Data:
        - Symbol: RELIANCE
        - Strategy: Momentum Pullback (Buy on RSI < 55 in a long-term uptrend)
        - Current Price: 2850.00
        - 50-Day SMA: 2800.00 (Price is above SMA - uptrend confirmed)
        - RSI(14): 52.0 (RSI is below 55 - pullback confirmed)
        """
        print(f"Asking Gemini with structured prompt...")
        analysis_decision = get_market_analysis(example_prompt)
        print("\n--- Gemini's Analysis ---")
        print(f"Decision: {analysis_decision.decision}")
        print(f"Confidence: {analysis_decision.confidence}")
        print(f"Reasoning: {analysis_decision.reasoning}")
        print("--------------------------")
    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")