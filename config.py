import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "sgl-project/sglang")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_FOLDER_TOKEN = os.getenv("FEISHU_FOLDER_TOKEN", "")
FEISHU_CHAT_ID = os.getenv("FEISHU_CHAT_ID", "")
FEISHU_DOMAIN = os.getenv("FEISHU_DOMAIN", "docs.feishu.cn")

DAYS_LOOKBACK = int(os.getenv("DAYS_LOOKBACK", "7"))  # 7 = weekly

REPOS = [
    {"repo": GITHUB_REPO, "folder_token": FEISHU_FOLDER_TOKEN},
    {"repo": "vllm-project/vllm", "folder_token": os.getenv("VLLM_FEISHU_FOLDER_TOKEN", "")},
]
