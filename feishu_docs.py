"""
Direct Python client for Feishu Docs API.
Matches the exact block format used by feishu-mcp internally.
"""
import re
import requests
from datetime import datetime, timezone
from config import FEISHU_APP_ID, FEISHU_APP_SECRET

_BASE = "https://open.feishu.cn/open-apis"
_BATCH = 50  # max blocks per API call


# ── Auth ──────────────────────────────────────────────────────────────────────

def _token():
    resp = requests.post(
        f"{_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["tenant_access_token"]


def _headers():
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


# ── Document ──────────────────────────────────────────────────────────────────

def create_document(title: str) -> dict:
    # Omitting folder_token creates the doc in the app's root space
    resp = requests.post(
        f"{_BASE}/docx/v1/documents",
        headers=_headers(),
        json={"title": title},
        timeout=15,
    )
    resp.raise_for_status()
    doc = resp.json()["data"]["document"]
    doc_id = doc["document_id"]
    return {"doc_id": doc_id, "doc_url": f"https://docs.feishu.cn/docx/{doc_id}"}


def append_blocks(doc_id: str, blocks: list) -> int:
    """Append raw Feishu block dicts to the document root. Returns total blocks written."""
    url = f"{_BASE}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children"
    written = 0
    for i in range(0, len(blocks), _BATCH):
        chunk = blocks[i : i + _BATCH]
        resp = requests.post(
            url,
            headers=_headers(),
            json={"children": chunk, "index": -1},
            timeout=30,
        )
        resp.raise_for_status()
        written += len(chunk)
    return written


# ── Markdown → Feishu blocks ──────────────────────────────────────────────────

_DEFAULT_STYLE = {"bold": False, "italic": False, "inline_code": False,
                  "strikethrough": False, "underline": False}
_INLINE = re.compile(r"(\*\*.*?\*\*|\[.*?\]\(.*?\)|`[^`]+`)")


def _runs(text: str) -> list:
    """Split one line of markdown into text_run elements."""
    runs = []
    for part in _INLINE.split(text):
        if not part:
            continue
        bold = re.fullmatch(r"\*\*(.*?)\*\*", part)
        link = re.fullmatch(r"\[(.*?)\]\((.*?)\)", part)
        code = re.fullmatch(r"`([^`]+)`", part)
        if bold:
            style = {**_DEFAULT_STYLE, "bold": True}
            runs.append({"text_run": {"content": bold.group(1), "text_element_style": style}})
        elif link:
            style = {**_DEFAULT_STYLE, "link": {"url": link.group(2)}}
            runs.append({"text_run": {"content": link.group(1), "text_element_style": style}})
        elif code:
            style = {**_DEFAULT_STYLE, "inline_code": True}
            runs.append({"text_run": {"content": code.group(1), "text_element_style": style}})
        else:
            runs.append({"text_run": {"content": part, "text_element_style": dict(_DEFAULT_STYLE)}})
    return runs or [{"text_run": {"content": text, "text_element_style": dict(_DEFAULT_STYLE)}}]


def _block(block_type: int, key: str, runs: list) -> dict:
    return {
        "block_type": block_type,
        key: {"elements": runs, "style": {"align": 1, "folded": False}},
    }


def md_to_blocks(md: str) -> list:
    blocks = []
    in_code = False
    code_lines: list[str] = []
    code_lang = ""

    for raw in md.splitlines():
        line = raw.rstrip()

        # Fenced code block
        fence = re.match(r"^```(\w*)", line)
        if fence and not in_code:
            in_code = True
            code_lang = fence.group(1)
            code_lines = []
            continue
        if in_code:
            if line.strip() == "```":
                blocks.append({
                    "block_type": 14,
                    "code": {
                        "elements": [{"text_run": {"content": "\n".join(code_lines),
                                                   "text_element_style": dict(_DEFAULT_STYLE)}}],
                        "style": {"language": 1, "wrap": False},
                    },
                })
                in_code = False
            else:
                code_lines.append(raw)
            continue

        if not line:
            continue

        # Divider
        if re.match(r"^[-*_]{3,}$", line):
            blocks.append({"block_type": 22, "divider": {}})
            continue

        # Headings — check most-specific first
        h = re.match(r"^(#{1,6})\s+(.*)", line)
        if h:
            level = min(len(h.group(1)), 9)
            key = f"heading{level}"
            blocks.append(_block(2 + level, key, _runs(h.group(2))))
            continue

        # Bullet list
        bullet = re.match(r"^[-*]\s+(.*)", line)
        if bullet:
            blocks.append(_block(12, "bullet", _runs(bullet.group(1))))
            continue

        # Numbered list (render as bullet)
        numbered = re.match(r"^\d+\.\s+(.*)", line)
        if numbered:
            blocks.append(_block(12, "bullet", _runs(numbered.group(1))))
            continue

        # Blockquote — strip leading >
        line = re.sub(r"^>\s*", "", line)
        if line:
            blocks.append(_block(2, "text", _runs(line)))

    return blocks


# ── High-level helper ─────────────────────────────────────────────────────────

def create_and_write_doc(title: str, markdown: str) -> dict:
    result = create_document(title)
    blocks = md_to_blocks(markdown)
    written = append_blocks(result["doc_id"], blocks)
    result["blocks_written"] = written
    return result
