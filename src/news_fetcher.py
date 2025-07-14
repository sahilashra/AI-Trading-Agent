from gnews import GNews
from logger import log

def get_financial_news(query: str = None, max_results: int = 5) -> list:
    """
    Fetches top financial news headlines for India using the gnews library.
    """
    try:
        google_news = GNews(language='en', country='IN', period='1d')
        google_news.max_results = max_results
        
        if query:
            news = google_news.get_news(f"{query} India")
        else:
            news = google_news.get_news('Business OR Finance OR Stock Market India')
        
        if not news:
            log.info(f"No news articles found for query: '{query}'")
            return []

        # gnews returns a list of dicts, so we extract the 'title'
        headlines = [article.get('title', 'No Title') for article in news]
        return headlines
        
    except Exception as e:
        # gnews can sometimes fail with network errors
        log.error(f"An error occurred while fetching financial news with gnews: {e}")
        return []

if __name__ == '__main__':
    log.info("Fetching latest financial news headlines...")
    headlines = get_financial_news("Reliance Industries")
    if headlines:
        for i, headline in enumerate(headlines, 1):
            log.info(f"{i}. {headline}")
    else:
        log.warning("Could not fetch news.")