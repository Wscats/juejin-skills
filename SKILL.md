---
version: 1.0.2
name: juejin-skills
license: MIT
description: 掘金技术社区一站式操作技能，支持热门文章排行榜查询、Markdown 文章一键发布和文章下载保存为 Markdown。
source: https://github.com/wscats/juejin
homepage: https://github.com/wscats/juejin
repository:
  type: git
  url: https://github.com/wscats/juejin.git
author: wscats
credentials:
  - name: juejin_session_cookie
    description: 通过 Playwright 浏览器登录后获得的掘金登录态 Cookie。
    storage_path: ~/.juejin_cookie.json
    storage_format: plain-text JSON
    file_permissions: "0600 (owner-only read/write, enforced by auth._save_cookies)"
    scope: 对用户登录的掘金账号具有读写权限（可发文章、读取私有草稿等）。
    rotation: 用户可随时通过删除 ~/.juejin_cookie.json 撤销访问；Cookie 过期后需要重新登录。
    hardening:
      - 不要在多人共享的机器或 CI 容器中使用（Cookie 即账号登录态）。
      - 使用完毕立即执行 `rm ~/.juejin_cookie.json` 撤销。
      - 不要将该文件提交到版本库；本仓库已在 `.clawhubignore` / `.gitignore` 中排除。
permissions:
  - network: 访问 https://juejin.cn/ 与 https://api.juejin.cn/
  - filesystem_write: 写入 ~/.juejin_cookie.json（会话凭证）及 ./output/*.md（下载文章）
  - browser_automation: 启动本地 Chromium 用于登录
publish_policy: draft-only-by-default  # 任何公开发布都需要用户显式确认
publish_policy_enforcement:
  api_layer: |
    juejin_skill.publisher.ArticlePublisher.publish_markdown() 的默认参数为
    save_draft_only=True, allow_public_publish=False。两个标志都需要被显式
    改为 False / True 时才会触发公开发布；任何一侧缺失都会直接拒绝并返回
    draft 结果。
  cli_layer: |
    run_publish.py 默认 draft-only；公开发布需要同时满足：
    (1) --publish 命令行开关, (2) 环境变量 JUEJIN_CONFIRM_PUBLISH=1,
    (3) 交互式输入 'yes'。publish_article.py 的交互流程同样默认走草稿分支，
    选择公开发布后需要再次键入 'yes' 确认。

---

> ⚠️ **凭证与权限声明**
>
> 本技能在登录成功后会把掘金会话 Cookie 以明文 JSON 形式保存到
> `~/.juejin_cookie.json`（文件权限会被设置为 `0600`，仅当前用户可读写）。
> 只要该文件存在且未过期，后续调用即可以你的身份访问掘金账号（发布文章、
> 读取草稿等）。
>
> - 仅在你愿意把掘金登录态保存在本机时才登录，**避免在共享/CI 环境运行**；
> - 使用结束后请执行 `rm ~/.juejin_cookie.json` 主动撤销；
> - 不要将该文件提交版本库（仓库已默认忽略）；
> - 本技能**默认只创建草稿**：API 层 `ArticlePublisher.publish_markdown()`
>   的默认行为是 `save_draft_only=True`，且公开发布还需要调用方额外显式
>   传入 `allow_public_publish=True`。入口脚本 `run_publish.py` 和
>   `publish_article.py` 则在此之上再加了命令行/交互式的人工确认门。

# Juejin Skills - 掘金技术社区操作技能

## 🚀 快速使用
本技能支持以下自然语言指令，直接对 AI 说出即可：

### 热门文章排行榜
- "获取掘金热门文章排行榜"
- "查看掘金前端分类的热门文章"
- "掘金有哪些文章分类？"
- "获取掘金后端/前端/Android/iOS/人工智能分类的热门趋势"
- "帮我看看掘金最近最火的文章是哪些"

### 文章发布
- "帮我把这篇 Markdown 文章发布到掘金"
- "发布文章到掘金，分类为前端，标签为 Vue.js"
- "一键发布文章到掘金平台"
- "登录掘金账号"（会通过 Playwright 打开浏览器让你登录）

### 文章下载
- "下载掘金文章并保存为 Markdown"
- "把这篇掘金文章保存到本地"
- "批量下载掘金某个作者的所有文章"
- "下载这个链接的掘金文章：https://juejin.cn/post/xxx"

---

## 技能描述

| 属性 | 内容 |
|------|------|
| **技能名称** | Juejin Skills（掘金技术社区操作技能） |
| **技能类型** | Prompt-based Skill（自然语言驱动） |
| **技能语言** | Python |
| **目标网站** | https://juejin.cn/ |
| **激活方式** | 自然语言指令 |

## 激活条件

当用户说出或暗示以下内容时，做出回应：

### 1. 热门文章排行榜技能
- 用户想要获取掘金网站热门文章排行榜
- 用户需要查询掘金文章分类列表
- 用户想了解各分类的热门文章趋势
- 用户需要获取全部领域或特定领域的热门文章
- 用户想要了解掘金技术文章排行、阅读量排名
- 关键词：掘金、热门、排行榜、文章分类、趋势、热榜

### 2. 文章发布技能
- 用户想要将 Markdown 文章发布到掘金平台
- 用户需要登录掘金账号（通过 Playwright 浏览器登录获取 Cookie）
- 用户想要设置文章分类、标签、摘要和封面图
- 用户需要一键发布文章到掘金
- 关键词：发布、发文、投稿、掘金、Markdown

### 3. 文章下载技能
- 用户想要下载掘金文章并保存为 Markdown 格式
- 用户需要批量下载某作者的掘金文章
- 用户想要保存掘金文章到本地
- 关键词：下载、保存、导出、Markdown、掘金文章

## 功能清单

### 📊 功能一：热门文章排行榜

| 子功能 | 说明 |
|--------|------|
| 获取分类列表 | 获取掘金所有文章分类（前端、后端、Android、iOS、人工智能等） |
| 热门文章排行 | 获取指定分类或全部分类的热门文章排行榜 |
| 文章趋势分析 | 按时间维度（3天/7天/30天/历史）查看文章热度趋势 |
| 排行榜筛选 | 支持按分类、时间范围、排序方式筛选 |

**API 接口**：
- 分类列表：`GET https://api.juejin.cn/tag_api/v1/query_category_briefs`
- 热门文章：`POST https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed`
- 分类文章：`POST https://api.juejin.cn/recommend_api/v1/article/recommend_cate_feed`
- 标签列表：`POST https://api.juejin.cn/tag_api/v1/query_category_tags`

### 📝 功能二：文章自动发布

| 子功能 | 说明 |
|--------|------|
| 浏览器登录 | 通过 Playwright 打开掘金登录页面，用户扫码或密码登录后自动获取 Cookie |
| Cookie 管理 | 保存、加载、验证 Cookie 状态 |
| Markdown 解析 | 读取本地 Markdown 文件，提取标题、正文内容 |
| 文章发布 | 通过掘金 API 创建草稿并发布，支持设置分类、标签、摘要、封面图 |
| 草稿管理 | 支持保存为草稿而不立即发布 |

**API 接口**：
- 创建草稿：`POST https://api.juejin.cn/content_api/v1/article_draft/create`
- 发布文章：`POST https://api.juejin.cn/content_api/v1/article/publish`
- 获取标签：`POST https://api.juejin.cn/tag_api/v1/query_category_tags`

**鉴权方式**：Cookie 鉴权（通过 Playwright 浏览器登录获取）

### 📥 功能三：文章下载

| 子功能 | 说明 |
|--------|------|
| 单篇下载 | 通过文章 URL 下载单篇文章，保存为 Markdown |
| 批量下载 | 下载指定作者的所有/部分文章 |
| 格式转换 | 将掘金文章 HTML 内容转换为标准 Markdown |
| 图片处理 | 可选下载文章中的图片到本地 |
| 元数据保留 | 保留文章标题、作者、发布时间、标签等元信息 |

**API 接口**：
- 文章详情：`POST https://api.juejin.cn/content_api/v1/article/detail`
- 用户文章列表：`POST https://api.juejin.cn/content_api/v1/article/query_list`

## 技术架构

```
juejin/
├── SKILL.md              # 技能定义文档
├── README.md             # 项目说明文档
├── requirements.txt      # Python 依赖
├── juejin_skill/         # 主模块
│   ├── __init__.py
│   ├── config.py         # 配置管理
│   ├── api.py            # 掘金 API 封装
│   ├── auth.py           # 登录鉴权（Playwright）
│   ├── hot_articles.py   # 热门文章排行榜
│   ├── publisher.py      # 文章发布
│   ├── downloader.py     # 文章下载
│   └── utils.py          # 工具函数
└── output/               # 下载文章输出目录
```

## 环境要求

- Python >= 3.9
- Playwright（用于浏览器登录）
- 网络可访问 https://juejin.cn/

## Prompt 示例

```
用户：帮我获取掘金前端分类的热门文章排行榜
AI：正在获取掘金前端分类的热门文章...

用户：把 ./my-article.md 发布到掘金，分类选前端，标签加上 Vue.js 和 TypeScript
AI：正在登录掘金账号并发布文章...

用户：下载这篇掘金文章 https://juejin.cn/post/7300000000000000000
AI：正在下载文章并转换为 Markdown 格式...
```
