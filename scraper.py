import feedparser
import trafilatura
import requests
from datetime import datetime, timezone, timedelta
from database import save_article
from googlenewsdecoder import new_decoderv1

SOURCES = [
    {
        "name": "Google News — Indianapolis Real Estate",
        "url": "https://news.google.com/rss/search?q=Indianapolis+real+estate&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Google News — Indianapolis Economy & Jobs",
        "url": "https://news.google.com/rss/search?q=Indianapolis+economy+jobs+business+hiring&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Google News — Indiana Housing & Mortgage",
        "url": "https://news.google.com/rss/search?q=Indiana+housing+mortgage+rent+rental&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Google News — Indianapolis Development",
        "url": "https://news.google.com/rss/search?q=Indianapolis+development+construction+expansion&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Google News — Indianapolis Fix Flip Wholesale",
        "url": "https://news.google.com/rss/search?q=Indianapolis+flip+wholesale+investment+property&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Federal Reserve",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
    },
    {
        "name": "Google News — Interest Rates Housing",
        "url": "https://news.google.com/rss/search?q=mortgage+rates+interest+rates+housing+market+2026&hl=en-US&gl=US&ceid=US:en",
    },
]

# ── אתרים עם Paywall — לא נשמור כתבות מהם ────────────────────────
PAYWALL_DOMAINS = {
    "indystar.com",        # USA Today paywall
    "law360.com",          # full paywall
    "bizjournals.com",     # paywall
    "ibj.com",             # Indianapolis Business Journal paywall
    "fortune.com",         # paywall
    "wsj.com",             # Wall Street Journal
    "nytimes.com",         # New York Times
    "washingtonpost.com",  # Washington Post
    "bloomberg.com",       # Bloomberg
    "ft.com",              # Financial Times
    "theatlantic.com",     # The Atlantic
    "thetimes.co.uk",      # The Times
    "economist.com",       # The Economist
    "theindianalawyer.com",# paywall
    "natlawreview.com",    # paywall
    "housingwire.com",     # partial paywall
}

def is_paywalled(url: str) -> bool:
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace("www.", "")
    return any(domain == p or domain.endswith("." + p) for p in PAYWALL_DOMAINS)

# ── סינון ראשוני לפני שמירה ──────────────────────────────────────
# כתבה חייבת להזכיר לפחות מילה אחת מהרשימה הזו
INDIANA_REQUIRED = [
    # Indianapolis & immediate metro
    "indianapolis", "indy",
    "carmel", "fishers", "noblesville", "greenwood", "avon", "zionsville",
    "speedway", "beech grove", "lawrence", "castleton", "broad ripple",
    "fountain square", "irvington", "pike township", "warren township",
    "eagle creek", "decatur township",
    # ZIP codes Indianapolis metro
    "46201", "46202", "46203", "46204", "46205", "46208", "46214",
    "46219", "46220", "46221", "46222", "46224", "46225", "46226",
    "46229", "46235", "46239", "46240", "46254", "46256",
    # Real estate data sources
    "mibor",
]

# כתבות כלכלה / ריביות ברמה לאומית — אלה מותרות גם בלי "indiana"
# כי הן משפיעות ישירות על כל משקיע נדל"ן
NATIONAL_ALLOWED = [
    "federal reserve", "fed rate", "mortgage rate", "interest rate",
    "housing market", "home prices", "real estate market",
    "inflation", "cpi", "10-year treasury", "fed pivot",
    "30-year fixed", "construction costs", "lumber prices",
]

def is_relevant_title(title: str) -> bool:
    """סינון מהיר לפי כותרת בלבד — לפני שמורידים את הכתבה."""
    t = title.lower()
    if any(kw in t for kw in INDIANA_REQUIRED):
        return True
    if any(kw in t for kw in NATIONAL_ALLOWED):
        return True
    return False


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def get_real_url_from_entry(entry):
    """Get the actual source URL from a Google News RSS entry."""
    # Google News RSS entries have a 'source' field with the real domain
    # and sometimes store the real URL in 'links'
    source = entry.get("source", {})
    source_href = source.get("href", "")

    # The Google News link is the encoded URL — we need the real article URL
    # Best approach: use the source domain + search for the article
    # But the most reliable is to follow the redirect properly
    gnews_url = entry.get("link", "")
    return gnews_url, source_href


def decode_google_news_url(gnews_url):
    """Decode a Google News encoded URL to the real article URL."""
    if "news.google.com" not in gnews_url:
        return gnews_url
    try:
        result = new_decoderv1(gnews_url)
        real = result.get("decoded_url", "")
        return real if real else gnews_url
    except Exception:
        return gnews_url


def fetch_article_text_and_url(gnews_url):
    """Decode Google News URL, then fetch article text. Returns (text, real_url)."""
    real_url = decode_google_news_url(gnews_url)
    try:
        resp = requests.get(real_url, headers=HEADERS, timeout=14)
        text = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
        return (text or ""), real_url
    except Exception:
        return "", real_url


def parse_date(entry):
    for field in ["published", "updated"]:
        val = getattr(entry, field, None)
        if val:
            return val
    # Indianapolis = UTC-4 (EDT summer) / UTC-5 (EST winter)
    edt = timezone(timedelta(hours=-4))
    return datetime.now(edt).strftime('%Y-%m-%d %H:%M:%S')


def fetch_feed(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        return feedparser.parse(resp.text)
    except Exception as e:
        print(f"  [feed error] {e}")
        return feedparser.FeedParserDict(entries=[])


def run_scraper():
    total_new = 0
    for source in SOURCES:
        print(f"[scraper] Fetching: {source['name']}")
        try:
            feed = fetch_feed(source["url"])
            for entry in feed.entries[:15]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                # ── סינון ראשוני לפי כותרת ──
                if not is_relevant_title(title):
                    print(f"  [skip] {title[:60]}")
                    continue

                gnews_url, source_domain = get_real_url_from_entry(entry)
                if not gnews_url:
                    continue

                published = parse_date(entry)
                full_text, real_url = fetch_article_text_and_url(gnews_url)

                # ── בדוק paywall לפי ה-URL האמיתי ──
                if is_paywalled(real_url):
                    print(f"  [paywall] {real_url[:60]}")
                    continue

                chars = len(full_text)
                saved = save_article(title, gnews_url, source["name"], published, full_text, real_url)
                if saved:
                    total_new += 1
                    print(f"  + [{chars} chars] {title[:55]}")
        except Exception as e:
            print(f"  [error] {source['name']}: {e}")

    print(f"[scraper] Done. {total_new} new articles saved.")
    return total_new


if __name__ == "__main__":
    from database import init_db
    init_db()
    run_scraper()
