#!/usr/bin/env python3
"""
第 3 步：把 output.json 写进飞书需求池（多维表格），更新水位，生成回群消息 post.md。

- 新记录：+record-batch-create，之后逐条 +record-get 拿「编号」
- 追加：+record-get 读当前 讨论摘要 / 附议者 / 来源 message_id，合并后 +record-upsert --record-id
- 水位：state.json 的 last_message_time + processed_ids（最近 500 条）
- 回群消息：post.md（Markdown，含 @提出者）；没有任何新增 / 追加时不生成

用法：python3 write.py --run <dir> [--as bot|user] [--dry-run]
"""

import argparse
import os
import sys
from datetime import datetime

from common import (LarkError, github_output, lark, load_config, load_json, load_state, now_cst,
                    rows_to_dicts, save_json, save_state)

PROCESSED_KEEP = 500


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--run', required=True)
    p.add_argument('--as', dest='identity', default=os.environ.get('LARK_AS', 'bot'), choices=['bot', 'user'])
    p.add_argument('--dry-run', action='store_true', help='只打印将写入的内容，不写需求池、不改水位')
    return p.parse_args()


def to_cell_values(r):
    cells = {
        '需求 / 问题': r['需求 / 问题'],
        '为了解决什么': r.get('为了解决什么') or '待确认',
        '类型': r['类型'],
        '产品': r.get('产品') or 'G1',
        '提出者': [{'id': r['提出者']}],
        '提出时间': r['提出时间'],
        '原文链接': r['原文链接'],
        '讨论摘要': r.get('讨论摘要') or '',
        '状态': '待筛选',
        '来源 message_id': ','.join(r.get('来源 message_id') or []),
    }
    mods = r.get('涉及模块') or []
    if mods:
        cells['涉及模块'] = mods
    supporters = [s for s in dict.fromkeys(r.get('附议者') or []) if s != r['提出者']]
    if supporters:
        cells['附议者'] = [{'id': s} for s in supporters]
    if r.get('初步建议'):
        cells['初步建议'] = r['初步建议']
    return cells


def get_record(cfg, identity, record_id):
    data = lark(['base', '+record-get', '--base-token', cfg['base_token'], '--table-id', cfg['table_id'],
                 '--record-id', record_id, '--format', 'json'], identity)
    rows = rows_to_dicts(data)
    return rows[0] if rows else {}


def create_records(cfg, identity, records):
    ids = []
    for i in range(0, len(records), 200):
        chunk = records[i:i + 200]
        payload = {'create_records': [to_cell_values(r) for r in chunk]}
        data = lark(['base', '+record-batch-create', '--base-token', cfg['base_token'], '--table-id', cfg['table_id'],
                     '--json', __import__('json').dumps(payload, ensure_ascii=False)], identity)
        ids.extend(data.get('record_id_list') or [])
    return ids


def apply_update(cfg, identity, u, stamp):
    cur = get_record(cfg, identity, u['record_id'])
    if not cur:
        raise LarkError({'message': f'记录不存在：{u["record_id"]}'}, ['base', '+record-get'])
    cells = {}
    if u.get('append_discussion'):
        old = cur.get('讨论摘要') or ''
        line = f'[{stamp}] {u["append_discussion"].strip()}'
        cells['讨论摘要'] = (old.rstrip() + '\n' + line) if old else line
    proposer = {x.get('id') for x in (cur.get('提出者') or []) if isinstance(x, dict)}
    if u.get('add_supporters'):
        old_ids = [x.get('id') for x in (cur.get('附议者') or []) if isinstance(x, dict)]
        merged = [s for s in dict.fromkeys(old_ids + list(u['add_supporters'])) if s and s not in proposer]
        cells['附议者'] = [{'id': s} for s in merged]
    if u.get('add_message_ids'):
        old_ids = [s.strip() for s in (cur.get('来源 message_id') or '').split(',') if s.strip()]
        cells['来源 message_id'] = ','.join(dict.fromkeys(old_ids + list(u['add_message_ids'])))
    if not cells:
        return cur
    lark(['base', '+record-upsert', '--base-token', cfg['base_token'], '--table-id', cfg['table_id'],
          '--record-id', u['record_id'], '--json', __import__('json').dumps(cells, ensure_ascii=False)], identity)
    return cur


def first(v):
    return v[0] if isinstance(v, list) and v else v


def build_post(cfg, created, updated, day_label):
    """created: [(编号, 记录 dict)]; updated: [(编号, 需求, update dict)]"""
    n, m = len(created), len(updated)
    head = f'📝 {cfg["product"]} 内测反馈 · {day_label} 自动收录 {n} 条' + (f'，追加 {m} 条' if m else '')
    lines = [head, '']
    limit = int(cfg.get('max_lines_in_post', 10))
    shown = 0
    for code, r in created:
        if shown >= limit:
            break
        at = f'<at user_id="{r["提出者"]}"></at>'
        tail = f' · {r["初步建议"]}' if r.get('初步建议') else ''
        prefix = f'{code} ' if code else ''
        lines.append(f'{shown + 1}. {prefix}{r["需求 / 问题"]} —— {at}{tail}')
        shown += 1
    rest = n - shown
    if rest > 0:
        lines.append(f'…… 另有 {rest} 条见需求池')
    if updated:
        lines.append('')
        lines.append('追加到已有记录：' + '；'.join(f'{c or ""} {t}'.strip() for c, t, _ in updated[:limit]))
    lines.append('')
    lines.append(f'📋 需求池：{cfg["pool_url"]}')
    lines.append(cfg.get('post_footer') or '每天 18:30 自动整理一次群里与产品相关的讨论；理解有偏差的直接回这条消息说一声，筛选、结论和进度在需求池里维护。')
    return '\n'.join(lines)


def main():
    a = parse_args()
    cfg = load_config()
    run_dir = os.path.abspath(a.run)
    inp = load_json(os.path.join(run_dir, 'input.json')) or {}
    out = load_json(os.path.join(run_dir, 'output.json'))
    if out is None:
        print('❌ 找不到 output.json')
        sys.exit(1)

    new_records = out.get('new_records') or []
    updates = out.get('updates') or []
    stamp = now_cst().strftime('%m-%d')
    day_label = now_cst().strftime('%m-%d')

    if a.dry_run:
        import json
        print('🧪 dry-run：以下内容将写入需求池')
        for r in new_records:
            print(json.dumps(to_cell_values(r), ensure_ascii=False))
        for u in updates:
            print('update', json.dumps(u, ensure_ascii=False))
        created = [(None, r) for r in new_records]
        updated = [(u.get('编号'), '', u) for u in updates]
        post = build_post(cfg, created, updated, day_label) if (created or updated) else ''
        print('--- post.md ---\n' + post)
        github_output(has_post='false')
        return

    created = []
    if new_records:
        ids = create_records(cfg, a.identity, new_records)
        print(f'✅ 新增 {len(ids)} 条记录')
        for rid, r in zip(ids, new_records):
            code = None
            try:
                code = get_record(cfg, a.identity, rid).get('编号')
            except LarkError as e:
                print(f'⚠️ 读取编号失败 {rid}：{e}')
            created.append((code, r))
    updated = []
    for u in updates:
        try:
            cur = apply_update(cfg, a.identity, u, stamp)
            updated.append((cur.get('编号') or u.get('编号'), cur.get('需求 / 问题') or '', u))
            print(f'✅ 追加到 {cur.get("编号")}：{u.get("append_discussion", "")[:40]}')
        except LarkError as e:
            print(f'❌ 追加失败 {u.get("record_id")}：{e}')
            raise

    # 水位：所有本次拉到的消息都算处理过（包括被判为闲聊的）
    state = load_state()
    msg_ids = [m['id'] for m in inp.get('messages', []) if m.get('id')]
    last_time = inp.get('run', {}).get('last_message_time') or state.get('last_message_time') or ''
    if last_time:
        state['last_message_time'] = last_time
    state['processed_ids'] = (list(state.get('processed_ids') or []) + msg_ids)[-PROCESSED_KEEP:]
    state['last_run_at'] = now_cst().strftime('%Y-%m-%d %H:%M:%S')
    state['last_run'] = {'created': len(created), 'updated': len(updated), 'messages': len(msg_ids), 'run_dir': os.path.basename(run_dir)}
    save_state(state)
    print(f'💾 水位更新：last_message_time={state["last_message_time"]}，processed_ids={len(state["processed_ids"])}')

    post_path = os.path.join(run_dir, 'post.md')
    if created or updated:
        post = build_post(cfg, created, updated, day_label)
        with open(post_path, 'w', encoding='utf-8') as f:
            f.write(post)
        print('--- post.md ---\n' + post)
        github_output(has_post='true' if cfg.get('post_to_group', True) else 'false')
    else:
        print(f'ℹ️ 无新增、无追加（{out.get("skipped_reason")}），不回群')
        github_output(has_post='false')
    save_json(os.path.join(run_dir, 'summary.json'), {
        'created': [{'编号': c, '需求 / 问题': r['需求 / 问题']} for c, r in created],
        'updated': [{'编号': c, '需求 / 问题': t} for c, t, _ in updated],
    })


if __name__ == '__main__':
    main()
