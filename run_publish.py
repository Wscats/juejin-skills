"""One-shot publish script - creates a draft on Juejin."""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from juejin_skill.auth import JuejinAuth
from juejin_skill.publisher import ArticlePublisher

# Load cookie
auth = JuejinAuth()
cookie = auth.load_cookie()
if not cookie:
    print("❌ No cookie found. Run login first.")
    sys.exit(1)
print("✅ Cookie loaded")

# Initialize publisher
pub = ArticlePublisher(cookie=cookie)

# Get tags
frontend_id = "6809637767543259144"
tags = pub.search_tags(frontend_id)
print(f"🏷️  Got {len(tags)} tags")
for i, t in enumerate(tags[:10]):
    print(f"  [{i+1}] {t['tag_name']}")

selected_tags = [tags[0]["tag_id"]] if tags else []

# Article content
content = """## 前言

这是一篇通过 **Juejin Skills** 自动发布工具发送的测试文章。

## 功能介绍

Juejin Skills 是一个基于 Python 的掘金操作工具集，支持：

- 🔥 **热门排行榜查询** - 获取各分类热门文章
- 📤 **文章自动发布** - Markdown 一键发布到掘金
- 📥 **文章下载** - 将掘金文章保存为 Markdown 格式

## 技术实现

- 使用 `httpx` 进行 API 调用
- 使用 `Playwright` 实现浏览器登录获取 Cookie
- 基于掘金官方 API 接口

## 总结

如果你觉得这个工具有用，欢迎 Star ⭐！
"""

print("\n📤 Creating draft...")
result = pub.publish_markdown(
    content=content,
    title="Hello Juejin - 来自自动发布工具的测试文章",
    category_id=frontend_id,
    tag_ids=selected_tags,
    brief_content="这是一篇通过 Juejin Skills 自动发布工具发送的测试文章",
    save_draft_only=True,
)

print(f"\n📋 Result: {json.dumps(result, indent=2, ensure_ascii=False)}")

if result.get("success") and result.get("draft_id"):
    print(f"\n🎉 Draft created! draft_id={result['draft_id']}")
    print("Now publishing the draft...")

    # Publish the draft
    result2 = pub.publish_markdown(
        content=content,
        title="Hello Juejin - 来自自动发布工具的测试文章",
        category_id=frontend_id,
        tag_ids=selected_tags,
        brief_content="这是一篇通过 Juejin Skills 自动发布工具发送的测试文章",
        save_draft_only=False,
    )
    print(f"\n📋 Publish Result: {json.dumps(result2, indent=2, ensure_ascii=False)}")
