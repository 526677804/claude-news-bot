#!/usr/bin/env python3
"""
第 2 步：AI 提取。Cursor SDK 无头代理阅读 <run>/input.json，把群聊里和产品相关的内容
整理成结构化的 output.json（新需求记录 + 对已有记录的追加）。

需要环境变量 CURSOR_API_KEY。失败自动重试一次（把校验错误反馈给代理）。
退出码：0 成功（含「本窗口没有产品相关内容」的空结果）；2 失败；3 未配置 API Key
"""

import argparse
import json
import os
import sys
import time

from common import load_json, save_json

MAX_ATTEMPTS = 2
RETRY_DELAY = 20

TYPES = ['新需求', '体验问题', 'Bug', '疑问', '流程', '信号']
MODULES = ['画布', '节点', '生成', '协作', '接口', '性能', '账号', '其他']
PRODUCTS = ['G1', 'G2', '其他']
SUGGESTIONS = ['直接做', '需探讨', '待确认']

OUTPUT_SCHEMA = """{
  "new_records": [
    {
      "需求 / 问题": "一句话，<= 40 字，说清用户要什么或遇到了什么",
      "为了解决什么": "背后的问题或动机，一两句；推断不出来就写「待确认」",
      "类型": "新需求 | 体验问题 | Bug | 疑问 | 流程 | 信号",
      "涉及模块": ["画布", "节点", "生成", "协作", "接口", "性能", "账号", "其他"],
      "产品": "G1 | G2 | 其他",
      "提出者": "ou_xxx（第一个提出的人的 sender_id）",
      "附议者": ["ou_xxx", "..."],
      "提出时间": "YYYY-MM-DD HH:mm:ss（第一次提出的消息时间）",
      "原文链接": "第一次提出的那条消息的 link",
      "讨论摘要": "群里围绕这条的来回：谁说了什么、有没有分歧、负责人怎么回的；用「姓名：要点」的形式，两到六句",
      "初步建议": "直接做 | 需探讨 | 待确认（类型为 信号/疑问/流程 时可留空字符串）",
      "来源 message_id": ["om_xxx", "..."]
    }
  ],
  "updates": [
    {
      "record_id": "existing_records 里的 record_id",
      "编号": "对应的编号，便于人读",
      "append_discussion": "本窗口新增的讨论要点（姓名：要点），不要重复已有内容",
      "add_supporters": ["ou_xxx"],
      "add_message_ids": ["om_xxx"]
    }
  ],
  "skipped_reason": "两个数组都为空时说明原因，否则为 null"
}"""


def build_prompt(run_dir, feedback=''):
    fb = ''
    if feedback:
        fb = f"""

## 上一次输出未通过校验，请修正后重写 output.json
{feedback}
"""
    return f"""你是「{{product}} 内测反馈」的记录员。当前目录下的 input.json 是飞书内测群一段时间内的聊天记录\
（messages 按时间升序；participants 是发言人及其 open_id；existing_records 是需求池里已有的记录）。\
请把其中和产品相关的内容整理成结构化记录，写入当前目录的 output.json（UTF-8，严格 JSON，不要 Markdown 代码围栏，不要注释）。

## 输出格式（字段名必须一字不差）
{OUTPUT_SCHEMA}

## 判断规则
- 只记录和产品有关的内容：功能需求、体验问题、Bug、对产品的疑问、流程类问题（比如「这里能不能顺便提另一个产品的意见」）、以及值得留档的明确正面信号。\
闲聊、寒暄、入群介绍、表情、调侃、人事安排一律忽略。
- 同一个人在几分钟内连发的多条消息通常是一个意思，合并成一条记录；不同的人在说同一件事，第一个提出的人是「提出者」，其他人进「附议者」。
- 一条消息里包含两个独立的诉求时拆成两条记录。
- 如果本窗口的消息是在继续讨论 existing_records 里已有的某条（看「需求 / 问题」和「来源 message_id」判断），\
不要新建，放进 updates 追加讨论；只有明确是新的诉求才进 new_records。状态为「已完成」或「不做」的旧记录，若又被提起，也用 updates 追加，不要新建。
- 「为了解决什么」要克制：从上下文能推断就写，推断不出来写「待确认」，不要编。
- 「初步建议」：诉求具体、改动小、没有分歧 → 直接做；有多个相互竞争的方案、或根本问题不清楚、或涉及产品定位 → 需探讨；内容主要在图片 / 视频里而你没看清 → 待确认。
- 消息里带 images 时，可以直接打开 lark-im-resources/ 下的图片文件来看截图内容，再决定怎么写；files 里的 .mp4 视频无法查看，在讨论摘要里注明「附视频，未读」。
- 「产品」默认 {{product}}；如果明确是在说 Triboo Boom / G2，写 G2。
- 时间一律按消息里的 time（北京时间），输出格式 YYYY-MM-DD HH:mm:ss。
- 提出者、附议者只能用 participants 里出现过的 open_id；来源 message_id 只能用 messages 里出现过的 id；record_id 只能用 existing_records 里出现过的。
- 负责人（通常是畅涛）在群里对诉求的回应（「记下来了」「下个版本处理」「分区功能已有」）写进讨论摘要，不要单独立项。
- 如果整个窗口没有任何产品相关内容，输出 {{"new_records": [], "updates": [], "skipped_reason": "原因"}}。
{fb}
只创建 / 覆盖 output.json 这一个文件，不要修改其他文件。"""


def validate(output, inp):
    errors = []
    if not isinstance(output, dict):
        return ['output.json 不是 JSON 对象']
    for key in ('new_records', 'updates'):
        if key not in output or not isinstance(output[key], list):
            errors.append(f'缺少数组字段 {key}')
    if errors:
        return errors

    msg_ids = {m['id'] for m in inp.get('messages', [])}
    people = {p['id'] for p in inp.get('participants', [])}
    rec_ids = {r['record_id'] for r in inp.get('existing_records', [])}

    for i, r in enumerate(output['new_records']):
        tag = f'new_records[{i}]'
        if not isinstance(r, dict):
            errors.append(f'{tag} 不是对象')
            continue
        for k in ('需求 / 问题', '类型', '产品', '提出者', '提出时间', '原文链接', '来源 message_id'):
            if not r.get(k):
                errors.append(f'{tag} 缺少 {k}')
        if r.get('类型') and r['类型'] not in TYPES:
            errors.append(f'{tag} 类型非法：{r["类型"]}（可选：{TYPES}）')
        if r.get('产品') and r['产品'] not in PRODUCTS:
            errors.append(f'{tag} 产品非法：{r["产品"]}')
        if r.get('初步建议') and r['初步建议'] not in SUGGESTIONS:
            errors.append(f'{tag} 初步建议非法：{r["初步建议"]}')
        mods = r.get('涉及模块') or []
        if not isinstance(mods, list) or any(m not in MODULES for m in mods):
            errors.append(f'{tag} 涉及模块非法：{mods}')
        if r.get('提出者') and r['提出者'] not in people:
            errors.append(f'{tag} 提出者不在 participants 里：{r["提出者"]}')
        for s in r.get('附议者') or []:
            if s not in people:
                errors.append(f'{tag} 附议者不在 participants 里：{s}')
        ids = r.get('来源 message_id') or []
        if not isinstance(ids, list) or any(x not in msg_ids for x in ids):
            errors.append(f'{tag} 来源 message_id 含未知 id：{ids}')
        t = str(r.get('提出时间') or '')
        if len(t) == 16:
            r['提出时间'] = t + ':00'
        elif len(t) != 19:
            errors.append(f'{tag} 提出时间格式应为 YYYY-MM-DD HH:mm:ss：{t}')

    for i, u in enumerate(output['updates']):
        tag = f'updates[{i}]'
        if not isinstance(u, dict):
            errors.append(f'{tag} 不是对象')
            continue
        if u.get('record_id') not in rec_ids:
            errors.append(f'{tag} record_id 不在 existing_records 里：{u.get("record_id")}')
        if not (u.get('append_discussion') or u.get('add_supporters') or u.get('add_message_ids')):
            errors.append(f'{tag} 没有任何追加内容')
        for s in u.get('add_supporters') or []:
            if s not in people:
                errors.append(f'{tag} add_supporters 含未知 open_id：{s}')
        for x in u.get('add_message_ids') or []:
            if x not in msg_ids:
                errors.append(f'{tag} add_message_ids 含未知 id：{x}')
    return errors


def describe_result(result):
    parts = [f"status={getattr(result, 'status', '?')}"]
    for attr in ('id', 'agent_id', 'duration_ms', 'model'):
        value = getattr(result, attr, None)
        if value:
            parts.append(f'{attr}={value}')
    text = (getattr(result, 'result', '') or '').strip()
    if text:
        parts.append(f'result={text[:500]}')
    return ' | '.join(parts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', required=True)
    a = p.parse_args()
    run_dir = os.path.abspath(a.run)
    in_path = os.path.join(run_dir, 'input.json')
    out_path = os.path.join(run_dir, 'output.json')

    inp = load_json(in_path)
    if not inp:
        print(f'❌ 找不到 {in_path}')
        sys.exit(1)
    if not inp.get('messages'):
        save_json(out_path, {'new_records': [], 'updates': [], 'skipped_reason': '窗口内没有新消息'})
        print('ℹ️ 没有新消息，写出空结果')
        sys.exit(0)

    api_key = os.environ.get('CURSOR_API_KEY', '')
    if not api_key:
        print('⚠️ 未配置 CURSOR_API_KEY，无法进行 AI 提取')
        sys.exit(3)

    from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions

    product = inp.get('run', {}).get('product', 'G1')
    feedback = ''
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if os.path.exists(out_path):
            os.remove(out_path)
        print(f'🤖 AI 提取（第 {attempt}/{MAX_ATTEMPTS} 次）…')
        prompt = build_prompt(run_dir, feedback).replace('{product}', product)
        try:
            result = Agent.prompt(
                prompt,
                AgentOptions(api_key=api_key, model='auto', local=LocalAgentOptions(cwd=run_dir)),
            )
        except CursorAgentError as e:
            print(f'❌ 代理启动失败：{e!r}')
            result = None
        if result is None or result.status != 'finished':
            if result is not None:
                print(f'❌ 代理运行失败：{describe_result(result)}')
            feedback = ''
        else:
            try:
                output = load_json(out_path)
            except Exception as e:  # JSON 解析失败
                output = None
                feedback = f'output.json 不是合法 JSON：{e}'
            if output is None and not feedback:
                feedback = '没有生成 output.json'
            if output is not None:
                errors = validate(output, inp)
                if not errors:
                    save_json(out_path, output)  # 规范化写回（补秒等）
                    n, u = len(output['new_records']), len(output['updates'])
                    print(f'✅ 提取完成：新增 {n} 条，追加 {u} 条' + (f'；原因：{output.get("skipped_reason")}' if not n and not u else ''))
                    sys.exit(0)
                feedback = '\n'.join(f'- {e}' for e in errors[:30])
                print(f'⚠️ 输出未通过校验（{len(errors)} 处）：\n{feedback}')
        if attempt < MAX_ATTEMPTS:
            print(f'⏳ {RETRY_DELAY} 秒后重试…')
            time.sleep(RETRY_DELAY)

    if os.path.exists(out_path):
        os.remove(out_path)
    print('❌ AI 提取失败，放弃本次运行')
    sys.exit(2)


if __name__ == '__main__':
    main()
