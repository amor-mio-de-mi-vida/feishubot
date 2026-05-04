import logging
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL, GITHUB_REPO, DAYS_LOOKBACK

log = logging.getLogger(__name__)
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")


def _commit_text(commits):
    lines = []
    for c in commits:
        lines.append(f"- [{c['sha']}] {c['message']} (by {c['author']}, {c['date'][:10]}) {c['url']}")
    return "\n".join(lines) if lines else "No commits this week."


def _issue_text(issues, label):
    lines = []
    for i in issues:
        tags = ", ".join(i["labels"]) if i["labels"] else "none"
        date_key = "closed_at" if i["state"] == "closed" else "created_at"
        lines.append(f"- #{i['number']} [{tags}] {i['title']} ({i[date_key][:10]}) {i['url']}")
    return f"### {label}\n" + ("\n".join(lines) if lines else "None.")


def summarize(commits, opened_issues, closed_issues):
    commit_block = _commit_text(commits)
    issue_block = (
        _issue_text(opened_issues, "Newly Opened Issues")
        + "\n\n"
        + _issue_text(closed_issues, "Recently Closed Issues")
    )

    prompt = f"""You are a technical analyst for the open-source project **{GITHUB_REPO}** (a fast LLM serving framework).

Below is the activity on the **main** branch over the past **{DAYS_LOOKBACK} days**.

## Commits ({len(commits)} total)
{commit_block}

## Issues
{issue_block}

Please produce a structured weekly report in **Chinese** with the following sections.

**Output rules**:
- Do NOT add any preamble, greeting, or introductory sentence before the report.
- The very first line must be the title: `## SGLang 技术周报 (YYYY-MM-DD ~ YYYY-MM-DD)` (fill in the actual date range from the commit dates).
- Use only standard Markdown: `##` / `###` / `####` headings, `-` bullet lists, `[text](url)` links, and `**bold**`. Do NOT use HTML or tables.
- **Every commit must appear** in section 2, grouped by category. Do not skip any commit.
- **Commit entry format** — two tiers:

  Tier 1 — regular commit (minor fix, CI change, doc update, small refactor):
  `- [sha](full_commit_url) commit title (#PR) - 一句简短中文说明`
  Keep the Chinese part to one concise sentence.

  Tier 2 — important commit (major feature, significant perf improvement, critical bug fix, key refactor):
  `- [sha](full_commit_url) **commit title (#PR)** - 详细中文分析（2-3句）`
  Bold the title. Write 2-3 sentences explaining: what problem it solves, the technical approach, and why developers should care.

  Example Tier 2:
  `- [62265ca](url) **[diffusion] feat: initial support for dynamic batching (#18764)** - 此前扩散模型每次只能处理单个请求，GPU利用率极低；动态批处理允许多请求合并执行，在并发服务场景下吞吐量可提升数倍。开发者部署时需开启对应参数，对实时图像/视频服务影响显著。`

- **Commit category headers** use `####` with emoji prefix:
  `#### 🚀 性能优化`, `#### 🐛 Bug 修复`, `#### ✨ 新功能`, `#### 📝 文档/测试/CI`, `#### 🔧 重构`, `#### 🧹 其他`
- **Issue 动态** sub-headers use `####`:
  `#### 新开 Issue 主题概览` (group by theme, cite issue numbers inline like `(#12345)`)
  `#### 重要关闭 Issue` (list as `- #number - 标题: 解决说明`)
- **重点关注** numbered items use this multi-line format:
  ```
  1. [Category] 标题 (#PR)
  commit: [sha](url)
  3-4句中文详细说明：改了什么、为什么重要、开发者应该怎么做。
  ```

Sections:
### 1. 本周概览
3-5 sentences: total commit count, most significant themes with numbers, and why these matter.

### 2. 提交分类
Cover ALL commits grouped by category. Use Tier 2 (bold + detailed) for every technically significant commit.

### 3. Issue 动态
Comprehensive: all major themes for new issues (with specific #numbers), then important closed issues.

### 4. 重点关注
Top 3 most impactful changes. Explanations should be detailed and actionable."""

    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        max_tokens=32768,
        messages=[
            {
                "role": "system",
                "content": "You are a senior engineer producing weekly technical digests for a Chinese-speaking engineering team.",
            },
            {"role": "user", "content": prompt},
        ],
    )
    choice = response.choices[0]
    if choice.finish_reason == "length":
        log.warning("DeepSeek output truncated (finish_reason=length). %d commits sent.", len(commits))
    return choice.message.content
