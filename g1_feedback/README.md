# G1 内测反馈收录管线

把飞书群「G1 - 联创团队」里和产品相关的讨论，自动整理成需求池（飞书多维表格）里的记录，并回群通报。

- 需求池：https://a9ihi0un9c.feishu.cn/wiki/AFw6wE6HUimR9Ak2LdYcWadcnJZ （知识库「内部业务 / 游戏」下）
- 调度：每天北京时间 18:30，由妙搭应用「资讯推送定时触发器」（`app_17bkc5gs27u`）的 cron 触发器 `g1FeedbackGithubTrigger` 调 `workflow_dispatch`——与日报、AI 一千零一夜同一套（handler 在该应用 `server/modules/github-trigger/github-trigger.automation.ts`，复用 `GITHUB_TRIGGER_TOKEN`）；工作流自带的 GitHub cron 作备份（可能延迟数小时）；也可手动 `workflow_dispatch` 或群里 @机器人
- 身份：全链路机器人「畅涛's Homunculus」（`--as bot`），只依赖仓库 Secrets 里的 `LARK_APP_ID` / `LARK_APP_SECRET`；AI 提取用 `CURSOR_API_KEY`

## 四步

| 步骤 | 脚本 | 做什么 |
|------|------|--------|
| 1 拉取 | `fetch.py` | 从水位（`state.json`）起增量拉群消息，过滤系统消息 / 表情 / 撤回 / 机器人自己的消息 / 已处理过的；展开话题回复；下载图片供 AI 读图；读出需求池现有记录 → `runs/<run>/input.json` |
| 2 提取 | `extract.py` | Cursor SDK 无头代理阅读 input.json，只保留产品相关内容，合并同一话题，判断是新记录还是旧记录的后续讨论 → `output.json`（有校验，失败自动重试一次） |
| 3 写入 | `write.py` | 新记录 `+record-batch-create`；追加讨论 / 附议者 `+record-upsert`；更新水位；生成回群消息 `post.md` |
| 4 回群 | `post.py` | 以机器人身份把 `post.md` 发到群里（@提出者）；失败私信管理员 |

工作流失败（任一步非 0）会私信管理员一条带运行链接的告警。每次运行的 input / output / post 以 artifact 保留 30 天。

## 手动触发（群里 @机器人）

除了每天 18:30，群里任何人 **@畅涛's Homunculus 记一下**（或「整理」「记录」）就会立刻跑一次；管理员在机器人私聊里直接发「记一下」也行；发「状态」看最近一次运行，「帮助」看用法。

- 实现：`listener.py` 常驻在负责人的 Mac 上（launchd，每 45 秒轮询群消息），发现触发消息后回一句「收到」，并用 `gh workflow run` 派发同一条 Actions 管线（`manual=true`，`reply_to=触发消息`），结果以回复触发消息的方式回群。
- **回群规则**：每日定时和私聊触发，只有新增了记录才回群；只追加到已有记录、或什么都没提取到，都静默处理（追加照样写进需求池）。群里 @ 触发无论结果都回复触发消息：有新增发汇总；只追加回一句「已并入哪几条、新增了哪些附议者」并附需求池链接；没提取到、没有新消息、运行失败也各回一句（试运行 dry_run 一律不回）。
- 每日 18:30 由妙搭触发器准点派发（见上）；`config.json` 的 `daily_time` 留空即表示本机不再派发每日任务（填 `18:30` 可切回本机派发）。GitHub 自己的 cron 只作备份——实测高峰期会晚 4–5 小时才跑（2026-10-23 的 18:30 任务 23:17 才执行）。多处触发跑的都是同一条管线、同一份水位，重复触发只会「没有新内容」而不会重复记录。
- 要让 @ 触发也不依赖 Mac：`trigger-worker/` 是现成的 Cloudflare Worker（接飞书事件订阅 → 调 `workflow_dispatch`，并可兼做 18:30 定时），部署步骤见该目录内注释；部署后把本机监听器 `launchctl bootout` 掉即可。
- 不会重复：手动和定时跑的是同一条管线、同一份水位（`state.json`，每次运行后写回仓库），且工作流设了 `concurrency: g1-feedback`，两次运行只会排队不会并行；后一次会看到前一次推进过的水位。3 分钟内连续 @ 只派发一次。
- Mac 睡眠时 @ 不会立即响应；醒来后 2 小时内的触发会补跑，更早的忽略（反正每日定时会兜底）。
- 安装 / 重启监听器（Mac 上执行一次）：

```bash
# 检出必须在 ~/Documents 之外（macOS 不允许后台进程读 Documents）
git clone https://github.com/526677804/claude-news-bot.git ~/.local/share/claude-news-bot
cp ~/.local/share/claude-news-bot/g1_feedback/com.changtao.g1-feedback-listener.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.changtao.g1-feedback-listener.plist
tail -f ~/.local/share/claude-news-bot/g1_feedback/runs/listener.log
# 停止：launchctl bootout gui/$(id -u)/com.changtao.g1-feedback-listener
```

监听器每次启动会先 `git pull`，所以改了 `config.json` / `listener.py` 推到仓库后，`launchctl kickstart -k gui/$(id -u)/com.changtao.g1-feedback-listener` 重启一下即可生效。依赖本机已登录的 `lark-cli`（bot 身份）和 `gh`。

## 需求池字段

智能体填：需求 / 问题、为了解决什么、类型（新需求 / 体验问题 / Bug / 疑问 / 流程 / 信号）、涉及模块、产品（G1 / G2 / 其他）、提出者、附议者、提出时间、原文链接、讨论摘要、初步建议（直接做 / 需探讨 / 待确认）、来源 message_id（去重用）。

人填：状态（待筛选 / 讨论中 / 直接做 / 已排期 / 已完成 / 不做）、第一性原理（根本问题）、最终方案、负责人。

## 本地运行

```bash
cd g1_feedback
python3 fetch.py --since 2026-10-22 --run runs/test --as bot --base-as user   # 机器人缺 Base 权限时可用 user 读需求池
CURSOR_API_KEY=... python3 extract.py --run runs/test
python3 write.py --run runs/test --as user --dry-run                            # 只打印，不写
python3 write.py --run runs/test --as user                                      # 真写 + 更新水位 + 生成 post.md
python3 post.py --run runs/test                                                  # 回群（始终 bot 身份）
```

`runs/` 已在 `.gitignore`；`state.json` 是水位，由 Actions 自动提交回仓库，手动本地写入后记得一并提交。

## 机器人需要的权限（开发者后台）

- 飞书群：机器人必须在群里（已于 2026-10-23 拉入）；读历史消息 `im:message:readonly`、发消息 `im:message:send_as_bot`
- 多维表格：`base:table:read`、`base:field:read`、`base:record:read`、`base:record:create`、`base:record:update`；并且机器人已被加为该 Base 的「可编辑」协作者
- 缺权限时 lark-cli 会返回 `missing_scopes` 和 `console_url`，到开发者后台申请并发布版本即可

## 调整

- 换群 / 换表：改 `config.json` 的 `chat_id`、`base_token`、`table_id`、`pool_url`
- 不回群：`post_to_group` 设为 `false`
- 回群最多列几条：`max_lines_in_post`
- 重新处理某一段：手动触发 workflow 并填 `since`；注意已处理过的 message_id 仍会被水位过滤，必要时先清空 `state.json` 的 `processed_ids`
- 提取规则（什么算需求、怎么合并、怎么判断初步建议）都在 `extract.py` 的 `build_prompt()` 里
