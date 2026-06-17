import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    url = DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # Render gives postgres:// but psycopg2 needs postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            real_url TEXT,
            source TEXT,
            published TEXT,
            full_text TEXT,
            summary_he TEXT,
            light TEXT DEFAULT 'green',
            relevance_score INTEGER DEFAULT 0,
            category TEXT DEFAULT 'General',
            fetched_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'America/New_York'),
            analyzed INTEGER DEFAULT 0,
            is_read INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def cleanup_old_articles():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM articles WHERE fetched_at < NOW() - INTERVAL '7 days'")
    conn.commit()
    cur.close()
    conn.close()


def save_article(title, url, source, published, full_text="", real_url=""):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO articles (title, url, real_url, source, published, full_text)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (url) DO NOTHING""",
            (title, url, real_url or url, source, published, full_text)
        )
        saved = cur.rowcount > 0
        conn.commit()
        return saved
    except Exception:
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


def get_unanalyzed():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM articles WHERE analyzed=0 ORDER BY fetched_at DESC LIMIT 20")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_articles_by_category(limit=200):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM articles WHERE analyzed=1
        ORDER BY fetched_at DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    from collections import defaultdict
    from datetime import date

    today = date.today()

    def date_label(fetched_at):
        try:
            if isinstance(fetched_at, str):
                d = datetime.strptime(fetched_at[:10], "%Y-%m-%d").date()
            else:
                d = fetched_at.date()
            diff = (today - d).days
            if diff == 0:
                return "Today"
            return d.strftime("%b %d")
        except Exception:
            return str(fetched_at)[:10]

    CAT_ORDER = [
        "Fix & Flip", "Rental Market", "Development & Construction",
        "Jobs & Companies", "Interest Rates & Fed", "Mortgages",
        "Market Prices & Stats", "Population & Growth", "General"
    ]

    grouped = defaultdict(lambda: defaultdict(list))
    all_by_date = defaultdict(list)

    for row in rows:
        cat = row["category"] or "General"
        label = date_label(row["fetched_at"])
        grouped[cat][label].append(row)
        all_by_date[label].append(row)

    def sort_articles(arts):
        order = {"red": 0, "yellow": 1, "green": 2}
        return sorted(arts, key=lambda a: (order.get(a["light"], 2), -(a["relevance_score"] or 0)))

    result = {}
    result["All Stories"] = {k: sort_articles(v) for k, v in all_by_date.items()}
    for cat in CAT_ORDER:
        if cat in grouped:
            result[cat] = {k: sort_articles(v) for k, v in grouped[cat].items()}
    for cat in grouped:
        if cat not in result:
            result[cat] = {k: sort_articles(v) for k, v in grouped[cat].items()}

    return result


def update_analysis(article_id, summary_he, light, relevance_score, category="General"):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE articles SET summary_he=%s, light=%s, relevance_score=%s, category=%s, analyzed=1 WHERE id=%s",
        (summary_he, light, relevance_score, category, article_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def get_all_articles_sorted(limit=100):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM articles
        ORDER BY
            CASE light WHEN 'red' THEN 1 WHEN 'yellow' THEN 2 ELSE 3 END,
            relevance_score DESC,
            fetched_at DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_all_articles(limit=100):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM articles ORDER BY fetched_at DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_article(article_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM articles WHERE id=%s", (article_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row
