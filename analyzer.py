import anthropic
import os
from pathlib import Path
from dotenv import load_dotenv
from database import get_unanalyzed, update_analysis

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a senior real estate investment analyst specializing in Indianapolis, Indiana.
Your clients are professional investors focused on Fix & Flip and Rental properties in Indiana.

Write your analysis IN HEBREW only. Plain text — no asterisks, no hashtags, no Markdown.
Important: write ALL text in Hebrew. Do not use English words mid-sentence.
Translate: Fix & Flip → קנייה-שיפוץ-מכירה, Rental → השכרה, BTR → בנייה להשכרה.

Use this EXACT structure:

סיכום: [3-4 משפטים — מה קרה, מי מעורב, נתונים מספריים רלוונטיים]

השפעה על קנייה-שיפוץ-מכירה: [2-3 משפטים — השפעה על עסקאות, עלות מימון, ביקוש לנכסים משופצים]

השפעה על נכסי השכרה: [2-3 משפטים — תשואות שכירות, ביקוש, כדאיות לטווח ארוך]

הזדמנויות בשוק: [2-3 משפטים — הזדמנויות ספציפיות, אזורים, סוגי נכסים]

המלצה לפעולה: [המלצה ספציפית וברורה]

LIGHT: red
SCORE: 8
CATEGORY: Interest Rates & Fed

Rules:
red = important, direct opportunity or risk, act now
yellow = developing trend, track it
green = general info, indirect relevance

CATEGORY must be exactly one of these English values — choose the MOST specific one:
- Mortgages → any article about mortgage rates, home loans, refinancing, lending, 30-year fixed, ARM
- Interest Rates & Fed → Federal Reserve decisions, Fed rate, treasury yields, inflation/CPI (not mortgage-specific)
- Development & Construction → new construction, permits, builders, zoning, development projects
- Jobs & Companies → hiring, layoffs, companies expanding/closing, employment data
- Population & Growth → migration, population trends, demographics, city growth
- Market Prices & Stats → home prices, median price, days on market, inventory, MLS data
- Rental Market → rents, rental demand, landlord/tenant, multifamily, BTR
- Fix & Flip → flipping, wholesale, distressed properties, ARV, rehab
- General → only if NONE of the above apply

NEVER use General if the article fits any other category.

If not related to real estate, Indianapolis, economy, rates, or employment:
LIGHT: green
SCORE: 1
CATEGORY: General
And write in Hebrew: כתבה זו אינה רלוונטית ישירות להשקעות נדל"ן באינדיאנפוליס."""


def analyze_article(title, full_text, url):
    content = f"כותרת: {title}\n\nתוכן:\n{full_text[:3000] if full_text else 'אין תוכן זמין'}\n\nמקור: {url}"

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}]
    )

    response = message.content[0].text

    VALID_CATEGORIES = [
        "Interest Rates & Fed", "Mortgages", "Development & Construction",
        "Jobs & Companies", "Population & Growth", "Market Prices & Stats",
        "Rental Market", "Fix & Flip", "General"
    ]

    light = "green"
    score = 5
    category = "General"

    for line in response.split("\n"):
        if line.startswith("LIGHT:"):
            val = line.replace("LIGHT:", "").strip().lower()
            if val in ("red", "yellow", "green"):
                light = val
        if line.startswith("SCORE:"):
            try:
                score = int(line.replace("SCORE:", "").strip())
            except Exception:
                pass
        if line.startswith("CATEGORY:"):
            val = line.replace("CATEGORY:", "").strip()
            if val in VALID_CATEGORIES:
                category = val

    summary = response.split("LIGHT:")[0].strip()
    return summary, light, score, category


INDIANA_KEYWORDS = [
    "indianapolis", "indiana", "indy", "hoosier",
    "46201", "46202", "46203", "46204", "46205", "46219", "46229",
    "carmel", "fishers", "greenwood", "avon", "noblesville", "zionsville",
    "fort wayne", "evansville", "lafayette",
    "mortgage rate", "federal reserve", "interest rate", "fed rate",
    "housing market", "real estate market", "home prices",
]

def is_relevant(title, text):
    combined = (title + " " + (text or "")).lower()
    return any(kw in combined for kw in INDIANA_KEYWORDS)


def run_analyzer():
    articles = get_unanalyzed()
    print(f"[analyzer] {len(articles)} articles to analyze")
    for article in articles:
        if not is_relevant(article["title"], article["full_text"]):
            update_analysis(article["id"], "כתבה לא רלוונטית לאינדיאנפוליס או לשוק הנדל\"ן.", "green", 1)
            print(f"  [skip] {article['title'][:60]}")
            continue
        print(f"  Analyzing: {article['title'][:60]}")
        try:
            summary, light, score, category = analyze_article(
                article["title"], article["full_text"], article["url"]
            )
            update_analysis(article["id"], summary, light, score, category)
            print(f"  → {light.upper()} (score: {score}) [{category}]")
        except Exception as e:
            print(f"  [error] {e}")
    print("[analyzer] Done.")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_analyzer()
