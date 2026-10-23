#!/usr/bin/env python3
"""
第 4 步：把 post.md 以机器人身份发回内测群；失败时私信管理员。
也可用 --alert "文本" 单独给管理员发告警（供 workflow 失败时调用）。

用法：python3 post.py --run <dir>
      python3 post.py --alert "G1 内测反馈管线失败：..."
"""

import argparse
import os
import sys

from common import LarkError, lark, load_config, now_cst


def send_markdown(cfg, chat_id, text, idem_key):
    args = ['im', '+messages-send', '--chat-id', chat_id, '--markdown', text]
    if idem_key:
        args += ['--idempotency-key', idem_key[:50]]
    return lark(args, 'bot')


def alert_admin(cfg, text):
    try:
        lark(['im', '+messages-send', '--user-id', cfg['admin_open_id'], '--text', text], 'bot')
        print('📣 已私信管理员')
    except LarkError as e:
        print(f'❌ 告警发送失败：{e}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run')
    p.add_argument('--alert', help='只给管理员发这段告警文本')
    a = p.parse_args()
    cfg = load_config()

    if a.alert:
        alert_admin(cfg, f'⚠️ {cfg["product"]} 内测反馈管线\n时间：{now_cst().strftime("%Y-%m-%d %H:%M")}\n{a.alert}')
        return

    if not a.run:
        print('需要 --run 或 --alert')
        sys.exit(1)
    run_dir = os.path.abspath(a.run)
    post_path = os.path.join(run_dir, 'post.md')
    if not os.path.exists(post_path):
        print('ℹ️ 没有 post.md，跳过回群')
        return
    text = open(post_path, 'r', encoding='utf-8').read().strip()
    if not text:
        print('ℹ️ post.md 为空，跳过回群')
        return
    if not cfg.get('post_to_group', True):
        print('ℹ️ 配置 post_to_group=false，跳过回群')
        return
    try:
        data = send_markdown(cfg, cfg['chat_id'], text, f'g1fb-{os.path.basename(run_dir)}')
        print(f'✅ 已回群：message_id={data.get("message_id")}')
    except LarkError as e:
        print(f'❌ 回群失败：{e}')
        alert_admin(cfg, f'回群失败：{e}\n运行目录：{os.path.basename(run_dir)}')
        sys.exit(1)


if __name__ == '__main__':
    main()
