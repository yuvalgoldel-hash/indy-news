import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "indy_news.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def cleanup_old_articles():
    conn = get_conn()
    conn.execute("DELETE FROM articles WHERE fetched_at < datetime('now', '-7 days', '-4 hours')")
    conn.commit()
    conn.close()


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            fetched_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', '-4 hours')),
            analyzed INTEGER DEFAULT 0
        )
    """)
    # Add category column if upgrading existing DB
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN category TEXT DEFAULT 'General'")
        conn.commit()
    except Exception:
        pass
    conn.commit()
    conn.close()


def save_article(title, url, source, published, full_text="", real_url=""):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO articles (title, url, real_url, source, published, full_text) VALUES (?,?,?,?,?,?)",
            (title, url, real_url or url, source, published, full_text)
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_unanalyzed():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM articles WHERE analyzed=0 ORDER BY fetched_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return rows


def get_articles_by_category(limit=200):
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM articles WHERE analyzed=1
        ORDER BY fetched_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    from collections import defaultdict
    from datetime import datetime, date

    today = date.today()

    def date_label(fetched_at):
        try:
            d = datetime.strptime(fetched_at[:10], "%Y-%m-%d").date()
            diff = (today - d).days
            if diff == 0: return "Today"
            return d.strftime("%b %d")  # Jun 17, Jun 16...
        except Exception:
            return fetched_at[:10]

    # Group by category → date → articles
    # Structure: { category: { date_label: [articles] } }
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

    # Sort each date group by signal
    def sort_articles(arts):
        order = {"red": 0, "yellow": 1, "green": 2}
        return sorted(arts, key=lambda a: (order.get(a["light"], 2), -(a["relevance_score"] or 0)))

    result = {}
    # Add "All" first
    result["All Stories"] = {k: sort_articles(v) for k, v in all_by_date.items()}
    # Then categories in preferred order
    for cat in CAT_ORDER:
        if cat in grouped:
            result[cat] = {k: sort_articles(v) for k, v in grouped[cat].items()}
    # Any extra categories
    for cat in grouped:
        if cat not in result:
            result[cat] = {k: sort_articles(v) for k, v in grouped[cat].items()}

    return result


def update_analysis(article_id, summary_he, light, relevance_score, category="General"):
    conn = get_conn()
    conn.execute(
        "UPDATE articles SET summary_he=?, light=?, relevance_score=?, category=?, analyzed=1 WHERE id=?",
        (summary_he, light, relevance_score, category, article_id)
    )
    conn.commit()
    conn.close()


def get_all_articles_sorted(limit=100):
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM articles
        ORDER BY
            CASE light WHEN 'red' THEN 1 WHEN 'yellow' THEN 2 ELSE 3 END,
            relevance_score DESC,
            fetched_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows


def get_all_articles(limit=100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM articles ORDER BY fetched_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


def get_article(article_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
    conn.close()
    return row
