#!/usr/bin/env python3
"""
AI 整理脚本（首选整理方式）
通过 Cursor SDK 的无头代理阅读 raw_news_YYYYMMDD.json，
撰写带摘要、点评和 TOP 1 精选的高质量日报 news_YYYYMMDD.md。

需要环境变量 CURSOR_API_KEY（Cursor Dashboard → Integrations 生成）。
未配置或执行失败时退出非 0，由调用方降级到 generate_report.py（模板整理）。
代理运行失败（如 status=error 的瞬时故障）会自动重试一次，重试仍失败才降级，
并输出运行 ID、时长、结果文本等细节便于排障（2026-08-12 首次线上失败仅有
status=error 一行可查，教训）。
"""

import json
import os
import sys
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MAX_ATTEMPTS = 2      # 共尝试次数（1 次正式 + 1 次重试）
RETRY_DELAY = 30      # 重试前等待秒数


def describe_result(result) -> str:
    """把 SDK 运行结果的关键信息拼成一行，供失败排障"""
    parts = [f"status={getattr(result, 'status', '?')}"]
    for attr in ('id', 'agent_id', 'duration_ms', 'model'):
        value = getattr(result, attr, None)
        if value:
            parts.append(f'{attr}={value}')
    text = (getattr(result, 'result', '') or '').strip()
    if text:
        parts.append(f'result={text[:500]}')
    return ' | '.join(parts)


def load_recent_topics(today: str) -> str:
    """读取近几日已推送的条目标题（mark_seen.py 维护），拼成 prompt 参考块"""
    path = os.path.join(BASE_DIR, 'recent_topics.json')
    if not os.path.exists(path):
        return ''
    try:
        with open(path, 'r', encoding='utf-8') as f:
            days = json.load(f).get('days', {})
    except Exception:
        return ''
    lines = []
    for d in sorted(days, reverse=True):
        if d >= today:  # 同日重跑时不把当天条目当历史
            continue
        for title in days[d]:
            lines.append(f'- [{d[:4]}-{d[4:6]}-{d[6:]}] {title}')
    return '\n'.join(lines)


def build_prompt(today: str, recent_block: str = '') -> str:
    dedup_rule = ''
    dedup_section = ''
    if recent_block:
        dedup_rule = """
- **跨天不重复**：文末「近几日已推送」清单中已报道过的事件，仅当今天出现实质性新进展\
（如官方正式发布、生效时间或范围变更、重要数据更新）时才可再次出现，且点评中必须注明是进展跟进\
（例如"此前 8 月 9 日已报道，今日官方正式公告落地"）；无实质增量则整条跳过（宁缺毋滥）。\
同一事件原则上最多登上一次 TOP 1，官方正式公告日可作为例外再上一次。"""
        dedup_section = f"""
## 近几日已推送（跨天去重参考，判断"事件是否已报道过"以此为准）
{recent_block}
"""
    return f"""你是「Claude Code 每日资讯」的编辑。请阅读本目录下的 raw_news_{today}.json（当天采集的原始资讯数据），\
撰写一份中文日报，写入文件 news_{today}.md（UTF-8，Markdown 格式，用于飞书群推送）。

## 输出结构（按顺序）
1. 标题行：`# 📰 Claude Code 每日资讯 · {datetime.now().strftime('%Y-%m-%d')}`
2. `## 🏆 今日 TOP 1`：全场最重要的一条（通常来自官方动态），给出 2-3 句点评说明为什么重要
3. `## 📌 官方动态`：Anthropic 官方发布、Claude Code 版本更新（最多 3 条）
4. `## 🏢 行业资讯`：权威科技媒体报道（最多 3 条）
5. `## 🛠️ 工具推荐`：开源项目、插件、工具（最多 3 条）
6. `## 💡 社区精选`：KOL 推文、博客、社区热帖（最多 3 条）
7. 页脚：`📊 本期数据：采集 N 条资讯`（N 取 JSON 里的 total_count）+ `🤖 由 Claude Code 资讯机器人自动生成（AI 整理）`

## 编辑原则（严格遵守）
- **宁缺毋滥**：某板块没有值得推荐的内容就整个省略该板块，绝不硬塞；TOP 1 只在确有重要内容时设置
- **择优**：板块内容超过 3 条时按重要性、时效性、影响面挑选，不是按分数机械排序
- **同一事件全报告只出现一次（最重要的规则之一）**：
  - 不同渠道报道同一件事（如官博发布 + 媒体报道 + 社区讨论 + KOL 推文都在说同一个新版本/新模型）时，只保留一条，放进最合适的板块，来源链接选最权威的（官方 > 媒体 > 社区）；如次要渠道有独特价值（如深度评测），可在该条摘要里一笔带过
  - 被选为 TOP 1 的内容，不得再出现在下方任何板块
  - 各板块之间不得出现同一事件的重复条目{dedup_rule}
- 每条格式：**加粗标题**（英文标题翻译成中文或保留原文均可，以可读为准）+ 一句话摘要/点评（说清楚"这条为什么值得看"）+ 🔗 来源链接（原样保留，不得改动 URL）
- 语言：简体中文，简洁专业，适合技术和非技术读者
- 事实必须来自 JSON 数据，不得编造内容或链接
- **如果 JSON 的 items 为空，或没有任何值得推送的内容，不要创建 news 文件**，直接结束并说明原因（当天将跳过推送）
{dedup_section}
只创建/覆盖 news_{today}.md 这一个文件，不要修改任何其他文件。"""


def main():
    api_key = os.environ.get('CURSOR_API_KEY', '')
    if not api_key:
        print('⚠️ 未配置 CURSOR_API_KEY，跳过 AI 整理')
        sys.exit(3)

    today = datetime.now().strftime('%Y%m%d')
    raw_file = os.path.join(BASE_DIR, f'raw_news_{today}.json')
    out_file = os.path.join(BASE_DIR, f'news_{today}.md')

    if not os.path.exists(raw_file):
        print(f'❌ 找不到原始数据 {raw_file}')
        sys.exit(1)

    from cursor_sdk import Agent, AgentOptions, LocalAgentOptions, CursorAgentError

    recent_block = load_recent_topics(today)
    if recent_block:
        print(f'🧠 已注入近几日推送记忆（{len(recent_block.splitlines())} 个条目标题）')

    print('🤖 启动 Cursor 无头代理进行 AI 整理...')
    result = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = Agent.prompt(
                build_prompt(today, recent_block),
                AgentOptions(
                    api_key=api_key,
                    model='auto',
                    local=LocalAgentOptions(cwd=BASE_DIR),
                ),
            )
            if result.status == 'finished':
                break
            print(f'❌ AI 整理运行失败（第 {attempt}/{MAX_ATTEMPTS} 次）: {describe_result(result)}')
        except CursorAgentError as e:
            result = None
            print(f'❌ AI 代理启动失败（第 {attempt}/{MAX_ATTEMPTS} 次）: {e!r}')
        if attempt < MAX_ATTEMPTS:
            print(f'⏳ {RETRY_DELAY} 秒后重试...')
            time.sleep(RETRY_DELAY)

    if result is None or result.status != 'finished':
        # 放弃前清掉失败运行可能留下的半成品，避免被当作有效报告推送
        if os.path.exists(out_file):
            os.remove(out_file)
        sys.exit(2)

    # 无新内容时 AI 按约定不生成文件，属正常跳过（区别于生成失败）
    with open(raw_file, 'r', encoding='utf-8') as f:
        has_items = bool(json.load(f).get('items'))
    if not os.path.exists(out_file):
        if not has_items:
            print('ℹ️ 今日无新增资讯，AI 按约定跳过报告生成')
            sys.exit(0)
        print('❌ AI 未生成报告文件')
        sys.exit(2)
    content = open(out_file, 'r', encoding='utf-8').read()
    if len(content) < 200 or 'Claude Code 每日资讯' not in content:
        print('❌ AI 生成的报告内容不完整')
        sys.exit(2)

    print(f'✅ AI 整理完成: {out_file}（{len(content)} 字符）')


if __name__ == '__main__':
    main()
