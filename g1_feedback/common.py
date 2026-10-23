#!/usr/bin/env python3
"""
G1 内测反馈管线 · 公共工具
- lark(): 调用 lark-cli 并解析 JSON 信封（ok=true 才算成功）
- 配置 / 状态文件读写
- 时间工具（统一按北京时间处理）
"""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
STATE_PATH = os.path.join(BASE_DIR, 'state.json')
RUNS_DIR = os.path.join(BASE_DIR, 'runs')

CST = timezone(timedelta(hours=8))

# lark-cli 的更新提示 / skills 提示会污染 JSON 输出，统一关掉
_ENV = dict(os.environ)
_ENV['LARKSUITE_CLI_NO_UPDATE_NOTIFIER'] = '1'
_ENV['LARKSUITE_CLI_NO_SKILLS_NOTIFIER'] = '1'


class LarkError(Exception):
    def __init__(self, error, cmd):
        self.error = error or {}
        self.cmd = cmd
        msg = self.error.get('message') or json.dumps(self.error, ensure_ascii=False)[:300]
        super().__init__(f'{msg} (cmd: {" ".join(cmd[:4])} ...)')

    @property
    def missing_scopes(self):
        return self.error.get('missing_scopes') or []

    @property
    def console_url(self):
        return self.error.get('console_url') or ''


def _first_json(text):
    """从可能带前缀日志的输出里取出第一个 JSON 对象"""
    if not text:
        return None
    start = text.find('{')
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj
    except json.JSONDecodeError:
        return None


def lark(args, identity, cwd=None, timeout=180):
    """运行 lark-cli，成功返回 data，失败抛 LarkError"""
    cmd = ['lark-cli', *args, '--as', identity]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=_ENV)
    payload = _first_json(proc.stdout) or _first_json(proc.stderr)
    if payload is None:
        raise LarkError({'message': (proc.stderr or proc.stdout or '').strip()[:500] or f'exit {proc.returncode}'}, cmd)
    if payload.get('ok'):
        return payload.get('data', payload)
    raise LarkError(payload.get('error') or payload, cmd)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def load_config():
    cfg = load_json(CONFIG_PATH)
    if not cfg:
        raise SystemExit(f'缺少配置文件 {CONFIG_PATH}')
    return cfg


def load_state():
    return load_json(STATE_PATH, default={'last_message_time': '', 'processed_ids': [], 'last_run_at': ''})


def save_state(state):
    save_json(STATE_PATH, state)


def now_cst():
    return datetime.now(CST)


def cst_text_to_iso(text):
    """'2026-10-23 15:14' → '2026-10-23T15:14:00+08:00'"""
    text = text.strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=CST)
            return dt.isoformat()
        except ValueError:
            continue
    # 已经是 ISO 的原样返回
    return text


def rows_to_dicts(data):
    """把 +record-list / +record-get 的列式 JSON 转成 [{字段: 值, record_id: ...}]"""
    fields = data.get('fields') or []
    ids = data.get('record_id_list') or []
    out = []
    for i, row in enumerate(data.get('data') or []):
        item = dict(zip(fields, row))
        item['record_id'] = ids[i] if i < len(ids) else None
        out.append(item)
    return out


def github_output(**kv):
    """把键值写进 GitHub Actions 的 step output（本地运行时只打印）"""
    path = os.environ.get('GITHUB_OUTPUT')
    lines = [f'{k}={v}' for k, v in kv.items()]
    if path:
        with open(path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    else:
        for line in lines:
            print(f'[output] {line}')
