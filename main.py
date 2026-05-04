#!/usr/bin/env python3
"""
sglang weekly digest bot.

Usage:
    python main.py              # run once immediately
    python main.py --schedule   # run now then weekly every Monday 09:00 CST
    python main.py --dry-run    # fetch + summarize, print to stdout only
"""

import argparse
import logging
import re
import sys
import time
from datetime import datetime, timezone

from github_fetcher import fetch_commits, fetch_issues
from summarizer import summarize
from feishu_sender import send_report
from feishu_mcp_client import create_and_write_doc
from config import FEISHU_APP_ID, FEISHU_APP_SECRET

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def _extract_overview(report: str) -> str:
    """Return the 本周概览 section text (without the heading line)."""
    lines = report.splitlines()
    overview, in_section = [], False
    for line in lines:
        if re.search(r'本周概览', line) and line.lstrip().startswith('#'):
            in_section = True
            continue
        if in_section:
            if line.lstrip().startswith('#') and re.match(r'#+\s*\d+', line.lstrip()):
                break
            overview.append(line)
    return '\n'.join(overview).strip()


def run(dry_run=False):
    log.info("Fetching commits from sglang/main …")
    commits = fetch_commits()
    log.info("Fetched %d commits", len(commits))

    log.info("Fetching issues …")
    opened, closed = fetch_issues()
    log.info("Opened: %d  Closed: %d", len(opened), len(closed))

    log.info("Summarizing with Claude …")
    report = summarize(commits, opened, closed)

    print("\n" + "=" * 60)
    print(report)
    print("=" * 60 + "\n")

    if dry_run:
        log.info("Dry-run complete — report printed above, not sent to Feishu.")
        return

    # Write full report to Feishu Doc (requires app credentials)
    doc_url = None
    if FEISHU_APP_ID and FEISHU_APP_SECRET:
        # Extract the first ## heading as the doc title; use the rest as body
        lines = report.strip().splitlines()
        doc_title = None
        body_start = 0
        for i, line in enumerate(lines):
            stripped = line.lstrip("#").strip()
            if line.startswith("#") and stripped:
                doc_title = stripped
                body_start = i + 1
                break
        if not doc_title:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            doc_title = f"SGLang 周报 · {today}"
        doc_body = "\n".join(lines[body_start:]).lstrip("\n")
        log.info("Creating Feishu doc '%s' …", doc_title)
        doc_info = create_and_write_doc(doc_title, doc_body)
        doc_url = doc_info["doc_url"]
        log.info("Doc created: %s (%d blocks)", doc_url, doc_info["blocks_written"])
    else:
        log.info("Skipping Feishu doc (FEISHU_APP_ID/SECRET/FOLDER_TOKEN not set)")

    overview = _extract_overview(report)
    log.info("Sending card to Feishu group …")
    result = send_report(overview, len(commits), len(opened), len(closed), doc_url=doc_url)
    log.info("Feishu response: %s", result)
    log.info("Done.")


def _next_monday_9am_cst():
    """Seconds until next Monday 09:00 CST (UTC+8)."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    # CST = UTC+8
    cst_offset = 8 * 3600
    now_ts = now.timestamp() + cst_offset
    # seconds since Monday 00:00 in CST week
    weekday = int(now_ts // 86400) % 7  # 0=Thu epoch, adjust
    # simpler: use datetime arithmetic
    import pytz
    cst = pytz.timezone("Asia/Shanghai")
    now_cst = datetime.now(cst)
    days_until_monday = (7 - now_cst.weekday()) % 7 or 7
    next_monday = now_cst.replace(hour=9, minute=0, second=0, microsecond=0)
    next_monday = next_monday + timedelta(days=days_until_monday)
    delta = (next_monday - now_cst).total_seconds()
    return max(delta, 0)


def schedule_loop():
    log.info("Scheduler started — running immediately, then every Monday 09:00 CST")
    while True:
        run()
        wait = _next_monday_9am_cst()
        log.info("Next run in %.1f hours (next Monday 09:00 CST)", wait / 3600)
        time.sleep(wait)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="sglang weekly digest bot")
    parser.add_argument("--schedule", action="store_true", help="Run on a weekly schedule")
    parser.add_argument("--dry-run", action="store_true", help="Print report to stdout only")
    parser.add_argument("--test-fetch", action="store_true", help="Fetch from GitHub and print raw stats, no Claude/Feishu")
    parser.add_argument("--list-chats", action="store_true", help="List Feishu groups the bot is in (to find FEISHU_CHAT_ID)")
    args = parser.parse_args()

    if args.list_chats:
        from feishu_sender import list_chats
        list_chats()
    elif args.test_fetch:
        from github_fetcher import fetch_commits, fetch_issues
        commits = fetch_commits()
        opened, closed = fetch_issues()
        print(f"Commits: {len(commits)}")
        for c in commits[:5]:
            print(f"  [{c['sha']}] {c['message'][:80]} — {c['author']} {c['url']}")
        print(f"Opened issues: {len(opened)}")
        for i in opened[:5]:
            print(f"  #{i['number']} {i['title'][:80]} {i['url']}")
        print(f"Closed issues: {len(closed)}")
        for i in closed[:5]:
            print(f"  #{i['number']} {i['title'][:80]} {i['url']}")
    elif args.schedule:
        schedule_loop()
    else:
        run(dry_run=args.dry_run)
