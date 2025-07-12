import os
import telegram
from dotenv import load_dotenv
from logger import log

# --- Robust Path Setup ---
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path=dotenv_path)
# -------------------------

# --- Telegram Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

async def send_telegram_alert(message: str):
    """
    Sends a message to the configured Telegram chat.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials not found. Skipping alert.")
        return

    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        log.info("Successfully sent Telegram alert.")
    except Exception as e:
        log.error(f"Failed to send Telegram alert: {e}")

if __name__ == '__main__':
    # Example usage:
    import asyncio
    log.info("Sending a test alert to Telegram...")
    asyncio.run(send_telegram_alert("This is a test alert from the AI Trading Agent."))
