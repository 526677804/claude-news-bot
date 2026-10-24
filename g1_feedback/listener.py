#!/usr/bin/env python3
"""
手动触发监听器：有人在内测群里 @机器人（或管理员私聊机器人）说「记一下 / 整理 / 记录」时，
立刻触发一次 GitHub Actions 上的收录管线（与每日定时同一条管线、同一份水位，所以不会重复记录）。

运行方式：常驻在本机（launchd），每 POLL_SECONDS 秒轮询一次群消息；不依赖事件订阅配置。
- 群里：必须 @机器人；私聊：任意文字即可
- 「状态」：回复最近一次运行的状态；其他文字：触发整理
- 同一轮整理进行中（3 分钟内）再次触发只回「已在整理」，不重复派发
- 触发消息超过 2 小时未处理（比如电脑睡了很久）就不再补跑，交给每日定时

用法：python3 listener.py            # 常驻
      python3 listener.py --once     # 只轮询一次（排障）
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

from common import CST, RUNS_DIR, LarkError, lark, load_config, load_json, save_json

POLL_SECONDS = 45
DEBOUNCE_SECONDS = 180
MAX_TRIGGER_AGE = timedelta(hours=2)
LOOKBACK = timedelta(minutes=3)
STATE_PATH = os.path.join(RUNS_DIR, 'listener_state.json')
REPO = '526677804/claude-news-bot'
WORKFLOW = 'g1-feedback.yml'
TRIGGER_WORDS = ('记一下', '记录', '整理', '收录', '更新一下', 'record', 'sync')
STATUS_WORDS = ('状态', 'status')
HELP_WORDS = ('帮助', 'help')


def log(msg):
    print(f'[{datetime.now(CST).strftime("%m-%d %H:%M:%S")}] {msg}', flush=True)


def load_state():
    return load_json(STATE_PATH, default={'handled_ids': [], 'last_check': '', 'last_dispatch_at': 0})


def save_state(state):
    os.makedirs(RUNS_DIR, exist_ok=True)
    state['handled_ids'] = state['handled_ids'][-300:]
    save_json(STATE_PATH, state)


def parse_time(text):
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=CST)
        except (ValueError, TypeError):
            continue
    return None


def strip_mentions(text):
    text = re.sub(r'<[^>]+>', ' ', text or '')
    text = re.sub(r'@\S+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def mentions_bot(msg, cfg):
    bot_id = cfg.get('bot_open_id')
    for m in msg.get('mentions') or []:
        if m.get('id') == bot_id or (cfg.get('bot_name') and m.get('name') == cfg.get('bot_name')):
            return True
    return False


def list_messages(chat_id, since_iso):
    out = []
    token = ''
    for _ in range(5):
        args = ['im', '+chat-messages-list', '--chat-id', chat_id, '--start', since_iso,
                '--order', 'asc', '--page-size', '50', '--no-reactions']
        if token:
            args += ['--page-token', token]
        data = lark(args, 'bot', timeout=90)
        out.extend(data.get('messages') or [])
        if not data.get('has_more') or not data.get('page_token'):
            break
        token = data['page_token']
    return out


def reply(message_id, text):
    try:
        lark(['im', '+messages-reply', '--message-id', message_id, '--text', text], 'bot', timeout=60)
    except LarkError as e:
        log(f'回复失败：{e}')


def latest_run_status():
    try:
        out = subprocess.run(['gh', 'run', 'list', '-R', REPO, '--workflow', WORKFLOW, '--limit', '1',
                              '--json', 'status,conclusion,createdAt,event,url'],
                             capture_output=True, text=True, timeout=60)
        runs = json.loads(out.stdout or '[]')
        if not runs:
            return '还没有运行记录'
        r = runs[0]
        created = r.get('createdAt', '')
        try:
            created = datetime.fromisoformat(created.replace('Z', '+00:00')).astimezone(CST).strftime('%m-%d %H:%M')
        except ValueError:
            pass
        return f'最近一次：{created} {r.get("event")} → {r.get("status")}/{r.get("conclusion") or "进行中"}\n{r.get("url")}'
    except Exception as e:  # noqa: BLE001
        return f'查询失败：{e}'


def dispatch(reply_to=None, manual=True):
    args = ['gh', 'workflow', 'run', WORKFLOW, '-R', REPO, '-f', f'manual={"true" if manual else "false"}']
    if reply_to:
        args += ['-f', f'reply_to={reply_to}']
    out = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip()[:300])


def daily_dispatch_if_due(cfg, state):
    """到了每日时间点（默认 18:30）就由本机准点派发一次；GitHub 自己的 cron 高峰期会晚几小时，只当备份。"""
    daily = cfg.get('daily_time')  # 为空表示每日定时不由本机派发（已交给妙搭触发器）
    if not daily:
        return
    now = datetime.now(CST)
    today = now.strftime('%Y-%m-%d')
    if state.get('last_daily_date') == today or now.strftime('%H:%M') < daily:
        return
    try:
        dispatch(manual=False)
        log(f'每日 {daily} 定时已由本机派发')
    except Exception as e:  # noqa: BLE001
        log(f'每日定时派发失败（GitHub cron 会兜底）：{e}')
    state['last_daily_date'] = today
    state['last_dispatch_at'] = time.time()
    save_state(state)


def handle(msg, cfg, state, in_group):
    text = strip_mentions(msg.get('content') if isinstance(msg.get('content'), str) else '')
    sender = (msg.get('sender') or {}).get('name') or ''
    mid = msg['message_id']
    low = text.lower()

    if any(w in low for w in HELP_WORDS):
        reply(mid, f'我目前只负责「{cfg["chat_name"]}」的内测反馈收录。在那个群里 @我 说「记一下」，或在这里对我说「记一下」，'
                   f'都会马上整理该群最近的讨论进需求池并回群通报；说「状态」看最近一次运行。每天 18:30 也会自动整理一次，手动和定时共用一份进度，不会重复记录。')
        return
    if any(w in low for w in STATUS_WORDS):
        reply(mid, latest_run_status())
        return

    now = time.time()
    if now - float(state.get('last_dispatch_at') or 0) < DEBOUNCE_SECONDS:
        reply(mid, '上一轮整理还在进行中，这次的内容会一起带上，稍等。')
        return
    try:
        dispatch(reply_to=mid if in_group else None)
    except Exception as e:  # noqa: BLE001
        log(f'派发失败：{e}')
        reply(mid, f'触发失败：{str(e)[:120]}')
        return
    state['last_dispatch_at'] = now
    log(f'已派发（{sender}：{text[:40]}）')
    where = '在群里通报' if in_group else f'发到「{cfg["chat_name"]}」群里'
    reply(mid, f'收到，正在整理「{cfg["chat_name"]}」最近的讨论（约 2–3 分钟）。有新记录才{where}，没有就不打扰。')


def poll(cfg, state):
    now = datetime.now(CST)
    last_check = parse_time(state.get('last_check')) if state.get('last_check') else None
    since = max(last_check - LOOKBACK if last_check else now - MAX_TRIGGER_AGE, now - MAX_TRIGGER_AGE)
    handled = set(state.get('handled_ids') or [])
    bot_id = cfg.get('bot_open_id')

    watch = [(cfg['chat_id'], True)]
    if cfg.get('admin_dm_chat_id'):
        watch.append((cfg['admin_dm_chat_id'], False))

    for chat_id, in_group in watch:
        try:
            msgs = list_messages(chat_id, since.isoformat())
        except LarkError as e:
            log(f'拉取失败 {chat_id}：{e}')
            continue
        for m in msgs:
            mid = m.get('message_id')
            sender = m.get('sender') or {}
            if not mid or mid in handled or m.get('deleted'):
                continue
            if sender.get('sender_type') == 'app' or sender.get('id') == bot_id:
                continue
            if m.get('msg_type') not in ('text', 'post'):
                continue
            if in_group and not mentions_bot(m, cfg):
                continue
            created = parse_time(m.get('create_time') or '')
            handled.add(mid)
            state['handled_ids'] = list(handled)
            if created and now - created > MAX_TRIGGER_AGE:
                log(f'跳过过期触发 {mid}（{m.get("create_time")}）')
                continue
            handle(m, cfg, state, in_group)
    state['last_check'] = now.strftime('%Y-%m-%d %H:%M:%S')
    save_state(state)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--once', action='store_true')
    a = p.parse_args()
    cfg = load_config()
    state = load_state()
    log(f'监听启动：群 {cfg["chat_name"]}' + ('，以及管理员私聊' if cfg.get('admin_dm_chat_id') else ''))
    while True:
        try:
            poll(cfg, state)
            daily_dispatch_if_due(cfg, state)
        except Exception as e:  # noqa: BLE001
            log(f'轮询异常：{e!r}')
        if a.once:
            break
        time.sleep(POLL_SECONDS)


if __name__ == '__main__':
    main()
