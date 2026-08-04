#!/usr/bin/env python3
"""
资讯报告生成脚本（降级模式）
从 raw_news_YYYYMMDD.json 生成 news_YYYYMMDD.md

生产环境的首选整理方式是 AI（阅读原始 JSON 后撰写摘要、点评、TOP 1），
本脚本是无 AI 环境下的兜底方案：按配置的板块结构做模板化整理，
保证服务器上的定时任务链路（采集 → 整理 → 推送）始终可用。
"""

import json
import os
import sys
from datetime import datetime


def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_item(index: int, item: dict) -> str:
    lines = [f"**{index}. {item['title'].strip()}**"]
    summary = (item.get('summary') or '').strip()
    if summary and summary != '官方发布':
        lines.append(summary[:150])
    lines.append(f"🔗 {item['url']}")
    return '\n'.join(lines)


def main():
    config = load_config()
    today = datetime.now().strftime('%Y%m%d')
    raw_file = os.path.join(os.path.dirname(__file__), f'raw_news_{today}.json')

    if not os.path.exists(raw_file):
        print(f"❌ 找不到原始数据: {raw_file}，请先运行 fetch_news.py")
        sys.exit(1)

    with open(raw_file, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    categorized = raw.get('categorized', {})
    sections = config.get('output', {}).get('sections', {})
    date_str = datetime.now().strftime('%Y-%m-%d')

    parts = [f"# 📰 Claude Code 每日资讯 · {date_str}"]

    # TOP 1：官方分类中分数最高的一条，没有官方内容时取全局最高分
    top_pool = categorized.get('official') or raw.get('items') or []
    if top_pool:
        top = max(top_pool, key=lambda x: x.get('score', 0))
        parts.append(
            f"\n## 🏆 今日 TOP 1\n\n**{top['title'].strip()}**\n🔗 {top['url']}"
        )

    for cat_key, section in sections.items():
        items = categorized.get(cat_key, [])
        if not items:
            continue
        max_items = section.get('max_items', 3)
        parts.append(f"\n---\n\n## {section['title']}")
        for i, item in enumerate(items[:max_items], 1):
            parts.append('\n' + format_item(i, item))

    parts.append(
        f"\n---\n\n📊 本期数据：采集 {raw.get('total_count', 0)} 条资讯"
        f"\n🤖 由 Claude Code 资讯机器人自动生成 · 发送 /资讯 帮助 查看指令"
    )

    output_file = os.path.join(os.path.dirname(__file__), f'news_{today}.md')
    content = '\n'.join(parts)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ 报告已生成: {output_file}（{len(content)} 字符）")


if __name__ == '__main__':
    main()
