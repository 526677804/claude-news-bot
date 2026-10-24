/**
 * G1 内测反馈 · 云端触发器（Cloudflare Worker）
 *
 * 两个入口，都只做一件事：调 GitHub API 派发 g1-feedback.yml（真正的整理在 GitHub Actions 里跑）。
 *   1. 定时：wrangler.toml 里的 cron（UTC 10:30 = 北京 18:30）→ 每日整理
 *   2. HTTP：飞书事件订阅（im.message.receive_v1）→ 群里 @机器人 或管理员私聊 → 立刻整理
 *
 * 需要的变量 / 密钥（wrangler secret put）：
 *   GITHUB_TOKEN              fine-grained PAT，仅对 claude-news-bot 仓库、Actions: Read and write
 *   FEISHU_VERIFICATION_TOKEN 飞书开发者后台「事件与回调 → 加密策略」里的 Verification Token（可选但建议）
 *   FEISHU_ENCRYPT_KEY        同页的 Encrypt Key；没配加密就留空
 * 普通变量在 wrangler.toml 的 [vars]：GITHUB_REPO、WORKFLOW_FILE、GROUP_CHAT_ID、ADMIN_DM_CHAT_ID、BOT_OPEN_ID
 */

const TRIGGER_WORDS = ['记一下', '记录', '整理', '收录', '更新一下', 'record', 'sync'];
const IGNORE_WORDS = ['状态', 'status', '帮助', 'help'];

export default {
  async scheduled(event, env, ctx) {
    // 一个 Worker 可以挂多条定时：按触发的 cron 表达式查 SCHEDULES（见 wrangler.toml），
    // 没匹配到的默认跑 G1 自己的管线。日报等其他仓库的定时也可以加进来共用。
    let schedules = {};
    try {
      schedules = JSON.parse(env.SCHEDULES || '{}');
    } catch {
      schedules = {};
    }
    const job = schedules[event.cron] || { repo: env.GITHUB_REPO, workflow: env.WORKFLOW_FILE, inputs: { manual: 'false' } };
    ctx.waitUntil(dispatch(env, job.inputs || {}, `cron ${event.cron}`, job.repo, job.workflow));
  },

  async fetch(request, env, ctx) {
    if (request.method !== 'POST') {
      return new Response('g1-feedback-trigger ok', { status: 200 });
    }
    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: 'bad json' }, 400);
    }
    if (body.encrypt) {
      if (!env.FEISHU_ENCRYPT_KEY) return json({ error: 'encrypted payload but no FEISHU_ENCRYPT_KEY' }, 400);
      try {
        body = JSON.parse(await decrypt(body.encrypt, env.FEISHU_ENCRYPT_KEY));
      } catch (e) {
        return json({ error: 'decrypt failed' }, 400);
      }
    }

    // 1. 飞书配置回调地址时的一次性校验
    if (body.type === 'url_verification') {
      if (env.FEISHU_VERIFICATION_TOKEN && body.token !== env.FEISHU_VERIFICATION_TOKEN) {
        return json({ error: 'bad token' }, 403);
      }
      return json({ challenge: body.challenge });
    }

    // 2. 事件推送（v2.0 schema）
    const header = body.header || {};
    if (env.FEISHU_VERIFICATION_TOKEN && header.token !== env.FEISHU_VERIFICATION_TOKEN) {
      return json({ error: 'bad token' }, 403);
    }
    if (header.event_type !== 'im.message.receive_v1') {
      return json({ ok: true, ignored: header.event_type || 'unknown' });
    }
    const ev = body.event || {};
    const msg = ev.message || {};
    const sender = ev.sender || {};
    const senderId = (sender.sender_id || {}).open_id || '';
    if (sender.sender_type !== 'user' || senderId === env.BOT_OPEN_ID) {
      return json({ ok: true, ignored: 'not a user' });
    }
    if (!['text', 'post'].includes(msg.message_type)) {
      return json({ ok: true, ignored: msg.message_type });
    }

    const inGroup = msg.chat_id === env.GROUP_CHAT_ID;
    const inAdminDm = msg.chat_type === 'p2p' && (!env.ADMIN_DM_CHAT_ID || msg.chat_id === env.ADMIN_DM_CHAT_ID);
    if (!inGroup && !inAdminDm) {
      return json({ ok: true, ignored: 'other chat' });
    }
    if (inGroup) {
      const mentioned = (msg.mentions || []).some((m) => ((m.id || {}).open_id || '') === env.BOT_OPEN_ID);
      if (!mentioned) return json({ ok: true, ignored: 'not mentioned' });
    }

    const text = extractText(msg.content).toLowerCase();
    if (IGNORE_WORDS.some((w) => text.includes(w))) {
      return json({ ok: true, ignored: 'status/help' });
    }
    // 群里 @ 了就触发（不强求关键词，避免大家记不住口令）；私聊里也是任意文字触发
    void TRIGGER_WORDS;

    const inputs = { manual: 'true', ack_to: msg.message_id || '' };
    if (inGroup && msg.message_id) inputs.reply_to = msg.message_id;
    ctx.waitUntil(dispatch(env, inputs, inGroup ? 'group-mention' : 'admin-dm'));
    return json({ ok: true, dispatched: true });
  },
};

function extractText(content) {
  if (!content) return '';
  try {
    const obj = JSON.parse(content);
    if (typeof obj.text === 'string') return obj.text.replace(/@_user_\d+/g, ' ');
    // post：{"zh_cn":{"title":"","content":[[{"tag":"text","text":"..."}]]}}
    const locale = obj.zh_cn || obj.en_us || Object.values(obj)[0] || {};
    const parts = [];
    for (const line of locale.content || []) for (const seg of line) if (seg.text) parts.push(seg.text);
    return parts.join(' ');
  } catch {
    return String(content);
  }
}

async function dispatch(env, inputs, reason, repo = env.GITHUB_REPO, workflow = env.WORKFLOW_FILE) {
  const url = `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'g1-feedback-trigger',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ref: 'main', inputs }),
  });
  console.log(`dispatch(${reason}) → ${res.status}`, JSON.stringify(inputs));
  if (res.status !== 204) console.log(await res.text());
}

async function decrypt(encrypted, key) {
  const raw = Uint8Array.from(atob(encrypted), (c) => c.charCodeAt(0));
  const keyBytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(key));
  const cryptoKey = await crypto.subtle.importKey('raw', keyBytes, { name: 'AES-CBC' }, false, ['decrypt']);
  const plain = await crypto.subtle.decrypt({ name: 'AES-CBC', iv: raw.slice(0, 16) }, cryptoKey, raw.slice(16));
  return new TextDecoder().decode(plain);
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
}
