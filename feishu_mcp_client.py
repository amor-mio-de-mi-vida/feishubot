"""
Feishu docs writer.
- Creates document via feishu-mcp stdio server (handles folder token / auth setup)
- Writes blocks via direct Feishu Docs API (supports inline links, bold, etc.)
"""
import asyncio
import json
import re
import os
import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_FOLDER_TOKEN, FEISHU_DOMAIN

_FEISHU_API = "https://open.feishu.cn/open-apis"
_BATCH_SIZE = 50   # blocks per direct-API call


# ── Auth ──────────────────────────────────────────────────────────────────────

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


# ── Document creation via feishu-mcp ─────────────────────────────────────────

def _server_params():
    env = {**os.environ, "FEISHU_APP_ID": FEISHU_APP_ID, "FEISHU_APP_SECRET": FEISHU_APP_SECRET}
    return StdioServerParameters(
        command="npx",
        args=[
            "feishu-mcp", "--stdio",
            "--enabled-modules", "document",
            "--feishu-scope-validation=false",
            "--log-level", "none",
        ],
        env=env,
    )


async def _create_doc(title: str) -> tuple:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            create_args = {"title": title}
            if FEISHU_FOLDER_TOKEN:
                create_args["folderToken"] = FEISHU_FOLDER_TOKEN
            r = await session.call_tool("create_feishu_document", create_args)
            text = r.content[0].text if r.content else ""
            if r.isError or text.startswith("创建文档失败"):
                if "1770040" in text or "no folder permission" in text:
                    raise RuntimeError(
                        "Feishu folder permission denied (1770040).\n"
                        "Share the folder with the app in Feishu Drive:\n"
                        "  Folder → ··· → Share → add app → Editor"
                    )
                raise RuntimeError(f"create_feishu_document failed: {text}")
            doc_data = json.loads(text)
            import logging; log = logging.getLogger(__name__)
            log.info("feishu-mcp doc_data keys: %s", list(doc_data.keys()))
            doc_id = (doc_data.get("document_id") or doc_data.get("obj_token")
                      or doc_data.get("document", {}).get("document_id")
                      or doc_data.get("data", {}).get("document", {}).get("document_id"))
            doc_url = doc_data.get("url") or f"https://{FEISHU_DOMAIN}/docx/{doc_id}"
            log.info("doc_id=%s  doc_url=%s", doc_id, doc_url)
            return doc_id, doc_url


# ── Block writing via direct Feishu Docs API ──────────────────────────────────

def _write_blocks(doc_id: str, blocks: list, token: str) -> int:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    url = f"{_FEISHU_API}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children"
    total = 0
    for i in range(0, len(blocks), _BATCH_SIZE):
        chunk = blocks[i: i + _BATCH_SIZE]
        resp = requests.post(url, headers=headers,
                             data=json.dumps({"children": chunk, "index": i}, ensure_ascii=False).encode("utf-8"),
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Block write failed (batch {i}): {data}")
        total += len(chunk)
    return total


async def _create_and_write(title: str, blocks: list) -> dict:
    doc_id, doc_url = await _create_doc(title)
    token = _tenant_token()
    total = _write_blocks(doc_id, blocks, token)
    return {"doc_id": doc_id, "doc_url": doc_url, "blocks_written": total}


# ── Markdown → native Feishu API block format ────────────────────────────────
# Block type numbers (Feishu API):
#   2=text, 3=heading1, 4=heading2, ..., 11=heading9
#  12=bullet, 13=ordered, 14=code

_INLINE = re.compile(r"(\*\*.*?\*\*|\[.*?\]\(.*?\)|`[^`]+`)")


def _elements(text: str) -> list:
    """Parse inline markdown into Feishu text_run elements (with link support)."""
    result = []
    for part in _INLINE.split(text):
        if not part:
            continue
        bold = re.fullmatch(r"\*\*(.*?)\*\*", part)
        link = re.fullmatch(r"\[(.*?)\]\((.*?)\)", part)
        code = re.fullmatch(r"`([^`]+)`", part)
        if bold:
            result.append({"text_run": {"content": bold.group(1),
                                        "text_element_style": {"bold": True}}})
        elif link:
            result.append({"text_run": {"content": link.group(1),
                                        "text_element_style": {
                                            "link": {"url": link.group(2)},
                                            "underline": True,
                                        }}})
        elif code:
            result.append({"text_run": {"content": code.group(1),
                                        "text_element_style": {"inline_code": True}}})
        else:
            result.append({"text_run": {"content": part, "text_element_style": {}}})
    return result or [{"text_run": {"content": text, "text_element_style": {}}}]


def md_to_feishu_blocks(md: str) -> list:
    blocks = []
    in_code, code_lines = False, []

    for raw in md.splitlines():
        line = raw.rstrip()

        # Fenced code block
        fence = re.match(r"^```(\w*)", line)
        if fence and not in_code:
            in_code, code_lines = True, []
            continue
        if in_code:
            if line.strip() == "```":
                blocks.append({
                    "block_type": 14,
                    "code": {
                        "elements": [{"text_run": {"content": "\n".join(code_lines),
                                                   "text_element_style": {}}}],
                        "style": {"language": 1, "wrap": False},
                    },
                })
                in_code = False
            else:
                code_lines.append(raw)
            continue

        if not line or re.match(r"^[-*_]{3,}$", line):
            continue

        # Headings — block_type = 2 + level (h1=3, h2=4, h3=5 …)
        h = re.match(r"^(#{1,6})\s+(.*)", line)
        if h:
            level = min(len(h.group(1)), 9)
            hkey = f"heading{level}"
            blocks.append({
                "block_type": 2 + level,
                hkey: {
                    "elements": [{"text_run": {"content": h.group(2),
                                               "text_element_style": {}}}],
                    "style": {"align": 1, "folded": False},
                },
            })
            continue

        # Bullet list
        bullet = re.match(r"^[-*]\s+(.*)", line)
        if bullet:
            blocks.append({
                "block_type": 12,
                "bullet": {"elements": _elements(bullet.group(1)), "style": {"align": 1}},
            })
            continue

        # Numbered list
        numbered = re.match(r"^(\d+)\.\s+(.*)", line)
        if numbered:
            blocks.append({
                "block_type": 13,
                "ordered": {"elements": _elements(numbered.group(2)), "style": {"align": 1}},
            })
            continue

        # Blockquote — strip leading >
        line = re.sub(r"^>\s*", "", line)
        if line:
            blocks.append({
                "block_type": 2,
                "text": {"elements": _elements(line), "style": {"align": 1}},
            })

    return blocks


# ── Public API ────────────────────────────────────────────────────────────────

def create_and_write_doc(title: str, markdown: str) -> dict:
    """Synchronous wrapper — creates doc via feishu-mcp, writes blocks via direct API."""
    blocks = md_to_feishu_blocks(markdown)
    return asyncio.run(_create_and_write(title, blocks))
