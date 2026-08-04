#!/usr/bin/env python3
"""
飞书推送脚本 v2.0
将资讯报告推送到指定飞书群，支持失败告警
"""

import json
import subprocess
import sys
import os
from datetime import datetime


def load_config() -> dict:
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def send_to_feishu(chat_id: str, content: str, msg_type: str = 'markdown') -> bool:
    """
    发送消息到飞书群
    使用 lark-cli 命令行工具
    """
    try:
        # 使用 lark-cli 以机器人身份发送消息
        cmd = [
            'lark-cli', 'im', '+messages-send', '--as', 'bot',
            '--chat-id', chat_id,
            '--markdown', content
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print("✅ 飞书消息发送成功")
            return True
        else:
            print(f"❌ 飞书消息发送失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 发送异常: {e}")
        return False


def send_text_message(chat_id: str, text: str) -> bool:
    """发送纯文本消息"""
    try:
        cmd = [
            'lark-cli', 'im', '+messages-send', '--as', 'bot',
            '--chat-id', chat_id,
            '--text', text
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ 文本消息发送成功")
            return True
        else:
            print(f"❌ 文本消息发送失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 发送异常: {e}")
        return False


def send_alert_to_admin(admin_user_id: str, error_msg: str) -> bool:
    """
    给管理员发送失败告警私信
    """
    try:
        alert_text = f"""
⚠️ Claude Code 每日资讯推送失败

时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
错误信息：{error_msg}

请检查：
1. 采集脚本是否正常运行
2. 飞书 API 是否可用
3. 网络连接是否正常
""".strip()
        
        cmd = [
            'lark-cli', 'im', '+messages-send', '--as', 'bot',
            '--user-id', admin_user_id,
            '--text', alert_text
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ 告警消息已发送给管理员")
            return True
        else:
            print(f"❌ 告警消息发送失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 告警异常: {e}")
        return False


def main():
    """主函数"""
    config = load_config()
    chat_id = config['feishu']['chat_id']
    chat_name = config['feishu']['chat_name']
    admin_user_id = config['feishu'].get('admin_user_id', '')
    
    print(f"📤 准备推送到飞书群: {chat_name}")
    print(f"   Chat ID: {chat_id}")
    
    # 读取今天的资讯报告
    today = datetime.now().strftime('%Y%m%d')
    report_file = os.path.join(os.path.dirname(__file__), f'news_{today}.md')
    
    if not os.path.exists(report_file):
        error_msg = f"找不到今天的资讯报告: {report_file}"
        print(f"❌ {error_msg}")
        print("   请先运行 fetch_news.py 生成报告")
        
        # 发送告警
        if admin_user_id:
            print("\n📢 发送失败告警给管理员...")
            send_alert_to_admin(admin_user_id, error_msg)
        
        sys.exit(1)
    
    with open(report_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"📄 报告长度: {len(content)} 字符")
    
    # 发送消息
    success = send_to_feishu(chat_id, content)
    
    if success:
        print("\n✅ 推送完成！")
    else:
        error_msg = "飞书消息发送失败，请检查日志"
        print(f"\n❌ 推送失败")
        
        # 发送告警
        if admin_user_id:
            print("\n📢 发送失败告警给管理员...")
            send_alert_to_admin(admin_user_id, error_msg)
        
        sys.exit(1)


if __name__ == '__main__':
    main()
