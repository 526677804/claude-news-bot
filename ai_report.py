#!/usr/bin/env python3
"""
AI 整理脚本（首选整理方式）
通过 Cursor SDK 的无头代理阅读 raw_news_YYYYMMDD.json，
撰写带摘要、点评和 TOP 1 精选的高质量日报 news_YYYYMMDD.md。

需要环境变量 CURSOR_API_KEY（Cursor Dashboard → Integrations 生成）。
未配置或执行失败时退出非 0，由调用方降级到 generate_report.py（模板整理）。
"""

import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def build_prompt(today: str) -> str:
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
- 每条格式：**加粗标题**（英文标题翻译成中文或保留原文均可，以可读为准）+ 一句话摘要/点评（说清楚"这条为什么值得看"）+ 🔗 来源链接（原样保留，不得改动 URL）
- 语言：简体中文，简洁专业，适合技术和非技术读者
- 事实必须来自 JSON 数据，不得编造内容或链接
- **如果 JSON 的 items 为空，或没有任何值得推送的内容，不要创建 news 文件**，直接结束并说明原因（当天将跳过推送）

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

    print('🤖 启动 Cursor 无头代理进行 AI 整理...')
    try:
        result = Agent.prompt(
            build_prompt(today),
            AgentOptions(
                api_key=api_key,
                model='auto',
                local=LocalAgentOptions(cwd=BASE_DIR),
            ),
        )
        if result.status != 'finished':
            print(f'❌ AI 整理运行失败: status={result.status}')
            sys.exit(2)
    except CursorAgentError as e:
        print(f'❌ AI 代理启动失败: {e}')
        sys.exit(1)

    # 无新内容时 AI 按约定不生成文件，属正常跳过（区别于生成失败）
    import json
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
