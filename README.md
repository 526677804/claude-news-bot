# Claude Code 每日资讯工作流

## 📋 项目概述

一个自动化的 Claude Code 相关资讯采集和推送工作流，每天定时从多个信息源采集最新资讯，经过 AI 深度整理后，推送到飞书群。

### 核心功能
- 📰 多源资讯采集（官方博客、GitHub、科技媒体、社区等）
- 🤖 AI 智能整理（摘要、点评、分类、TOP 1 精选）
- 📤 飞书群自动推送
- 💬 群内互动指令（帮助、今日、状态、关键词调整）
- 🔔 失败告警（推送失败时通知管理员）
- 👋 新成员欢迎（自动发私信欢迎新成员）
- 🔄 采集重试机制（失败自动重试）

---

## 📁 项目结构

```
claude-news-bot/
├── config.json              # 配置文件（核心）
├── fetch_news.py            # 资讯采集脚本
├── ai_report.py             # AI 整理脚本（Cursor SDK 无头代理，首选）
├── generate_report.py       # 模板整理脚本（AI 不可用时的降级方案）
├── mark_seen.py             # 已推送记录维护（推送成功后运行）
├── seen_urls.json           # 已推送 URL 记录（保留 60 天，Actions 自动回写）
├── push_to_feishu.py        # 飞书推送脚本
├── bot_listener.py          # 互动指令监听机器人
├── manage.sh                # 运维管理脚本（本地/手动模式）
├── test_sources.py          # 信息源测试脚本
├── welcome_message.txt      # 新成员欢迎消息
├── requirements.txt         # Python 依赖
├── .env.example             # 环境变量模板（API Key 配置）
├── .gitignore               # Git 忽略配置
├── deploy/                  # 服务器部署配置
│   ├── setup.sh             # 一键部署脚本（Ubuntu/Debian）
│   ├── claude-news-daily.service   # 每日采集推送（systemd oneshot）
│   ├── claude-news-daily.timer     # 每天 10:00 触发（systemd timer）
│   └── claude-news-bot.service     # 互动机器人常驻服务
└── README.md                # 本说明文档
```

---

## ⚙️ 配置文件说明（config.json）

### 完整配置结构

```json
{
  "keywords": [
    "Claude Code",
    "ClaudeCode",
    "Anthropic",
    "Claude 3.5",
    "Claude 3.5 Sonnet",
    "Claude 3 Opus",
    "Claude 3 Haiku",
    "Dario Amodei",
    "Daniela Amodei",
    "Claude AI",
    "Anthropic Claude",
    "Claude API",
    "Claude 4",
    "Claude Opus",
    "Claude Sonnet"
  ],
  "sources": {
    "official_blog": {
      "enabled": true,
      "url": "https://www.anthropic.com/news",
      "name": "Anthropic 官方博客",
      "reliability": "official"
    },
    "claude_code_releases": {
      "enabled": true,
      "url": "https://github.com/anthropics/claude-code/releases.atom",
      "name": "Claude Code 版本发布",
      "reliability": "official"
    },
    "github": {
      "enabled": true,
      "name": "GitHub",
      "reliability": "high"
    },
    "hackernews": {
      "enabled": true,
      "name": "Hacker News",
      "reliability": "high"
    },
    "techcrunch": {
      "enabled": true,
      "name": "TechCrunch",
      "reliability": "high",
      "url": "https://techcrunch.com/tag/anthropic/"
    },
    "theverge": {
      "enabled": true,
      "name": "The Verge",
      "reliability": "high",
      "url": "https://www.theverge.com/ai-artificial-intelligence"
    },
    "arstechnica": {
      "enabled": true,
      "name": "Ars Technica",
      "reliability": "high",
      "url": "https://arstechnica.com/ai/"
    },
    "reddit": {
      "enabled": true,
      "subreddits": ["ClaudeAI", "Anthropic"],
      "name": "Reddit",
      "reliability": "medium"
    },
    "v2ex": {
      "enabled": false,
      "name": "V2EX",
      "nodes": ["programmer", "create", "share", "ai"],
      "reliability": "medium"
    },
    "twitter": {
      "enabled": true,
      "name": "X (Twitter)",
      "reliability": "high",
      "nitter_instances": ["https://nitter.net", "https://nitter.perennialte.ch"],
      "max_age_hours": 36,
      "account_groups": {
        "official": {
          "name": "官方账号",
          "filter_by_keywords": false,
          "score": 90,
          "accounts": ["AnthropicAI", "claudeai"]
        },
        "claude_code_team": {
          "name": "Claude Code 核心团队",
          "filter_by_keywords": false,
          "score": 80,
          "accounts": ["bcherny", "catwu", "trq212", "noahzweben",
                       "amorriscode", "alexalbert__", "neilhtennek", "lydiahallie"]
        },
        "founders": {
          "name": "Anthropic 创始人",
          "filter_by_keywords": true,
          "score": 70,
          "accounts": ["DarioAmodei", "DanielaAmodei", "jackclarkSF", "jaredkaplan"]
        },
        "researchers": {
          "name": "核心研究员",
          "filter_by_keywords": true,
          "score": 60,
          "accounts": ["karpathy", "sleepinyourhat", "ch402", "johnschulman2", "amandaaskell"]
        }
      }
    },
    "kol_blogs": {
      "enabled": true,
      "name": "KOL 博客",
      "reliability": "high",
      "feeds": [
        {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/"}
      ]
    }
  },
  "output": {
    "language": "zh-CN",
    "sections": {
      "official": {
        "title": "📌 官方动态",
        "max_items": 3,
        "description": "Anthropic 官方发布的更新、公告、博客"
      },
      "industry": {
        "title": "🏢 行业资讯",
        "max_items": 3,
        "description": "权威科技媒体的相关报道"
      },
      "tools": {
        "title": "🛠️ 工具推荐",
        "max_items": 3,
        "description": "实用的开源项目、插件、工具"
      },
      "community": {
        "title": "💡 社区精选",
        "max_items": 3,
        "description": "社区热门讨论和实用技巧"
      }
    }
  },
  "schedule": {
    "time": "10:00",
    "timezone": "Asia/Shanghai"
  },
  "feishu": {
    "chat_id": "oc_ed60c1bee04f5d29cdbce9f929eaf6f1",
    "chat_name": "Claude Code 每日资讯",
    "admin_user_id": "ou_e8baac7349338da94493c8db654d7227",
    "admin_user_ids": [
      "ou_e8baac7349338da94493c8db654d7227"
    ]
  },
  "quality": {
    "min_relevance_score": 0.6,
    "enable_ai_summary": true,
    "enable_value_comment": true,
    "enable_top_pick": true
  },
  "retry": {
    "max_retries": 2,
    "retry_delay": 3
  }
}
```

### 配置项说明

| 配置项 | 说明 |
|--------|------|
| `keywords` | 关键词列表，用于筛选相关资讯 |
| `sources` | 信息源配置，每个源可以单独启用/禁用 |
| `sources.*.reliability` | 可靠度：official（官方）、high（高）、medium（中） |
| `output.sections` | 输出板块配置 |
| `feishu.chat_id` | 飞书群 ID |
| `feishu.admin_user_ids` | 管理员 open_id 列表 |
| `retry.max_retries` | 采集失败最大重试次数 |

---

## 🐍 核心脚本说明

### 1. fetch_news.py - 资讯采集脚本

**功能：** 从多个信息源采集 Claude Code 相关资讯，输出结构化 JSON 数据。

**输出：** `raw_news_YYYYMMDD.json`

**数据结构：**
```python
@dataclass
class NewsItem:
    title: str              # 标题
    url: str                # 原文链接
    source: str             # 来源名称
    source_type: str        # 来源类型：official, media, community, tool, kol
    reliability: str        # 可靠度：official, high, medium
    summary: str = ""       # 摘要
    published_at: str = ""  # 发布时间
    score: int = 0          # 热度分数
    category: str = "community"  # 分类：official, industry, tools, community
```

**已实现的采集函数：**
| 函数 | 信息源 | 状态 | 说明 |
|------|--------|------|------|
| `fetch_anthropic_blog` | Anthropic 官方博客 | ✅ 正常 | 网页抓取（h4 标题匹配） |
| `fetch_claude_code_releases` | Claude Code Releases | ✅ 正常 | GitHub Releases Atom feed（官方变更日志） |
| `fetch_github_trending` | GitHub | ✅ 正常 | GitHub API 搜索 |
| `fetch_hackernews` | Hacker News | ✅ 正常 | Algolia 搜索 API（近 48h，一次请求） |
| `fetch_techcrunch` | TechCrunch | ✅ 正常 | RSS |
| `fetch_theverge` | The Verge | ✅ 正常 | RSS |
| `fetch_arstechnica` | Ars Technica | ✅ 正常 | RSS |
| `fetch_reddit` | Reddit | ✅ 正常 | RSS 端点 + 浏览器 UA（JSON API 已被封） |
| `fetch_v2ex` | V2EX | 🚫 已禁用 | 国内源，按需求禁用 |
| `fetch_twitter` | X (Twitter) | ✅ 正常 | twitterapi.io（主）+ nitter RSS（回退），19 个账号分 4 组 |
| `fetch_kol_blogs` | KOL 博客 | ✅ 正常 | RSS（当前含 Simon Willison） |

**X (Twitter) 账号分组：**
- **官方账号**（不做关键词过滤）：@AnthropicAI、@claudeai
- **Claude Code 核心团队**（不做关键词过滤）：@bcherny、@catwu、@trq212、@noahzweben、@amorriscode、@alexalbert__、@neilhtennek、@lydiahallie
- **Anthropic 创始人**（按关键词过滤）：@DarioAmodei、@DanielaAmodei、@jackclarkSF、@jaredkaplan
- **核心研究员**（按关键词过滤）：@karpathy、@sleepinyourhat、@ch402、@johnschulman2、@amandaaskell

推文只保留 `max_age_hours`（默认 36 小时）内的内容，自动跳过回复，nitter 链接转回 x.com 原始链接。

**X 采集途径（双通道）：**
1. **主途径：twitterapi.io**（第三方数据 API，按量计费约 $0.15/千条；本项目 19 个账号每日一拉约 380 条/天，月成本不到 2 美元）
   - 注册 https://twitterapi.io/ 获取 API Key
   - 把 Key 写入项目目录的 `.env` 文件（参考 `.env.example`）或环境变量 `TWITTERAPI_IO_KEY`
   - API 途径额外提供互动数据（点赞/转发），会作为热度加分（封顶 +20）
   - twitterapi.io 对低价套餐有 QPS 限流，代码内置 429 退避重试（最多 3 次），单账号重试后仍失败才回退 nitter
2. **回退途径：nitter RSS**（免费）：API 未配置或单账号失败时自动回退，实例列表见 `sources.twitter.nitter_instances`

**采集失败告警：** X 源全部账号采集失败（API 和 nitter 都不可用）、或部分失败且当日 0 条时，自动私信告警管理员，避免静默失效。

**重试机制：**
- 官方博客：重试 3 次（最高优先级）
- Claude Code Releases、GitHub、Hacker News、TechCrunch、The Verge、Ars Technica、KOL 博客：重试 2 次
- Reddit、X (Twitter)：重试 1 次（Twitter 内部已有多实例回退；Reddit 限流严格，子版之间间隔 5 秒）

**使用方式：**
```bash
python3 fetch_news.py
```

---

### 2. push_to_feishu.py - 飞书推送脚本

**功能：** 读取当天的资讯报告，推送到指定飞书群。

**核心函数：**
- `send_to_feishu(chat_id, content)` - 发送 markdown 消息
- `send_text_message(chat_id, text)` - 发送纯文本消息
- `send_alert_to_admin(admin_user_id, error_msg)` - 给管理员发失败告警

**失败告警：** 推送失败时，自动给管理员发私信提醒。

**使用方式：**
```bash
python3 push_to_feishu.py
```

**依赖：** 需要 `lark-cli` 命令可用。

---

### 3. bot_listener.py - 互动指令机器人

**功能：** 后台常驻运行，监听群消息，响应 `/资讯` 开头的指令。

**指令列表：**

| 指令 | 回复方式 | 权限 | 功能 |
|------|----------|------|------|
| `/资讯 帮助` | 群内回复 | 所有人 | 显示所有可用指令 |
| `/资讯 今日` | 群内回复 | 所有人 | 重新推送今天的资讯 |
| `/资讯 状态` | 群内回复 | 所有人 | 查看系统运行状态 |
| `/资讯 关键词` | 私信回复 | 所有人 | 查看当前关注的关键词 |
| `/资讯 关键词 +XXX` | 私信回复 | 仅管理员 | 增加关注关键词 |
| `/资讯 关键词 -XXX` | 私信回复 | 仅管理员 | 移除关注关键词 |

**核心机制：**
- 每 10 秒轮询一次群消息
- 每 1 分钟检查一次新成员
- 新成员入群自动发欢迎私信
- 状态保存在 `bot_state.json`

**使用方式：**
```bash
# 启动
./manage.sh start

# 停止
./manage.sh stop

# 重启
./manage.sh restart

# 查看状态
./manage.sh status

# 查看日志
./manage.sh logs
```

---

### 4. manage.sh - 运维管理脚本

**功能：** 一键管理机器人进程。

**命令：**
```bash
./manage.sh start    # 启动机器人
./manage.sh stop     # 停止机器人
./manage.sh restart  # 重启机器人
./manage.sh status   # 查看运行状态
./manage.sh logs     # 查看实时日志
```

**特性：**
- PID 文件管理（bot.pid）
- 日志文件（bot.log）
- 运行时长统计
- 强制停止机制（优雅停止失败后 kill -9）
- 彩色输出

---

### 5. test_sources.py - 信息源测试脚本

**功能：** 逐个测试所有信息源是否正常工作。

**使用方式：**
```bash
python3 test_sources.py
```

**输出：** 每个信息源的测试结果（成功/失败、耗时、获取数量、示例）

---

## 🚀 部署和运行

### 环境要求
- Python 3.10+
- 依赖包：requests, feedparser
- 飞书 CLI（lark-cli）已配置

### 安装依赖
```bash
pip3 install -r requirements.txt
```

### 手动运行
```bash
# 1. 采集资讯
python3 fetch_news.py

# 2. 整理报告（二选一）
#    首选：AI 整理（阅读 raw_news_*.json，生成带摘要/点评/TOP 1 的 news_*.md）
#    降级：模板化整理（无 AI 环境下保证链路可用）
python3 generate_report.py

# 3. 推送到飞书
python3 push_to_feishu.py
```

### 整理环节的两种模式

| 模式 | 执行者 | 质量 | 适用场景 |
|------|--------|------|---------|
| AI 整理 | `ai_report.py`（Cursor SDK 无头代理，需 `CURSOR_API_KEY`） | 高（摘要、点评、TOP 1 精选、择优） | 首选，Actions 中自动优先 |
| 降级整理 | `generate_report.py`（纯模板） | 基础（标题+链接+板块分类） | AI 不可用时自动兜底 |

### 编辑原则（两种模式共同遵守）
- **宁缺毋滥**：板块没有新内容就整个省略，不硬塞旧闻；TOP 1 仅在官方有真正重要内容时设置
- **择优**：内容超量时按重要性、时效性、影响面挑选（AI 模式），模板模式按分数排序取前 N
- **不重复**：已推送过的 URL 记录在 `seen_urls.json`（保留 60 天），后续采集自动过滤

### 定时任务设置

#### 方式一：GitHub Actions（推荐，零服务器成本）
- 配置文件：`.github/workflows/daily-news.yml`，每天 UTC 02:07（北京 10:07）自动运行，也可在 Actions 页面手动触发
- 触发时间特意避开整点：GitHub 在整点高峰可能延迟甚至丢弃 scheduled 任务（2026-08-05 实际踩坑：02:00 整的 cron 未被触发）
- 需要在仓库 **Settings → Secrets and variables → Actions** 配置 secret：
  - `LARK_APP_ID`：飞书应用 App ID（必需）
  - `LARK_APP_SECRET`：飞书应用 App Secret（必需）
  - `TWITTERAPI_IO_KEY`：twitterapi.io 的 API Key（必需）
  - `CURSOR_API_KEY`：Cursor API Key，用于 AI 整理（可选，缺省时自动降级模板整理）
- 优势：公开仓库 Actions 免费无限量；runner 在海外，所有海外信息源直连；全 bot 身份认证无需扫码，天然适配 CI
- 注意：Actions cron 有 3~15 分钟浮动；每次运行的 raw/news 产物会归档为 artifact 保留 14 天
- **限制：互动指令机器人（bot_listener）是常驻进程，无法跑在 Actions 上**，需要单独宿主（本机 manage.sh 或服务器 systemd）

#### 方式二：服务器 systemd（备选，配置见 deploy/）
```bash
# 服务器上 clone 仓库到 /opt/claude-news-bot 后：
sudo bash deploy/setup.sh
# 会安装依赖、注册 systemd timer（每天 10:00 北京时间）和互动机器人常驻服务
```

部署前置条件（setup.sh 会检查并提示）：
1. `lark-cli` 已安装，`config init` 完成，且用户身份有 `im:message.send_as_user` scope
2. `.env` 已配置 `TWITTERAPI_IO_KEY`
3. 部署后运行 `python3 test_sources.py` 复测所有信息源连通性

#### 方式三：豆包定时任务（已于 2026-08-04 停用）
- 曾经的方式：每天 10:00 触发，由 AI 执行完整流程（采集 → AI 整理 → 推送）
- 已被 GitHub Actions 替代并暂停；如需恢复可在豆包对话中说"恢复定时任务"

### 互动机器人后台运行
```bash
# 服务器（systemd，随 setup.sh 自动注册，崩溃自动重启、开机自启）
systemctl status claude-news-bot

# 本地/手动模式
./manage.sh start
```

---

## 📊 当前状态

### ✅ 正常运行的功能
- 每日定时推送（豆包定时任务）
- 10 个可用信息源（2026-08-04 实测验证）：
  - Anthropic 官方博客
  - Claude Code Releases（GitHub Atom feed）
  - GitHub
  - Hacker News（Algolia API）
  - TechCrunch
  - The Verge
  - Ars Technica
  - Reddit（RSS 端点）
  - X (Twitter)（nitter.net，19 个账号）
  - Simon Willison 博客
- AI 智能整理（摘要、点评、TOP 1）
- 飞书群推送
- 失败告警

### ⚠️ 注意事项
- **X (Twitter)**：主途径 twitterapi.io 需要配置 API Key（见 `.env.example`），未配置时回退 nitter RSS；nitter 可用实例只有 nitter.net 和 nitter.perennialte.ch 两个，全部失效时会触发管理员告警；@neilhtennek 的 RSS 在两个 nitter 实例上都是 404（账号受限，网页版正常），配置 API Key 后可正常采集
- **Reddit**：JSON API 已被封，RSS 可用但限流严格（429），已加 30 秒退避重试

### 🚫 已禁用/暂停的功能
- **V2EX**：国内源，按需求禁用
- **互动指令机器人**：暂不启用（代码保留在 `bot_listener.py`，需要时 `./manage.sh start` 启动；推送消息中已移除指令相关提示文案）

---

## 🔧 已知问题和注意事项

### 1. 网络与采集途径
- Hacker News 改用 Algolia 搜索 API、Reddit 改用 RSS 端点、X 改用 nitter.net RSS 后，全部信息源在当前网络环境下实测可用（2026-08-04）
- X 采集依赖 nitter.net 单一实例，若失效需寻找新实例（配置 `sources.twitter.nitter_instances` 支持多实例回退，代码会逐个尝试）
- 部署环境变化后建议先跑 `python3 test_sources.py` 复测

### 2. Anthropic 官方博客采集
- RSS 地址不可用，已改为网页抓取
- 使用 h4 标题匹配，可能会随网站结构变化而失效
- 建议：定期检查采集是否正常

### 3. 互动机器人进程管理
- 当前用 nohup 后台运行
- VM 重启或会话结束后进程会停止
- 建议：生产环境使用 systemd 或 supervisor 管理

### 4. 飞书 CLI 依赖与身份策略
- 推送功能依赖 `lark-cli` 命令，不同环境需要单独配置飞书认证
- **身份策略（v2.6 起）**：所有 lark-cli 调用（读+写）均走 **bot 身份**（`--as bot`），只依赖 App ID + Secret，不依赖任何个人用户授权，服务器无人值守可靠；消息以机器人名义发送
- 前置条件：lark-cli 应用的机器人已加入目标群（本群已加入），且应用已开通 bot 的收发消息、查看群成员等权限（已开通）
- 注意：open_id 是按应用签发的，更换 lark-cli 应用后需重新解析 `feishu.admin_user_ids`（用 `lark-cli im +chat-members-list` 查群成员即可）

### 5. 消息轮询延迟
- 互动指令使用轮询方式，每 10 秒检查一次
- 指令回复有最多 10 秒延迟，属于正常现象

---

## 🎯 后续优化方向

### 高优先级
1. **配置 twitterapi.io API Key**（注册后写入 `.env`，X 采集即切换到主途径）

2. **提升部署稳定性**
   - 部署到独立服务器
   - 使用 systemd 管理进程
   - 开机自启、崩溃自动重启

### 中优先级
3. **内容质量优化**
   - 质量评分机制
   - 更智能的筛选和排序
   - 个性化推荐

4. **更多互动指令**
   - `/资讯 搜索 关键词` - 搜索历史资讯
   - `/资讯 周报` - 生成周报
   - `/资讯 月报` - 生成月报

5. **数据看板**
   - 统计资讯数量、来源分布
   - 热门话题趋势
   - 用户活跃度

### 低优先级
6. **多群支持**
   - 支持推送到多个飞书群
   - 不同群不同的关键词配置

7. **用户个性化订阅**
   - 用户可以自定义关注的关键词
   - 私信推送个性化内容

8. **配置后台**
   - Web 界面管理配置
   - 可视化的信息源管理

---

## 🔑 关键 ID 和配置

### 飞书相关
- **群名称**：Claude Code 每日资讯
- **群 Chat ID**：oc_ed60c1bee04f5d29cdbce9f929eaf6f1
- **群链接**：（公开仓库不放邀请链接，入群请联系管理员）
- **lark-cli 应用**：畅涛's Feishu CLI（App ID: cli_aafa3defaf389bef，机器人已入群）
- **管理员 open_id**：ou_ec49eba4f8ac4c6d7d799e04929c65e6（本应用签发；旧值 ou_e8baac73... 属豆包应用，已作废）
- **管理员邮箱**：changtao@vastai3d.com

### 定时任务
- **当前方式**：GitHub Actions（`.github/workflows/daily-news.yml`，每天北京时间 10:00）
- **豆包旧任务**：Claude Code 每日资讯推送（任务 ID 11314484045058），已于 2026-08-04 停用

---

## 📝 版本历史

### v2.7 (当前版本)
- AI 整理接入 Cursor SDK 无头代理（`ai_report.py`，Actions 中优先执行，失败自动降级模板）
- 新增已推送记录去重（`seen_urls.json` + `mark_seen.py`）：不重复推送旧闻，宁缺毋滥
- 修复官博标题-链接错配 bug（正则跨卡片匹配导致）
- TOP 1 仅在官方板块有新内容时设置，不再全局兜底
- 互动指令机器人暂停启用，推送文案移除指令提示

### v2.6
- 飞书调用全面切换为 bot 身份（`--as bot`，读+写）：只依赖 App ID + Secret，零个人授权依赖，服务器部署可靠，消息以机器人名义发送
- lark-cli 机器人已加入资讯群；管理员 open_id 更新为本应用签发的新值
- 应用版本 1.0.2 已发布，bot 读写 scope 均已生效（实测验证）

### v2.5
- X 采集改为双通道：twitterapi.io API 优先（API Key 走 `.env`/环境变量，未配置自动回退 nitter）
- API 途径带互动数据（点赞/转发）作为热度加分
- 新增采集失败告警：X 源全部失败或可疑 0 条时私信管理员
- 新增备用 nitter 实例 nitter.perennialte.ch（实测 18 个社区实例中唯一可用的备用）
- 新增 `.env.example`

### v2.4
- 信息源大修（2026-08-04，全部实测验证）：
  - X (Twitter)：RSSHub（失效）→ nitter.net RSS；账号从 4 个扩充到 19 个，分 4 组（官方/核心团队/创始人/研究员），官方和核心团队不做关键词过滤
  - Hacker News：Firebase 逐条抓取 → Algolia 搜索 API（一次请求覆盖近 48h）
  - Reddit：JSON API（已被封）→ RSS 端点 + 浏览器 UA
  - 新增 Claude Code Releases（GitHub Atom feed，官方变更日志）
  - 新增 KOL 博客源（Simon Willison）
  - 禁用 V2EX（国内源），移除无实现的 official_docs 配置
  - 推文增加时间窗口过滤（36h）、跳过回复、nitter 链接转回 x.com

### v2.3
- 增加 X (Twitter) 信息源配置（4 个账号）
- 优化 Anthropic 官方博客抓取（RSS → 网页抓取）
- 增加信息源测试脚本

### v2.2
- 增加新成员欢迎功能
- 增加权限控制（管理员才能改配置）
- 增加运维管理脚本（manage.sh）

### v2.1
- 增加采集重试机制
- 优化错误处理

### v2.0
- 增加权威科技媒体源（TechCrunch、The Verge、Ars Technica）
- 增加 AI 深度整理（摘要、点评、TOP 1）
- 增加失败告警功能
- 配置文件大升级

### v1.0
- 初始版本
- 5 个信息源：官方博客、GitHub、Hacker News、Reddit、V2EX
- 基础采集和推送功能
- 飞书群创建
- 定时任务设置

---

## 📞 交接说明

### 给下一个 AI 的建议
1. **先跑通现有功能**：确保采集和推送都正常
2. **阅读代码**：重点看 `config.json` 和 `fetch_news.py`
3. **测试信息源**：运行 `test_sources.py` 了解当前状态
4. **从小处开始优化**：不要一上来就大改
5. **保持向后兼容**：修改配置时注意兼容旧版本

### 常见问题排查
1. **推送失败**：检查 lark-cli 是否配置正确，网络是否通
2. **采集 0 条**：检查信息源是否能访问，关键词是否合适
3. **机器人不响应**：检查进程是否在运行，日志有没有报错
4. **定时任务没触发**：检查定时任务配置，时区是否正确

---

## 📚 参考资料

- 飞书开放平台文档：https://open.feishu.cn/
- lark-cli 使用说明：飞书命令行工具
- GitHub API 文档：https://docs.github.com/en/rest
- RSSHub 文档：https://docs.rsshub.app/

---

**最后更新：2026-08-04（v2.5 X 双通道采集 + 失败告警）**
**维护者：畅涛 (changtao@vastai3d.com)**
