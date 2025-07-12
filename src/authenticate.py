import os
import sys
import asyncio
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# --- Robust Path Setup ---
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)
dotenv_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path=dotenv_path)
# -------------------------

api_key = os.getenv("KITE_API_KEY")
api_secret = os.getenv("KITE_API_SECRET")

async def generate_access_token_async():
    """Asynchronously generates and saves the access token."""
    if not api_key or not api_secret or "YOUR_API_KEY" in api_key:
        print("Error: KITE_API_KEY and KITE_API_SECRET must be set in the .env file.")
        return

    kite = KiteConnect(api_key=api_key)
    print(f"\nStep 1: Go to this URL and log in:\n{kite.login_url()}\n")
    
    loop = asyncio.get_event_loop()
    request_token = await loop.run_in_executor(
        None, 
        lambda: input("Step 2: Paste the request_token from the redirect URL here: ").strip()
    )

    try:
        data = await loop.run_in_executor(
            None,
            lambda: kite.generate_session(request_token, api_secret=api_secret)
        )
        access_token = data["access_token"]

        with open(dotenv_path, "r") as f:
            lines = f.readlines()

        token_updated = False
        with open(dotenv_path, "w") as f:
            for line in lines:
                if line.strip().startswith("ACCESS_TOKEN="):
                    f.write(f'ACCESS_TOKEN="{access_token}"\n')
                    token_updated = True
                else:
                    f.write(line)
            if not token_updated:
                if lines and not lines[-1].endswith('\n'):
                    f.write('\n')
                f.write(f'ACCESS_TOKEN="{access_token}"\n')

        print("\nSuccess! Access token has been updated in your .env file.")
        print("You can now run the main application.")

    except Exception as e:
        print(f"\nAuthentication failed: {e}")

if __name__ == "__main__":
    asyncio.run(generate_access_token_async())
