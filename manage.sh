#!/bin/bash
# Claude Code 资讯机器人 - 管理脚本
# 用法：./manage.sh start|stop|restart|status|logs

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOT_SCRIPT="bot_listener.py"
PID_FILE="$SCRIPT_DIR/bot.pid"
LOG_FILE="$SCRIPT_DIR/bot.log"

cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        else
            # PID 文件存在但进程不存在，清理
            rm -f "$PID_FILE"
            return 1
        fi
    fi
    return 1
}

start() {
    if is_running; then
        echo -e "${YELLOW}⚠️  机器人已经在运行中 (PID: $(cat $PID_FILE))${NC}"
        return 1
    fi
    
    echo "🚀 启动 Claude Code 资讯机器人..."
    
    # 启动机器人
    nohup python3 "$BOT_SCRIPT" > "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    
    # 等待一下确认启动成功
    sleep 2
    
    if is_running; then
        echo -e "${GREEN}✅ 机器人启动成功！(PID: $pid)${NC}"
        echo "📝 日志文件: $LOG_FILE"
        return 0
    else
        echo -e "${RED}❌ 机器人启动失败，请查看日志${NC}"
        tail -20 "$LOG_FILE"
        return 1
    fi
}

stop() {
    if ! is_running; then
        echo -e "${YELLOW}⚠️  机器人没有在运行${NC}"
        return 1
    fi
    
    local pid=$(cat "$PID_FILE")
    echo "⏹️  停止机器人 (PID: $pid)..."
    
    kill "$pid"
    sleep 2
    
    # 如果还没停止，强制杀死
    if kill -0 "$pid" 2>/dev/null; then
        echo "⚠️  进程未响应，强制停止..."
        kill -9 "$pid"
        sleep 1
    fi
    
    rm -f "$PID_FILE"
    echo -e "${GREEN}✅ 机器人已停止${NC}"
    return 0
}

restart() {
    echo "🔄 重启机器人..."
    stop
    sleep 1
    start
}

status() {
    if is_running; then
        local pid=$(cat "$PID_FILE")
        echo -e "${GREEN}✅ 机器人运行中${NC}"
        echo "   PID: $pid"
        echo "   日志: $LOG_FILE"
        
        # 显示运行时长
        if [ -f /proc/$pid/stat ]; then
            local start_time=$(stat -c %Y /proc/$pid)
            local now=$(date +%s)
            local elapsed=$((now - start_time))
            local days=$((elapsed / 86400))
            local hours=$(( (elapsed % 86400) / 3600 ))
            local mins=$(( (elapsed % 3600) / 60 ))
            echo "   运行时长: ${days}天 ${hours}小时 ${mins}分钟"
        fi
        
        # 显示最后几行日志
        echo ""
        echo "📋 最近日志:"
        tail -5 "$LOG_FILE"
    else
        echo -e "${RED}❌ 机器人未运行${NC}"
        return 1
    fi
}

logs() {
    if [ -f "$LOG_FILE" ]; then
        echo "📋 显示日志 (按 Ctrl+C 退出)"
        echo "----------------------------------------"
        tail -f "$LOG_FILE"
    else
        echo "❌ 日志文件不存在"
        return 1
    fi
}

# 主逻辑
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        echo "🤖 Claude Code 资讯机器人 - 管理脚本"
        echo ""
        echo "用法: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "命令:"
        echo "  start    - 启动机器人"
        echo "  stop     - 停止机器人"
        echo "  restart  - 重启机器人"
        echo "  status   - 查看运行状态"
        echo "  logs     - 查看实时日志"
        echo ""
        exit 1
        ;;
esac
