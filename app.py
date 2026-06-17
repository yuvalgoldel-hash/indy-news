from flask import Flask, render_template, jsonify, request, Response, redirect
from neighborhoods_data import NEIGHBORHOODS
from database import init_db, get_all_articles, get_all_articles_sorted, get_article, get_articles_by_category
from scraper import run_scraper
from analyzer import run_analyzer
import os, requests, re
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Make neighborhoods available in all templates
@app.context_processor
def inject_globals():
    def get_neighborhoods():
        return sorted(NEIGHBORHOODS, key=lambda x: x["crime_index"])
    return dict(get_neighborhoods=get_neighborhoods)

PROXY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@app.route("/")
def index():
    filter_light = request.args.get("filter", "all")
    articles = get_all_articles_sorted(limit=200)
    if filter_light != "all":
        articles = [a for a in articles if a["light"] == filter_light]
    all_articles = get_all_articles(200)
    counts = {
        "all": len(all_articles),
        "red": sum(1 for a in all_articles if a["light"] == "red"),
        "yellow": sum(1 for a in all_articles if a["light"] == "yellow"),
        "green": sum(1 for a in all_articles if a["light"] == "green"),
    }
    by_category = get_articles_by_category()
    return render_template("index.html", articles=articles, filter_light=filter_light, counts=counts, by_category=by_category)


@app.route("/article/<int:article_id>")
def article(article_id):
    art = get_article(article_id)
    if not art:
        return "Article not found", 404
    return render_template("article.html", article=art)


@app.route("/proxy")
def proxy():
    """Fetch external article and strip X-Frame-Options so it can be embedded."""
    url = request.args.get("url", "")
    if not url or not url.startswith("http"):
        return "Invalid URL", 400
    try:
        resp = requests.get(url, headers=PROXY_HEADERS, timeout=15, allow_redirects=True)
        content = resp.text

        # Fix relative URLs to absolute so images/links still work
        base = "/".join(url.split("/")[:3])
        content = re.sub(r'(href|src)="(/[^"]*)"', rf'\1="{base}\2"', content)
        content = re.sub(r"(href|src)='(/[^']*)'", rf"\1='{base}\2'", content)

        # Inject base tag so relative assets load correctly
        base_tag = f'<base href="{url}">'
        content = content.replace("<head>", f"<head>{base_tag}", 1)
        if "<head>" not in content:
            content = base_tag + content

        # Remove any CSP or frame-blocking headers
        response = Response(content, status=resp.status_code)
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        # Do NOT pass X-Frame-Options or Content-Security-Policy
        return response

    except Exception as e:
        return f"<html><body style='font-family:sans-serif;padding:40px;text-align:center'><h2>⚠️ Could not load article</h2><p>{str(e)}</p><a href='{url}' target='_blank' style='color:#e63946'>Open in New Tab ↗</a></body></html>", 200


@app.route("/category/<path:cat_name>")
def category(cat_name):
    by_cat = get_articles_by_category()
    # Find matching category
    matched = None
    for cat, date_groups in by_cat.items():
        slug = cat.replace(' ','_').replace('&','and').replace('/','_')
        if slug == cat_name or cat == cat_name:
            matched = (cat, date_groups)
            break
    if not matched:
        return redirect('/')
    return render_template("category.html", cat_name=matched[0], date_groups=matched[1])


@app.route("/neighborhoods")
def neighborhoods():
    from neighborhoods_data import NEIGHBORHOODS
    sorted_n = sorted(NEIGHBORHOODS, key=lambda x: x["crime_index"])
    return render_template("neighborhoods.html", neighborhoods=sorted_n)


@app.route("/api/mark-read/<int:article_id>", methods=["POST"])
def mark_read(article_id):
    from database import get_conn
    conn = get_conn()
    conn.execute("UPDATE articles SET is_read=1 WHERE id=?", (article_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/mark-unread/<int:article_id>", methods=["POST"])
def mark_unread(article_id):
    from database import get_conn
    conn = get_conn()
    conn.execute("UPDATE articles SET is_read=0 WHERE id=?", (article_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/refresh", methods=["POST"])
def refresh():
    new_count = run_scraper()
    run_analyzer()
    return jsonify({"status": "ok", "new": new_count})


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5050)
