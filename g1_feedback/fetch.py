#!/usr/bin/env python3
"""
第 1 步：增量拉取 G1 内测群消息 + 需求池现有记录，整理成 input.json 交给 AI 提取。

- 起点：--since 参数 > state.json 的 last_message_time > config.initial_since
- 过滤：系统消息、表情包、已撤回、机器人自己发的、上次已处理过的 message_id
- 话题回复：有 thread_id 的消息会展开其回复
- 图片 / 文件：随消息下载到 <run>/lark-im-resources/，供 AI 读图
- 现有记录：从需求池读出（供 AI 判断「这是新需求还是旧需求的后续讨论」）

用法：python3 fetch.py [--since 2026-10-22] [--run runs/xxx] [--as bot|user] [--no-images] [--allow-no-base]
退出码：0 正常（即使没有新消息）；非 0 为硬错误
"""

import argparse
import os
import sys
from datetime import datetime

from common import (CST, RUNS_DIR, LarkError, cst_text_to_iso, github_output, lark, load_config,
                    load_state, now_cst, rows_to_dicts, save_json)

SKIP_TYPES = {'system', 'sticker', 'share_chat', 'share_user'}
RECORD_FIELDS = ['编号', '需求 / 问题', '为了解决什么', '类型', '状态', '提出者', '附议者', '来源 message_id', '提出时间']


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--since', help='起始时间（YYYY-MM-DD 或 YYYY-MM-DD HH:MM，北京时间）；不传则用水位')
    p.add_argument('--run', help='本次运行目录；默认 runs/<时间戳>')
    p.add_argument('--as', dest='identity', default=os.environ.get('LARK_AS', 'bot'), choices=['bot', 'user'])
    p.add_argument('--base-as', dest='base_identity', default=None, choices=['bot', 'user'],
                   help='读需求池用的身份；默认与 --as 相同')
    p.add_argument('--no-images', action='store_true', help='不下载图片 / 文件')
    p.add_argument('--allow-no-base', action='store_true', help='需求池读取失败时继续（仅用于 dry-run）')
    return p.parse_args()


def normalize(msg, run_dir, thread_of=None):
    sender = msg.get('sender') or {}
    item = {
        'id': msg.get('message_id'),
        'time': msg.get('create_time'),
        'sender': sender.get('name') or sender.get('id'),
        'sender_id': sender.get('id'),
        'type': msg.get('msg_type'),
        'text': msg.get('content') if isinstance(msg.get('content'), str) else str(msg.get('content')),
        'link': msg.get('message_app_link'),
    }
    if msg.get('reply_to'):
        item['reply_to'] = msg['reply_to']
    if thread_of:
        item['thread_of'] = thread_of
    if msg.get('mentions'):
        item['mentions'] = [{'name': m.get('name'), 'id': m.get('id')} for m in msg['mentions']]
    images, files = [], []
    for r in msg.get('resources') or []:
        if r.get('error') or not r.get('local_path'):
            continue
        rel = os.path.relpath(r['local_path'], run_dir)
        (images if r.get('type') == 'image' else files).append(rel)
    if images:
        item['images'] = images
    if files:
        item['files'] = files
    return item


def fetch_messages(cfg, identity, start_iso, run_dir, with_images):
    raw = []
    page_token = ''
    for _ in range(200):  # 每页 50，上限 1 万条，足够
        args = ['im', '+chat-messages-list', '--chat-id', cfg['chat_id'], '--start', start_iso,
                '--order', 'asc', '--page-size', '50', '--no-reactions']
        if with_images:
            args.append('--download-resources')
        if page_token:
            args += ['--page-token', page_token]
        data = lark(args, identity, cwd=run_dir, timeout=300)
        raw.extend(data.get('messages') or [])
        if not data.get('has_more'):
            break
        page_token = data.get('page_token') or ''
        if not page_token:
            break
    return raw


def fetch_thread(cfg, identity, thread_id, run_dir):
    out = []
    page_token = ''
    for _ in range(20):
        args = ['im', '+threads-messages-list', '--thread', thread_id, '--order', 'asc', '--page-size', '50']
        if page_token:
            args += ['--page-token', page_token]
        try:
            data = lark(args, identity, cwd=run_dir)
        except LarkError as e:
            print(f'⚠️ 话题 {thread_id} 回复读取失败：{e}')
            break
        out.extend(data.get('messages') or [])
        if not data.get('has_more') or not data.get('page_token'):
            break
        page_token = data['page_token']
    return out


def fetch_existing_records(cfg, identity):
    records = []
    offset = 0
    limit = min(int(cfg.get('existing_records_limit', 300)), 200)
    while True:
        args = ['base', '+record-list', '--base-token', cfg['base_token'], '--table-id', cfg['table_id'],
                '--limit', str(limit), '--offset', str(offset), '--format', 'json']
        for f in RECORD_FIELDS:
            args += ['--field-id', f]
        data = lark(args, identity)
        rows = rows_to_dicts(data)
        for r in rows:
            def first(v):
                return v[0] if isinstance(v, list) and v else v
            records.append({
                'record_id': r.get('record_id'),
                '编号': r.get('编号'),
                '需求 / 问题': r.get('需求 / 问题'),
                '为了解决什么': r.get('为了解决什么'),
                '类型': first(r.get('类型')),
                '状态': first(r.get('状态')),
                '提出者': [u.get('name') for u in (r.get('提出者') or []) if isinstance(u, dict)],
                '提出者_id': [u.get('id') for u in (r.get('提出者') or []) if isinstance(u, dict)],
                '附议者_id': [u.get('id') for u in (r.get('附议者') or []) if isinstance(u, dict)],
                '来源 message_id': [s.strip() for s in (r.get('来源 message_id') or '').split(',') if s.strip()],
                '提出时间': r.get('提出时间'),
            })
        if not data.get('has_more') or not rows:
            break
        offset += len(rows)
        if offset >= int(cfg.get('existing_records_limit', 300)):
            break
    return records


def main():
    a = parse_args()
    cfg = load_config()
    state = load_state()
    base_identity = a.base_identity or a.identity

    run_dir = a.run or os.path.join(RUNS_DIR, now_cst().strftime('%Y%m%d-%H%M%S'))
    os.makedirs(run_dir, exist_ok=True)
    run_dir = os.path.abspath(run_dir)

    if a.since:
        start_iso = cst_text_to_iso(a.since)
        since_source = 'arg'
    elif state.get('last_message_time'):
        start_iso = cst_text_to_iso(state['last_message_time'])
        since_source = 'state'
    else:
        start_iso = cfg['initial_since']
        since_source = 'config'
    print(f'📥 拉取 {cfg["chat_name"]} 自 {start_iso} 起的消息（来源：{since_source}，身份：{a.identity}）')

    raw = fetch_messages(cfg, a.identity, start_iso, run_dir, not a.no_images)
    processed = set(state.get('processed_ids') or [])
    bot_id = cfg.get('bot_open_id')

    messages = []
    skipped = {'system_or_sticker': 0, 'deleted': 0, 'bot': 0, 'processed': 0}
    for m in raw:
        if m.get('msg_type') in SKIP_TYPES:
            skipped['system_or_sticker'] += 1
            continue
        if m.get('deleted'):
            skipped['deleted'] += 1
            continue
        sender = m.get('sender') or {}
        if sender.get('sender_type') == 'app' or (bot_id and sender.get('id') == bot_id):
            skipped['bot'] += 1
            continue
        if m.get('message_id') in processed:
            skipped['processed'] += 1
            continue
        item = normalize(m, run_dir)
        item['_seq'] = float(m.get('message_position') or len(messages))
        messages.append(item)
        if m.get('thread_id'):
            for k, r in enumerate(fetch_thread(cfg, a.identity, m['thread_id'], run_dir)):
                if r.get('message_id') in processed or r.get('deleted') or r.get('msg_type') in SKIP_TYPES:
                    continue
                reply = normalize(r, run_dir, thread_of=m.get('message_id'))
                reply['_seq'] = item['_seq'] + (k + 1) / 1000  # 紧跟在被回复的顶层消息后面
                messages.append(reply)

    # 保持群里的真实先后顺序（同一分钟内 message_id 不单调，不能按 id 排）
    messages.sort(key=lambda x: x['_seq'])
    for m in messages:
        m.pop('_seq', None)

    existing = []
    base_error = None
    try:
        existing = fetch_existing_records(cfg, base_identity)
    except LarkError as e:
        base_error = str(e)
        if not a.allow_no_base:
            print(f'❌ 读取需求池失败：{e}')
            if e.missing_scopes:
                print(f'   缺少 scope：{e.missing_scopes}；开通地址：{e.console_url}')
            sys.exit(1)
        print(f'⚠️ 读取需求池失败，按 --allow-no-base 继续（现有记录按空处理）：{e}')

    last_time = max([m.get('create_time') or '' for m in raw] + [state.get('last_message_time') or ''])
    payload = {
        'run': {
            'product': cfg['product'],
            'chat_id': cfg['chat_id'],
            'chat_name': cfg['chat_name'],
            'since': start_iso,
            'since_source': since_source,
            'generated_at': now_cst().strftime('%Y-%m-%d %H:%M:%S'),
            'raw_count': len(raw),
            'skipped': skipped,
            'last_message_time': last_time,
            'base_error': base_error,
        },
        'participants': sorted({(m['sender'], m['sender_id']) for m in messages if m.get('sender_id')}),
        'messages': messages,
        'existing_records': existing,
    }
    payload['participants'] = [{'name': n, 'id': i} for n, i in payload['participants']]
    save_json(os.path.join(run_dir, 'input.json'), payload)

    print(f'✅ 原始 {len(raw)} 条 → 待处理 {len(messages)} 条（跳过：{skipped}）；现有记录 {len(existing)} 条')
    print(f'   运行目录：{run_dir}')
    github_output(run_dir=run_dir, has_messages=str(bool(messages)).lower(), message_count=len(messages))


if __name__ == '__main__':
    main()
