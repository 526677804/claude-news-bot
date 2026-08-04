#!/usr/bin/env python3
"""
已推送记录维护脚本
在推送成功后运行：把当天采集到的所有 URL 记入 seen_urls.json，
后续采集会自动过滤这些内容，保证不重复推送旧闻（宁缺毋滥原则）。
记录保留 60 天后自动清理。
"""

import json
import os
import sys
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(BASE_DIR, 'seen_urls.json')
RETENTION_DAYS = 60


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


if __name__ == '__main__':
    main()
