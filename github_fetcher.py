import requests
from datetime import datetime, timezone, timedelta
from config import GITHUB_TOKEN, GITHUB_REPO, DAYS_LOOKBACK


def _headers():
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if GITHUB_TOKEN and GITHUB_TOKEN.startswith("ghp_") and len(GITHUB_TOKEN) > 30:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _since_iso():
    dt = datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _paginate(url, params):
    """Follow GitHub Link: next headers and yield every item across all pages."""
    while url:
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        yield from resp.json()
        # Parse next page URL from Link header
        url = None
        params = {}  # params are already encoded in the next URL
        link_header = resp.headers.get("Link", "")
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break


def fetch_commits():
    since = _since_iso()
    url = f"https://api.github.com/repos/{GITHUB_REPO}/commits"
    params = {"sha": "main", "since": since, "per_page": 100}
    commits = []
    for item in _paginate(url, params):
        commits.append({
            "sha": item["sha"][:7],
            "message": item["commit"]["message"].split("\n")[0],
            "author": item["commit"]["author"]["name"],
            "date": item["commit"]["author"]["date"],
            "url": item["html_url"],
        })
    return commits


def fetch_issues():
    since = _since_iso()
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"

    # Newly opened issues (updated since = covers newly created ones)
    params = {"state": "open", "since": since, "per_page": 100, "sort": "created", "direction": "desc"}
    opened = []
    for item in _paginate(url, params):
        if item.get("pull_request"):
            continue
        # Only include issues actually created within the window
        if item.get("created_at", "") >= since:
            opened.append({
                "number": item["number"],
                "title": item["title"],
                "state": "open",
                "labels": [l["name"] for l in item.get("labels", [])],
                "created_at": item["created_at"],
                "url": item["html_url"],
                "body_preview": (item.get("body") or "")[:200],
            })

    # Recently closed issues
    params = {"state": "closed", "since": since, "per_page": 100, "sort": "updated", "direction": "desc"}
    closed = []
    for item in _paginate(url, params):
        if item.get("pull_request"):
            continue
        if item.get("closed_at", "") >= since:
            closed.append({
                "number": item["number"],
                "title": item["title"],
                "state": "closed",
                "labels": [l["name"] for l in item.get("labels", [])],
                "closed_at": item["closed_at"],
                "url": item["html_url"],
                "body_preview": (item.get("body") or "")[:200],
            })

    return opened, closed
