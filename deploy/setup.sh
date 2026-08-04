#!/bin/bash
# 服务器部署脚本（Ubuntu/Debian）
# 用法：在服务器上 clone 仓库到 /opt/claude-news-bot 后执行 sudo bash deploy/setup.sh
set -e

APP_DIR=/opt/claude-news-bot

if [ ! -d "$APP_DIR" ]; then
    echo "❌ 请先把仓库 clone 到 $APP_DIR"
    exit 1
fi

echo "==> 1/4 安装 Python 依赖"
apt-get update -qq
apt-get install -y -qq python3 python3-pip
pip3 install -q -r "$APP_DIR/requirements.txt"

echo "==> 2/4 检查 lark-cli"
if ! command -v lark-cli &> /dev/null; then
    echo "⚠️  lark-cli 未安装，请手动安装并完成认证："
    echo "    1) 安装 lark-cli（参考飞书官方文档）"
    echo "    2) lark-cli config init --new"
    echo "    3) lark-cli auth login --scope \"im:message.send_as_user\""
fi

echo "==> 3/4 检查 .env（twitterapi.io API Key）"
if [ ! -f "$APP_DIR/.env" ]; then
    echo "⚠️  未找到 .env，请复制 .env.example 并填入 TWITTERAPI_IO_KEY"
fi

echo "==> 4/4 安装 systemd 服务"
cp "$APP_DIR/deploy/claude-news-daily.service" /etc/systemd/system/
cp "$APP_DIR/deploy/claude-news-daily.timer" /etc/systemd/system/
cp "$APP_DIR/deploy/claude-news-bot.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now claude-news-daily.timer
systemctl enable --now claude-news-bot.service

echo ""
echo "✅ 部署完成。验证命令："
echo "   systemctl list-timers claude-news-daily.timer   # 查看下次触发时间"
echo "   systemctl status claude-news-bot                # 互动机器人状态"
echo "   cd $APP_DIR && python3 test_sources.py          # 复测所有信息源连通性"
echo "   systemctl start claude-news-daily.service       # 手动触发一次完整流程"
