import json
import requests
from datetime import datetime, timezone
from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_CHAT_ID, GITHUB_REPO, DAYS_LOOKBACK

_FEISHU_API = "https://open.feishu.cn/open-apis"
_CHUNK = 3500


def _tenant_token() -> str:
    resp = requests.post(
        f"{_FEISHU_API}/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Failed to get tenant token: {data}")
    return data["tenant_access_token"]


def _repo_url():
    return f"https://github.com/{GITHUB_REPO}"


def _md_chunks(text: str):
    if len(text) <= _CHUNK:
        return [text]
    chunks, current, current_len = [], [], 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > _CHUNK and current:
            chunks.append("".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def _build_card(overview: str, commit_count: int, opened_count: int, closed_count: int, doc_url: str = None, repo: str = None) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    repo_name = (repo or GITHUB_REPO).split("/")[-1]

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**提交数：** {commit_count} · "
                    f"**新 Issue：** {opened_count} · "
                    f"**关闭 Issue：** {closed_count}"
                ),
            },
        },
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": overview}},
        {"tag": "hr"},
    ]

    actions = []
    if doc_url:
        actions.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "查看完整周报文档"},
            "type": "primary",
            "url": doc_url,
        })

    if actions:
        elements.append({"tag": "action", "actions": actions})

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"{repo_name} 周报 · {today}"},
            "template": "blue",
        },
        "elements": elements,
    }


def send_report(overview: str, commit_count: int, opened_count: int, closed_count: int, doc_url: str = None, repo: str = None):
    if not FEISHU_CHAT_ID:
        raise ValueError("FEISHU_CHAT_ID is not set — run with --list-chats to find your group ID")

    token = _tenant_token()
    card = _build_card(overview, commit_count, opened_count, closed_count, doc_url=doc_url, repo=repo)

    payload = {
        "receive_id": FEISHU_CHAT_ID,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }

    resp = requests.post(
        f"{_FEISHU_API}/im/v1/messages?receive_id_type=chat_id",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    if result.get("code", 0) != 0:
        raise RuntimeError(f"Feishu API error: {result}")
    return result


def list_chats():
    """Print all groups the bot is a member of, so you can find the chat_id."""
    token = _tenant_token()
    url = f"{_FEISHU_API}/im/v1/chats"
    params = {"page_size": 100}
    while url:
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", 0) != 0:
            raise RuntimeError(f"list_chats failed: {data}")
        for chat in data.get("data", {}).get("items", []):
            print(f"{chat['chat_id']}  {chat.get('name', '(no name)')}")
        page_token = data.get("data", {}).get("page_token")
        if not data.get("data", {}).get("has_more"):
            break
        params = {"page_size": 100, "page_token": page_token}
        url = f"{_FEISHU_API}/im/v1/chats"
