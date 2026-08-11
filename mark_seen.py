#!/usr/bin/env python3
"""
已推送记录维护脚本
在推送成功后运行：
1. 把当天采集到的所有 URL 记入 seen_urls.json（保留 60 天），后续采集自动过滤，
   保证不重复推送旧闻（宁缺毋滥原则）；
2. 把当天日报的条目标题记入 recent_topics.json（保留 7 天），供 AI 整理做
   跨天事件去重——同一事件不同渠道的连日跟进报道，URL 不同拦不住，靠这份
   标题清单让 AI 在语义层判断。
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(BASE_DIR, 'seen_urls.json')
RETENTION_DAYS = 60

TOPICS_FILE = os.path.join(BASE_DIR, 'recent_topics.json')
# 跨天事件去重的记忆窗口：覆盖新闻跟进周期即可，不宜超过 RETENTION_DAYS（60 天）
TOPICS_RETENTION_DAYS = 7


def extract_report_titles(report_path: str) -> list:
    """从日报 markdown 提取条目标题（独立成行的 **加粗** 文本，去掉序号前缀）"""
    titles = []
    with open(report_path, 'r', encoding='utf-8') as f:
        for line in f:
            m = re.match(r'^\*\*(.+?)\*\*$', line.strip())
            if not m:
                continue
            title = re.sub(r'^\d+[.、]\s*', '', m.group(1)).strip()
            if title:
                titles.append(title)
    return titles


def update_recent_topics(today: str) -> int:
    """把当天日报的条目标题记入 recent_topics.json，返回新增条数"""
    topics = {'updated_at': '', 'days': {}}
    if os.path.exists(TOPICS_FILE):
        try:
            with open(TOPICS_FILE, 'r', encoding='utf-8') as f:
                topics = json.load(f)
        except Exception:
            pass

    cutoff = (datetime.now() - timedelta(days=TOPICS_RETENTION_DAYS)).strftime('%Y%m%d')
    days = {d: t for d, t in topics.get('days', {}).items() if d >= cutoff}

    added = 0
    report_file = os.path.join(BASE_DIR, f'news_{today}.md')
    if os.path.exists(report_file):
        titles = extract_report_titles(report_file)
        if titles:
            days[today] = titles
            added = len(titles)

    topics['days'] = days
    topics['updated_at'] = datetime.now().isoformat()
    with open(TOPICS_FILE, 'w', encoding='utf-8') as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)
    return added


def main():
    today = datetime.now().strftime('%Y%m%d')
    raw_file = os.path.join(BASE_DIR, f'raw_news_{today}.json')

    if not os.path.exists(raw_file):
        print(f"❌ 找不到 {raw_file}")
        sys.exit(1)

    with open(raw_file, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    seen = {'updated_at': '', 'urls': {}}
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r', encoding='utf-8') as f:
                seen = json.load(f)
        except Exception:
            pass

    urls = seen.get('urls', {})

    # 清理超过保留期的记录
    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime('%Y%m%d')
    urls = {u: d for u, d in urls.items() if d >= cutoff}

    added = 0
    for item in raw.get('items', []):
        url = item.get('url', '')
        if url and url not in urls:
            urls[url] = today
            added += 1

    seen['urls'] = urls
    seen['updated_at'] = datetime.now().isoformat()

    with open(SEEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)

    print(f"✅ 已推送记录更新：新增 {added} 条，总计 {len(urls)} 条（保留 {RETENTION_DAYS} 天）")

    added_titles = update_recent_topics(today)
    if added_titles:
        print(f"✅ 跨天去重记录更新：记入当日 {added_titles} 个条目标题（保留 {TOPICS_RETENTION_DAYS} 天）")
    else:
        print("ℹ️ 今日无日报，跨天去重记录仅做过期清理")


if __name__ == '__main__':
    main()
