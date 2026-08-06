#!/usr/bin/env python3
"""
Claude Code 资讯机器人 - 互动指令监听脚本 v1.1
持续监听群消息，识别指令并回复
v1.1: 增加权限控制

指令格式：
  普通指令（所有人可用）：
    /资讯 帮助    - 显示可用指令（群内回复）
    /资讯 今日    - 重新推送今天的资讯（群内回复）
    /资讯 状态    - 查看系统状态（群内回复）
    /资讯 关键词  - 查看当前关键词（私信回复）

  管理员指令（仅管理员可用）：
    /资讯 关键词 +XXX - 增加关键词（私信回复）
    /资讯 关键词 -XXX - 移除关键词（私信回复）
"""

import json
import subprocess
import time
import os
import re
from datetime import datetime
from typing import List, Dict, Optional


def load_config() -> dict:
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config: dict):
    """保存配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_last_message_id() -> str:
    """获取最后处理的消息 ID"""
    state_file = os.path.join(os.path.dirname(__file__), 'bot_state.json')
    if os.path.exists(state_file):
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
            return state.get('last_message_id', '')
    return ''


def save_last_message_id(message_id: str):
    """保存最后处理的消息 ID"""
    state_file = os.path.join(os.path.dirname(__file__), 'bot_state.json')
    
    # 读取现有状态
    state = {}
    if os.path.exists(state_file):
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
    
    # 更新消息 ID
    state['last_message_id'] = message_id
    state['updated_at'] = datetime.now().isoformat()
    
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_known_members() -> List[str]:
    """获取已知的群成员列表"""
    state_file = os.path.join(os.path.dirname(__file__), 'bot_state.json')
    if os.path.exists(state_file):
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
            return state.get('known_members', [])
    return []


def save_known_members(members: List[str]):
    """保存已知的群成员列表"""
    state_file = os.path.join(os.path.dirname(__file__), 'bot_state.json')
    
    # 读取现有状态
    state = {}
    if os.path.exists(state_file):
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
    
    # 更新成员列表
    state['known_members'] = members
    state['members_updated_at'] = datetime.now().isoformat()
    
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_chat_members(chat_id: str) -> List[dict]:
    """获取群成员列表"""
    try:
        cmd = [
            'lark-cli', 'im', '+chat-members-list', '--as', 'bot',
            '--chat-id', chat_id,
            '--page-size', '100',
            '--format', 'json'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"❌ 获取群成员失败: {result.stderr}")
            return []
        
        data = json.loads(result.stdout)
        # 用户列表在 data.users 中
        users = data.get('data', {}).get('users', [])
        return users
        
    except Exception as e:
        print(f"❌ 获取群成员异常: {e}")
        return []


def get_welcome_message() -> str:
    """获取欢迎消息"""
    welcome_file = os.path.join(os.path.dirname(__file__), 'welcome_message.txt')
    if os.path.exists(welcome_file):
        with open(welcome_file, 'r', encoding='utf-8') as f:
            return f.read()
    
    # 默认欢迎消息
    return """
👋 欢迎加入 Claude Code 交流群！

每天早上 10:57 自动推送 Claude Code 相关资讯。

🤖 发送 /资讯 帮助 查看所有可用指令

祝使用愉快！🚀
""".strip()


def check_new_members(chat_id: str) -> List[dict]:
    """检查新成员，返回新加入的成员列表"""
    known_members = get_known_members()
    current_members = get_chat_members(chat_id)
    
    current_member_ids = [m.get('member_id', '') for m in current_members if m.get('member_id')]
    
    # 找出新成员
    new_member_ids = [mid for mid in current_member_ids if mid not in known_members]
    
    if not new_member_ids:
        # 没有新成员，更新已知成员列表（防止有人退出）
        if known_members != current_member_ids:
            save_known_members(current_member_ids)
        return []
    
    # 获取新成员的详细信息
    new_members = [m for m in current_members if m.get('member_id') in new_member_ids]
    
    print(f"🎉 发现 {len(new_members)} 位新成员")
    
    # 给新成员发欢迎私信
    for member in new_members:
        member_id = member.get('member_id', '')
        member_name = member.get('name', '新成员')
        
        if member_id:
            welcome_msg = get_welcome_message()
            send_private_message(member_id, welcome_msg)
            print(f"   ✅ 已发送欢迎私信给 {member_name}")
    
    # 更新已知成员列表
    save_known_members(current_member_ids)
    
    return new_members


def get_new_messages(chat_id: str, last_message_id: str = '') -> List[dict]:
    """获取群里的新消息"""
    try:
        cmd = [
            'lark-cli', 'im', '+chat-messages-list', '--as', 'bot',
            '--chat-id', chat_id,
            '--page-size', '20',
            '--order', 'desc',
            '--format', 'json'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"❌ 获取消息失败: {result.stderr}")
            return []
        
        data = json.loads(result.stdout)
        messages = data.get('data', {}).get('messages', [])
        
        # 如果有 last_message_id，只返回新消息
        if last_message_id:
            new_messages = []
            for msg in messages:
                if msg['message_id'] == last_message_id:
                    break
                new_messages.append(msg)
            # 反转，按时间正序处理
            return list(reversed(new_messages))
        
        return messages
        
    except Exception as e:
        print(f"❌ 获取消息异常: {e}")
        return []


def send_message_to_chat(chat_id: str, content: str, msg_type: str = 'text') -> bool:
    """发送消息到群里"""
    try:
        if msg_type == 'markdown':
            cmd = [
                'lark-cli', 'im', '+messages-send', '--as', 'bot',
                '--chat-id', chat_id,
                '--markdown', content
            ]
        else:
            cmd = [
                'lark-cli', 'im', '+messages-send', '--as', 'bot',
                '--chat-id', chat_id,
                '--text', content
            ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return True
        else:
            print(f"❌ 发送消息失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 发送消息异常: {e}")
        return False


def send_private_message(user_id: str, content: str) -> bool:
    """发送私信给用户"""
    try:
        cmd = [
            'lark-cli', 'im', '+messages-send', '--as', 'bot',
            '--user-id', user_id,
            '--text', content
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return True
        else:
            print(f"❌ 发送私信失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 发送私信异常: {e}")
        return False


def extract_text_content(message: dict) -> str:
    """提取消息的纯文本内容"""
    content = message.get('content', '')
    msg_type = message.get('msg_type', '')
    
    if msg_type == 'text':
        # text 类型，content 是 JSON 字符串
        try:
            content_json = json.loads(content)
            return content_json.get('text', '')
        except:
            return content
    elif msg_type == 'post':
        # post 类型，尝试提取文本
        # 简单处理：去掉 HTML 标签
        text = re.sub(r'<[^>]+>', '', content)
        return text.strip()
    
    return content


def is_admin(user_id: str) -> bool:
    """检查用户是否是管理员"""
    config = load_config()
    admin_ids = config.get('feishu', {}).get('admin_user_ids', [])
    # 兼容旧配置
    if not admin_ids:
        admin_id = config.get('feishu', {}).get('admin_user_id', '')
        if admin_id:
            admin_ids = [admin_id]
    return user_id in admin_ids


# ==================== 指令处理函数 ====================

def cmd_help(user_id: str = '') -> str:
    """帮助指令"""
    help_text = """
🤖 Claude Code 资讯机器人 - 可用指令

📢 普通指令（所有人可用）：
  /资讯 帮助    - 显示此帮助信息
  /资讯 今日    - 重新推送今天的资讯
  /资讯 状态    - 查看系统运行状态
  /资讯 关键词  - 查看当前关注的关键词

🔒 管理员指令（仅管理员可用）：
  /资讯 关键词 +XXX - 增加关注关键词
  /资讯 关键词 -XXX - 移除关注关键词

💡 提示：直接在群里发送指令即可，不需要 @ 任何人
""".strip()
    
    if user_id and is_admin(user_id):
        help_text += "\n\n⭐ 您是管理员，可以使用所有指令"
    
    return help_text


def cmd_today() -> str:
    """今日资讯指令 - 重新推送今天的资讯"""
    today = datetime.now().strftime('%Y%m%d')
    report_file = os.path.join(os.path.dirname(__file__), f'news_{today}.md')
    
    if not os.path.exists(report_file):
        return "⚠️ 今天的资讯还没有生成，请稍等~"
    
    with open(report_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return content


def cmd_status() -> str:
    """状态指令"""
    config = load_config()
    
    # 统计信息源
    sources = config.get('sources', {})
    enabled_sources = [name for name, cfg in sources.items() if cfg.get('enabled', False)]
    
    # 统计关键词
    keywords = config.get('keywords', [])
    
    # 检查今天的报告
    today = datetime.now().strftime('%Y%m%d')
    report_file = os.path.join(os.path.dirname(__file__), f'news_{today}.md')
    raw_file = os.path.join(os.path.dirname(__file__), f'raw_news_{today}.json')
    
    report_exists = os.path.exists(report_file)
    raw_exists = os.path.exists(raw_file)
    
    raw_count = 0
    if raw_exists:
        try:
            with open(raw_file, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
                raw_count = raw_data.get('total_count', 0)
        except:
            pass
    
    # 重试配置
    retry_config = config.get('retry', {})
    
    return f"""
📊 系统状态

⏰ 推送时间：每天 {config.get('schedule', {}).get('time', '10:00')}
📡 启用信息源：{len(enabled_sources)} 个
   {', '.join(enabled_sources)}
🔑 关注关键词：{len(keywords)} 个
🔄 重试机制：最多 {retry_config.get('max_retries', 2)} 次

📅 今日状态：
   原始数据：{'✅ 已采集 (' + str(raw_count) + ' 条)' if raw_exists else '❌ 未采集'}
   整理报告：{'✅ 已生成' if report_exists else '❌ 未生成'}

💡 发送 /资讯 帮助 查看所有指令
""".strip()


def cmd_keywords_list() -> str:
    """查看关键词列表"""
    config = load_config()
    keywords = config.get('keywords', [])
    
    if not keywords:
        return "🔑 当前没有设置关键词"
    
    result = "🔑 当前关注的关键词：\n\n"
    for i, kw in enumerate(keywords, 1):
        result += f"  {i}. {kw}\n"
    
    result += f"\n共 {len(keywords)} 个关键词"
    result += "\n\n💡 增加关键词：/资讯 关键词 +XXX"
    result += "\n💡 移除关键词：/资讯 关键词 -XXX"
    
    return result


def cmd_keywords_add(keyword: str) -> str:
    """增加关键词"""
    config = load_config()
    keywords = config.get('keywords', [])
    
    if keyword in keywords:
        return f"⚠️ 关键词「{keyword}」已经存在了"
    
    keywords.append(keyword)
    config['keywords'] = keywords
    save_config(config)
    
    return f"""
✅ 已添加关键词：{keyword}

当前共 {len(keywords)} 个关键词
""".strip()


def cmd_keywords_remove(keyword: str) -> str:
    """移除关键词"""
    config = load_config()
    keywords = config.get('keywords', [])
    
    if keyword not in keywords:
        return f"⚠️ 关键词「{keyword}」不存在"
    
    keywords.remove(keyword)
    config['keywords'] = keywords
    save_config(config)
    
    return f"""
✅ 已移除关键词：{keyword}

当前共 {len(keywords)} 个关键词
""".strip()


# ==================== 主逻辑 ====================

def process_command(message: dict, chat_id: str) -> bool:
    """
    处理一条消息中的指令
    返回 True 表示处理了指令
    """
    sender_id = message.get('sender', {}).get('id', '')
    sender_name = message.get('sender', {}).get('name', '未知用户')
    text = extract_text_content(message)
    
    # 检查是否是指令（以 /资讯 开头）
    if not text.startswith('/资讯'):
        return False
    
    print(f"📥 收到指令：{text}（来自 {sender_name}）")
    
    # 解析指令
    parts = text.strip().split()
    if len(parts) < 2:
        # 只有 /资讯，显示帮助
        response = cmd_help(sender_id)
        send_message_to_chat(chat_id, response)
        return True
    
    command = parts[1].lower()
    
    # 群内回复的指令
    if command == '帮助' or command == 'help':
        response = cmd_help(sender_id)
        send_message_to_chat(chat_id, response)
        return True
    
    elif command == '今日' or command == 'today':
        response = cmd_today()
        send_message_to_chat(chat_id, response, msg_type='markdown')
        return True
    
    elif command == '状态' or command == 'status':
        response = cmd_status()
        send_message_to_chat(chat_id, response)
        return True
    
    # 关键词相关指令
    elif command == '关键词' or command == 'keyword':
        if len(parts) >= 3:
            action = parts[2]
            if action.startswith('+') or action.startswith('-'):
                # 修改关键词，需要管理员权限
                if not is_admin(sender_id):
                    no_perm_msg = f"⚠️ {sender_name}，您没有权限修改关键词\n\n如需调整，请联系管理员"
                    send_message_to_chat(chat_id, no_perm_msg)
                    print(f"   ❌ 权限不足，拒绝执行")
                    return True
                
                keyword = action[1:]
                if action.startswith('+'):
                    response = cmd_keywords_add(keyword)
                else:
                    response = cmd_keywords_remove(keyword)
                
                # 私信回复
                if sender_id:
                    send_private_message(sender_id, response)
                    # 群里公告一下
                    send_message_to_chat(chat_id, f"🔑 管理员 {sender_name} 已更新关键词配置")
                else:
                    send_message_to_chat(chat_id, response)
                return True
            else:
                # 查看关键词列表，所有人都可以
                response = cmd_keywords_list()
        else:
            # 查看关键词列表，所有人都可以
            response = cmd_keywords_list()
        
        # 查看列表，私信回复
        if sender_id:
            send_private_message(sender_id, response)
            # 群里提示一下
            send_message_to_chat(chat_id, f"✅ 已私信发送关键词信息给 {sender_name}")
        else:
            send_message_to_chat(chat_id, response)
        
        return True
    
    # 未知指令
    else:
        response = f"❓ 未知指令：{command}\n\n发送 /资讯 帮助 查看可用指令"
        send_message_to_chat(chat_id, response)
        return True


def main():
    """主函数 - 持续监听消息"""
    print("🤖 Claude Code 资讯机器人启动...")
    
    config = load_config()
    chat_id = config['feishu']['chat_id']
    chat_name = config['feishu']['chat_name']
    
    print(f"📡 监听群聊：{chat_name}")
    print(f"   Chat ID: {chat_id}")
    
    # 获取最后处理的消息 ID
    last_message_id = get_last_message_id()
    if last_message_id:
        print(f"   上次处理到：{last_message_id}")
    else:
        print("   首次启动，将从最新消息开始处理")
        # 首次启动，获取最新一条消息的 ID 作为起点
        messages = get_new_messages(chat_id)
        if messages:
            last_message_id = messages[0]['message_id']
            save_last_message_id(last_message_id)
            print(f"   起点消息：{last_message_id}")
    
    # 初始化已知成员列表
    known_members = get_known_members()
    if not known_members:
        print("   初始化群成员列表...")
        members = get_chat_members(chat_id)
        member_ids = [m.get('member_id', '') for m in members if m.get('member_id')]
        save_known_members(member_ids)
        print(f"   当前群成员：{len(member_ids)} 人")
    
    print("\n🚀 开始监听消息...（按 Ctrl+C 停止）")
    print("💡 发送 /资讯 帮助 查看可用指令")
    print()
    
    poll_interval = 10  # 轮询间隔（秒）
    member_check_interval = 6  # 每 6 轮（1分钟）检查一次新成员
    member_check_counter = 0
    
    try:
        while True:
            # 获取新消息
            new_messages = get_new_messages(chat_id, last_message_id)
            
            for msg in new_messages:
                # 跳过系统消息和自己发的消息
                msg_type = msg.get('msg_type', '')
                sender_type = msg.get('sender', {}).get('sender_type', '')
                
                if msg_type == 'system':
                    continue
                
                # 处理指令
                try:
                    processed = process_command(msg, chat_id)
                except Exception as e:
                    print(f"❌ 处理消息出错: {e}")
                
                # 更新最后处理的消息 ID
                last_message_id = msg['message_id']
                save_last_message_id(last_message_id)
            
            # 定期检查新成员
            member_check_counter += 1
            if member_check_counter >= member_check_interval:
                member_check_counter = 0
                try:
                    check_new_members(chat_id)
                except Exception as e:
                    print(f"❌ 检查新成员出错: {e}")
            
            # 等待下一轮
            time.sleep(poll_interval)
            
    except KeyboardInterrupt:
        print("\n\n👋 机器人已停止")
    except Exception as e:
        print(f"\n❌ 运行出错: {e}")


if __name__ == '__main__':
    main()
