#!/usr/bin/env python3
"""
Indy Intel — Full update script
Runs: scraper → analyzer
Scheduled 3x daily via cron
"""
import sys
import os
from pathlib import Path
from datetime import datetime

# Set working directory to project root
os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

LOG_FILE = Path(__file__).parent / "update_log.txt"

def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

if __name__ == "__main__":
    log("=== Starting Indy Intel Update ===")

    from database import init_db, cleanup_old_articles
    init_db()
    cleanup_old_articles()

    from scraper import run_scraper
    log("Scraping news sources...")
    new_count = run_scraper()
    log(f"Scraper done — {new_count} new articles")

    from analyzer import run_analyzer
    log("Analyzing with Claude...")
    run_analyzer()
    log("Analyzer done")

    log("=== Update Complete ===\n")
