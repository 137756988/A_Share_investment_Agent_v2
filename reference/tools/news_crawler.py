import os
import json
from datetime import datetime, timedelta
import yfinance as yf
from tools.openrouter_config import get_chat_completion, logger as api_logger
import time


def get_stock_news(symbol: str, max_news: int = 10) -> list:
    """Get and process stock news from Yahoo Finance

    Args:
        symbol (str): Stock symbol, e.g. "AAPL"
        max_news (int, optional): Maximum number of news articles to fetch. Defaults to 10.

    Returns:
        list: List of news articles, each containing title, content, publish time etc.
    """
    # Limit max news to 100
    max_news = min(max_news, 100)

    # Get current date
    today = datetime.now().strftime("%Y-%m-%d")

    # Build news file path
    news_dir = os.path.join("src", "data", "stock_news")
    print(f"News directory: {news_dir}")

    # Ensure directory exists
    try:
        os.makedirs(news_dir, exist_ok=True)
        print(
            f"Successfully created or confirmed directory exists: {news_dir}")
    except Exception as e:
        print(f"Failed to create directory: {e}")
        return []

    news_file = os.path.join(news_dir, f"{symbol}_news.json")
    print(f"News file path: {news_file}")

    # Check if we need to update news
    need_update = True
    if os.path.exists(news_file):
        try:
            with open(news_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get("date") == today:
                    cached_news = data.get("news", [])
                    if len(cached_news) >= max_news:
                        print(f"Using cached news data: {news_file}")
                        return cached_news[:max_news]
                    else:
                        print(
                            f"Cached news count({len(cached_news)}) is less than requested({max_news})")
        except Exception as e:
            print(f"Failed to read cache file: {e}")

    print(f'Starting to fetch news for {symbol}...')

    try:
        # Get stock info using yfinance
        stock = yf.Ticker(symbol)

        # Get news
        news_data = stock.news
        if not news_data:
            print(f"No news found for {symbol}")
            return []

        print(f"Successfully fetched {len(news_data)} news items")
        print("Raw news data sample:", json.dumps(
            news_data[0] if news_data else {}, indent=2))

        # Process news
        news_list = []
        for i, news in enumerate(news_data[:max_news]):
            try:
                # Get news content from the content object
                content_obj = news.get('content', {})
                if not content_obj:
                    print(f"\nSkipping news item {i+1}: No content object")
                    continue

                title = content_obj.get('title', '')
                content = content_obj.get('summary', '')
                if not content:
                    content = content_obj.get('description', '')

                print(f"\nProcessing news item {i+1}:")
                print(f"Title: {title}")
                print(f"Content length: {len(content)}")

                # Skip if content is too short
                if len(content) < 10:
                    print("Skipping: content too short")
                    continue

                # Get provider info
                provider = content_obj.get('provider', {})
                source = provider.get('displayName', '')

                # Get URL
                click_through = content_obj.get('clickThroughUrl', {})
                url = click_through.get('url', '')

                # Convert timestamp to datetime
                pub_date = content_obj.get('pubDate', '')
                if pub_date:
                    try:
                        # Parse ISO format date
                        dt = datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%SZ")
                        publish_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception as e:
                        print(f"Failed to parse date {pub_date}: {e}")
                        publish_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                else:
                    publish_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                print(f"Publish time: {publish_time}")

                # Add news item
                news_item = {
                    "title": title.strip(),
                    "content": content.strip(),
                    "publish_time": publish_time,
                    "source": source.strip(),
                    "url": url.strip(),
                }
                news_list.append(news_item)
                print(f"Successfully added news: {news_item['title']}")

            except Exception as e:
                print(f"Failed to process single news item: {e}")
                continue

        # Sort by publish time
        news_list.sort(key=lambda x: x["publish_time"], reverse=True)

        # Keep only requested number of news
        news_list = news_list[:max_news]

        # Save to file
        try:
            save_data = {
                "date": today,
                "news": news_list
            }
            with open(news_file, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            print(
                f"Successfully saved {len(news_list)} news items to file: {news_file}")
        except Exception as e:
            print(f"Failed to save news data to file: {e}")

        return news_list

    except Exception as e:
        print(f"Failed to fetch news data: {e}")
        return []


def get_news_sentiment(news_list: list, num_of_news: int = 5) -> float:
    """Analyze news sentiment using LLM

    Args:
        news_list (list): List of news articles
        num_of_news (int, optional): Number of news articles to analyze. Defaults to 5.

    Returns:
        float: Sentiment score between -1 and 1
    """
    if not news_list:
        return 0.0

    # Check cache
    cache_file = "src/data/sentiment_cache.json"
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)

    # Generate unique key for news content
    news_key = "|".join([
        f"{news['title']}|{news['content'][:100]}|{news['publish_time']}"
        for news in news_list[:num_of_news]
    ])

    # Check cache
    if os.path.exists(cache_file):
        print("Found sentiment analysis cache file")
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                if news_key in cache:
                    print("Using cached sentiment analysis result")
                    return cache[news_key]
                print("No matching sentiment analysis cache found")
        except Exception as e:
            print(f"Failed to read sentiment cache: {e}")
            cache = {}
    else:
        print("No sentiment analysis cache file found, will create new one")
        cache = {}

    # Prepare system message
    system_message = {
        "role": "system",
        "content": """You are a professional US stock market analyst specializing in news sentiment analysis. You need to analyze a set of news articles and provide a sentiment score between -1 and 1:
        - 1 represents extremely positive (e.g., major positive news, breakthrough earnings, strong industry support)
        - 0.5 to 0.9 represents positive (e.g., growth in earnings, new project launch, contract wins)
        - 0.1 to 0.4 represents slightly positive (e.g., small contract signings, normal operations)
        - 0 represents neutral (e.g., routine announcements, personnel changes, non-impactful news)
        - -0.1 to -0.4 represents slightly negative (e.g., minor litigation, non-core business losses)
        - -0.5 to -0.9 represents negative (e.g., declining performance, major customer loss, industry regulation tightening)
        - -1 represents extremely negative (e.g., major violations, core business severe losses, regulatory penalties)

        Focus on:
        1. Performance related: financial reports, earnings forecasts, revenue/profit
        2. Policy impact: industry policies, regulatory policies, local policies
        3. Market performance: market share, competitive position, business model
        4. Capital operations: M&A, equity incentives, additional issuance
        5. Risk events: litigation, arbitration, penalties
        6. Industry position: technological innovation, patents, market share
        7. Public opinion: media evaluation, social impact

        Please ensure to analyze:
        1. News authenticity and reliability
        2. News timeliness and impact scope
        3. Actual impact on company fundamentals
        4. US stock market's specific reaction patterns"""
    }

    # Prepare news content
    news_content = "\n\n".join([
        f"Title: {news['title']}\n"
        f"Source: {news['source']}\n"
        f"Time: {news['publish_time']}\n"
        f"Content: {news['content']}"
        for news in news_list[:num_of_news]
    ])

    user_message = {
        "role": "user",
        "content": f"Please analyze the sentiment of the following US stock related news:\n\n{news_content}\n\nPlease return only a number between -1 and 1, no explanation needed."
    }

    try:
        # Get LLM analysis result
        result = get_chat_completion([system_message, user_message])
        if result is None:
            print("Error: LLM returned None")
            return 0.0

        # Extract numeric result
        try:
            sentiment_score = float(result.strip())
        except ValueError as e:
            print(f"Error parsing sentiment score: {e}")
            print(f"Raw result: {result}")
            return 0.0

        # Ensure score is between -1 and 1
        sentiment_score = max(-1.0, min(1.0, sentiment_score))

        # Cache result
        cache[news_key] = sentiment_score
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error writing cache: {e}")

        return sentiment_score

    except Exception as e:
        print(f"Error analyzing news sentiment: {e}")
        return 0.0  # Return neutral score on error
