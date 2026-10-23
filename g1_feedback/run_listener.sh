#!/bin/bash
# 手动触发监听器的启动包装：先把本地检出更新到最新（配置 / 代码随仓库走），再常驻运行 listener.py。
# 由 launchd 调用（见 README「手动触发」一节）。这个检出必须放在 ~/Documents 之外，
# 否则 macOS 的隐私保护会拒绝后台进程读取文件。
set -u
cd "$(dirname "$0")" || exit 1
git pull --ff-only -q 2>/dev/null || echo "[run_listener] git pull 失败，用当前版本继续"
exec /usr/bin/python3 listener.py
