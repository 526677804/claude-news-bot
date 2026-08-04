#!/usr/bin/env python3
"""
Claude Code 每日资讯采集脚本 v2.1
从多个可靠来源采集相关资讯，输出结构化原始数据供 AI 整理
v2.1: 增加采集重试机制
"""

import calendar
import json
import os
import subprocess
import requests
import time
import re
import feedparser
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, asdict
from html.parser import HTMLParser

# 部分站点（Reddit RSS、nitter 等）会拒绝非浏览器 UA
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
}


def fetch_feed(url: str, timeout: int = 20) -> feedparser.FeedParserDict:
    """带浏览器 UA 抓取并解析 RSS/Atom feed"""
    resp = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text or '').strip()


def entry_is_fresh(entry, max_age_hours: int) -> bool:
    """判断 feed 条目是否在时间窗口内；无时间信息时默认保留"""
    t = entry.get('published_parsed') or entry.get('updated_parsed')
    if not t:
        return True
    published = datetime.utcfromtimestamp(calendar.timegm(t))
    return datetime.utcnow() - published <= timedelta(hours=max_age_hours)


def load_env_var(name: str) -> str:
    """读取环境变量，取不到时尝试项目目录下的 .env 文件（KEY=VALUE 格式）"""
    value = os.environ.get(name, '')
    if value:
        return value
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
    return ''


def with_retry(func: Callable, max_retries: int = 2, retry_delay: int = 3) -> Callable:
    """
    重试装饰器：函数失败时自动重试
    """
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    print(f"   ⚠️  第 {attempt + 1} 次失败，{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                else:
                    print(f"   ❌ 重试 {max_retries} 次后仍然失败")
        raise last_exception
    return wrapper

@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    source_type: str  # official, media, community, tool
    reliability: str  # official, high, medium
    summary: str = ""
    published_at: str = ""
    score: int = 0
    category: str = "community"

class HTMLTextExtractor(HTMLParser):
    """提取 HTML 中的纯文本"""
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = False
    
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip = True
    
    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = False
    
    def handle_data(self, data):
        if not self.skip:
            self.text.append(data.strip())
    
    def get_text(self):
        return ' '.join(t for t in self.text if t)


def load_config() -> dict:
    """加载配置文件"""
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def match_keywords(text: str, keywords: List[str]) -> bool:
    """检查文本是否包含任一关键词"""
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True
    return False


def fetch_anthropic_blog(keywords: List[str]) -> List[NewsItem]:
    """从 Anthropic 官方博客采集"""
    items = []
    try:
        # 直接网页抓取（RSS 不稳定）
        url = "https://www.anthropic.com/news"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=20)
        
        if resp.status_code == 200:
            content = resp.text
            
            # 匹配文章链接和标题（h4 标题格式）
            pattern = r'<a[^>]+href="(/news/[a-zA-Z0-9-]+)"[^>]*>.*?<h4[^>]*>([^<]+)</h4>'
            matches = re.findall(pattern, content, re.DOTALL)
            
            seen = set()
            for path, title in matches:
                title = title.strip()
                if title and path not in seen:
                    seen.add(path)
                    full_url = f"https://www.anthropic.com{path}"
                    
                    # 官方博客的文章都算相关
                    item = NewsItem(
                        title=title,
                        url=full_url,
                        source='Anthropic 官方博客',
                        source_type='official',
                        reliability='official',
                        summary='官方发布',
                        score=100,
                        category='official'
                    )
                    items.append(item)
            
            # 如果 h4 格式没找到，尝试简单链接匹配
            if not items:
                pattern2 = r'href="(/news/[a-zA-Z0-9-]+)"'
                links = re.findall(pattern2, content)
                unique_links = list(set(links))
                for path in unique_links:
                    # 从路径生成标题
                    title = path.replace('/news/', '').replace('-', ' ').title()
                    full_url = f"https://www.anthropic.com{path}"
                    item = NewsItem(
                        title=title,
                        url=full_url,
                        source='Anthropic 官方博客',
                        source_type='official',
                        reliability='official',
                        summary='官方发布',
                        score=100,
                        category='official'
                    )
                    items.append(item)
    except Exception as e:
        print(f"Anthropic 博客采集失败: {e}")
    
    return items[:5]


def fetch_github_trending(keywords: List[str]) -> List[NewsItem]:
    """从 GitHub 采集相关项目"""
    items = []
    try:
        query = ' OR '.join(f'"{kw}"' for kw in keywords[:5])
        url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=20"
        headers = {'Accept': 'application/vnd.github.v3+json'}
        resp = requests.get(url, headers=headers, timeout=15)
        
        if resp.status_code == 200:
            data = resp.json()
            one_week_ago = datetime.now() - timedelta(days=7)
            
            for repo in data.get('items', []):
                created_at = datetime.strptime(repo['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                if created_at > one_week_ago or repo['stargazers_count'] > 100:
                    item = NewsItem(
                        title=f"[{repo['full_name']}] {repo.get('description', 'No description')}",
                        url=repo['html_url'],
                        source='GitHub',
                        source_type='tool',
                        reliability='high',
                        summary=f"⭐ {repo['stargazers_count']} stars · 语言: {repo.get('language', 'N/A')}",
                        published_at=repo['pushed_at'],
                        score=repo['stargazers_count'],
                        category='tools'
                    )
                    items.append(item)
    except Exception as e:
        print(f"GitHub 采集失败: {e}")
    
    return items[:10]


def fetch_hackernews(keywords: List[str]) -> List[NewsItem]:
    """从 Hacker News 采集（Algolia 搜索 API，一次请求覆盖近 48 小时）"""
    items = []
    seen_ids = set()
    since = int(time.time()) - 48 * 3600
    
    for query in ('claude', 'anthropic'):
        try:
            url = (f"https://hn.algolia.com/api/v1/search_by_date"
                   f"?query={query}&tags=story"
                   f"&numericFilters=created_at_i>{since}&hitsPerPage=50")
            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            
            for hit in resp.json().get('hits', []):
                story_id = hit.get('objectID', '')
                title = hit.get('title') or ''
                if story_id in seen_ids or not title:
                    continue
                if not match_keywords(title, keywords):
                    continue
                seen_ids.add(story_id)
                
                items.append(NewsItem(
                    title=title,
                    url=hit.get('url') or f"https://news.ycombinator.com/item?id={story_id}",
                    source='Hacker News',
                    source_type='community',
                    reliability='high',
                    summary=f"👍 {hit.get('points', 0)} points · 💬 {hit.get('num_comments', 0)} comments",
                    published_at=hit.get('created_at', ''),
                    score=hit.get('points', 0) or 0,
                    category='community'
                ))
        except Exception as e:
            print(f"Hacker News ({query}) 采集失败: {e}")
        time.sleep(0.5)
    
    return sorted(items, key=lambda x: x.score, reverse=True)[:10]


def fetch_techcrunch(keywords: List[str]) -> List[NewsItem]:
    """从 TechCrunch 采集"""
    items = []
    try:
        feed_url = "https://techcrunch.com/category/artificial-intelligence/feed/"
        feed = feedparser.parse(feed_url)
        
        for entry in feed.entries[:15]:
            title = entry.get('title', '')
            if match_keywords(title, keywords):
                item = NewsItem(
                    title=title,
                    url=entry.get('link', ''),
                    source='TechCrunch',
                    source_type='media',
                    reliability='high',
                    summary=entry.get('summary', '')[:200],
                    published_at=entry.get('published', ''),
                    score=50,
                    category='industry'
                )
                items.append(item)
    except Exception as e:
        print(f"TechCrunch 采集失败: {e}")
    
    return items[:5]


def fetch_theverge(keywords: List[str]) -> List[NewsItem]:
    """从 The Verge 采集"""
    items = []
    try:
        feed_url = "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"
        feed = feedparser.parse(feed_url)
        
        for entry in feed.entries[:15]:
            title = entry.get('title', '')
            if match_keywords(title, keywords):
                item = NewsItem(
                    title=title,
                    url=entry.get('link', ''),
                    source='The Verge',
                    source_type='media',
                    reliability='high',
                    summary=entry.get('summary', '')[:200],
                    published_at=entry.get('published', ''),
                    score=50,
                    category='industry'
                )
                items.append(item)
    except Exception as e:
        print(f"The Verge 采集失败: {e}")
    
    return items[:5]


def fetch_arstechnica(keywords: List[str]) -> List[NewsItem]:
    """从 Ars Technica 采集"""
    items = []
    try:
        feed_url = "https://feeds.arstechnica.com/arstechnica/technology-lab"
        feed = feedparser.parse(feed_url)
        
        for entry in feed.entries[:15]:
            title = entry.get('title', '')
            if match_keywords(title, keywords):
                item = NewsItem(
                    title=title,
                    url=entry.get('link', ''),
                    source='Ars Technica',
                    source_type='media',
                    reliability='high',
                    summary=entry.get('summary', '')[:200],
                    published_at=entry.get('published', ''),
                    score=50,
                    category='industry'
                )
                items.append(item)
    except Exception as e:
        print(f"Ars Technica 采集失败: {e}")
    
    return items[:5]


def fetch_reddit(keywords: List[str], subreddits: List[str]) -> List[NewsItem]:
    """
    从 Reddit 采集（RSS 端点，JSON API 已被封禁）
    配置中的 subreddit 均为 Claude 专属社区，热帖默认相关，不做关键词过滤
    """
    items = []
    
    for subreddit in subreddits:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.rss?limit=25"
            try:
                feed = fetch_feed(url)
            except requests.HTTPError as e:
                # Reddit 429 是 IP 级限流，短暂退避后重试一次
                if e.response is not None and e.response.status_code == 429:
                    print(f"   ⚠️ r/{subreddit} 被限流，30 秒后重试...")
                    time.sleep(30)
                    feed = fetch_feed(url)
                else:
                    raise
            
            for rank, entry in enumerate(feed.entries[:15]):
                title = entry.get('title', '')
                if not title:
                    continue
                
                items.append(NewsItem(
                    title=title,
                    url=entry.get('link', ''),
                    source=f"r/{subreddit}",
                    source_type='community',
                    reliability='medium',
                    summary=strip_html(entry.get('summary', ''))[:200],
                    published_at=entry.get('published', ''),
                    # RSS 不带票数，按热榜位置估分
                    score=30 - rank,
                    category='community'
                ))
        except Exception as e:
            print(f"Reddit r/{subreddit} 采集失败: {e}")
        # Reddit 对连续请求限流严格，拉大间隔
        time.sleep(5)
    
    return sorted(items, key=lambda x: x.score, reverse=True)[:10]


def fetch_v2ex(keywords: List[str], nodes: List[str]) -> List[NewsItem]:
    """从 V2EX 采集"""
    items = []
    headers = {'User-Agent': 'ClaudeNewsBot/2.0'}
    
    for node in nodes:
        try:
            url = f"https://www.v2ex.com/api/topics/hot.json?node_name={node}"
            resp = requests.get(url, headers=headers, timeout=15)
            
            if resp.status_code == 200:
                topics = resp.json()
                for topic in topics:
                    title = topic.get('title', '')
                    content = topic.get('content', '')
                    
                    if match_keywords(title + ' ' + content, keywords):
                        item = NewsItem(
                            title=title,
                            url=topic.get('url', ''),
                            source=f"V2EX - {node}",
                            source_type='community',
                            reliability='medium',
                            summary=f"👍 {topic.get('replies', 0)} 回复",
                            score=topic.get('replies', 0),
                            category='community'
                        )
                        items.append(item)
        except Exception as e:
            print(f"V2EX {node} 采集失败: {e}")
        time.sleep(1)
    
    return sorted(items, key=lambda x: x.score, reverse=True)[:10]


# X 采集统计，供 main() 判断是否需要告警
TWITTER_STATS = {'total_accounts': 0, 'failed_accounts': 0, 'method': ''}


def fetch_tweets_via_api(account: str, api_cfg: dict, api_key: str,
                         max_age_hours: int) -> List[dict]:
    """
    通过 twitterapi.io 获取账号最新推文
    返回标准化的 dict 列表：{title, url, summary, published_at, engagement}
    """
    base_url = api_cfg.get('base_url', 'https://api.twitterapi.io')
    resp = None
    # twitterapi.io 有 QPS 限流，429 时退避重试
    for attempt in range(3):
        resp = requests.get(
            f"{base_url}/twitter/user/last_tweets",
            params={'userName': account},
            headers={'X-API-Key': api_key},
            timeout=20
        )
        if resp.status_code == 429 and attempt < 2:
            time.sleep(5 * (attempt + 1))
            continue
        break
    resp.raise_for_status()
    data = resp.json()
    
    if data.get('status') == 'error':
        raise RuntimeError(data.get('message', 'twitterapi.io 返回错误'))
    
    # 实际返回中 tweets 可能在顶层或 data 内，两种都兼容
    tweets = data.get('tweets') or data.get('data', {}).get('tweets') or []
    
    results = []
    now = datetime.now(timezone.utc)
    for tw in tweets:
        if tw.get('isReply'):
            continue
        # createdAt 格式如 "Tue Dec 10 07:00:30 +0000 2024"
        created_str = tw.get('createdAt', '')
        try:
            created = datetime.strptime(created_str, '%a %b %d %H:%M:%S %z %Y')
            if now - created > timedelta(hours=max_age_hours):
                continue
        except ValueError:
            pass
        
        text = (tw.get('text') or '').strip()
        if not text:
            continue
        
        engagement = (tw.get('likeCount', 0) or 0) + (tw.get('retweetCount', 0) or 0) * 2
        results.append({
            'title': text.replace('\n', ' '),
            'url': tw.get('url', ''),
            'summary': text[:200],
            'published_at': created_str,
            'engagement': engagement,
        })
    return results


def fetch_tweets_via_nitter(account: str, instances: List[str],
                            max_age_hours: int) -> List[dict]:
    """
    通过 nitter 实例的 RSS 获取账号最新推文（API 不可用时的回退方案）
    返回与 fetch_tweets_via_api 相同结构的 dict 列表
    """
    feed = None
    for instance in instances:
        try:
            candidate = fetch_feed(f"{instance}/{account}/rss")
            if candidate.entries:
                feed = candidate
                break
        except Exception:
            continue
    
    if feed is None:
        raise RuntimeError('所有 nitter 实例均无法获取')
    
    results = []
    for entry in feed.entries[:20]:
        title = strip_html(entry.get('title', ''))
        # 跳过回复（nitter 中回复标题以 "R to @xxx:" 开头）
        if title.startswith('R to @'):
            continue
        if not entry_is_fresh(entry, max_age_hours):
            continue
        
        # nitter 链接转回 x.com 原始链接
        url = entry.get('link', '')
        url = re.sub(r'https?://[^/]+/', 'https://x.com/', url, count=1)
        url = url.replace('#m', '')
        
        results.append({
            'title': title,
            'url': url,
            'summary': strip_html(entry.get('summary', ''))[:200],
            'published_at': entry.get('published', ''),
            'engagement': 0,
        })
    return results


def fetch_twitter(keywords: List[str], twitter_config: dict) -> List[NewsItem]:
    """
    从 X (Twitter) 采集指定账号的推文
    优先走 twitterapi.io（需配置 API key），失败或未配置时回退 nitter RSS
    账号按分组配置：官方/核心团队不做关键词过滤，创始人/研究员按关键词过滤
    """
    items = []
    api_cfg = twitter_config.get('api_provider', {})
    api_key = load_env_var(api_cfg.get('api_key_env', 'TWITTERAPI_IO_KEY')) if api_cfg else ''
    instances = twitter_config.get('nitter_instances', ['https://nitter.net'])
    max_age_hours = twitter_config.get('max_age_hours', 36)
    account_groups = twitter_config.get('account_groups', {})
    
    if api_key:
        print(f"   使用 {api_cfg.get('name', 'API')} 采集（nitter 作为回退）")
        TWITTER_STATS['method'] = 'api'
    else:
        print("   未配置 X API key，使用 nitter RSS 采集")
        TWITTER_STATS['method'] = 'nitter'
    
    TWITTER_STATS['total_accounts'] = 0
    TWITTER_STATS['failed_accounts'] = 0
    
    for group_key, group in account_groups.items():
        group_name = group.get('name', group_key)
        need_filter = group.get('filter_by_keywords', True)
        base_score = group.get('score', 60)
        
        for account in group.get('accounts', []):
            TWITTER_STATS['total_accounts'] += 1
            tweets = None
            
            if api_key:
                try:
                    tweets = fetch_tweets_via_api(account, api_cfg, api_key, max_age_hours)
                except Exception as e:
                    print(f"   ⚠️ X @{account} API 采集失败（{e}），尝试 nitter 回退...")
            
            if tweets is None:
                try:
                    tweets = fetch_tweets_via_nitter(account, instances, max_age_hours)
                except Exception:
                    print(f"   ❌ X @{account} 所有采集途径均失败")
                    TWITTER_STATS['failed_accounts'] += 1
                    time.sleep(1)
                    continue
            
            for tw in tweets:
                if need_filter and not match_keywords(tw['title'] + ' ' + tw['summary'], keywords):
                    continue
                
                items.append(NewsItem(
                    title=f"@{account}: {tw['title'][:100]}",
                    url=tw['url'],
                    source=f"X - @{account} ({group_name})",
                    source_type='kol',
                    reliability='high',
                    summary=tw['summary'],
                    published_at=tw['published_at'],
                    # 分组基础分 + 互动热度加成（封顶 20）
                    score=base_score + min(tw['engagement'] // 100, 20),
                    category='community'
                ))
            time.sleep(1)
    
    return sorted(items, key=lambda x: x.score, reverse=True)[:20]


def fetch_claude_code_releases(keywords: List[str], url: str) -> List[NewsItem]:
    """从 GitHub Releases feed 采集 Claude Code 版本发布（官方变更日志）"""
    items = []
    try:
        feed = fetch_feed(url)
        for entry in feed.entries[:5]:
            if not entry_is_fresh(entry, 48):
                continue
            items.append(NewsItem(
                title=f"Claude Code 发布 {entry.get('title', '')}",
                url=entry.get('link', ''),
                source='Claude Code Releases',
                source_type='official',
                reliability='official',
                summary=strip_html(entry.get('summary', ''))[:300],
                published_at=entry.get('published', entry.get('updated', '')),
                score=95,
                category='official'
            ))
    except Exception as e:
        print(f"Claude Code Releases 采集失败: {e}")
    
    return items[:3]


def fetch_kol_blogs(keywords: List[str], feeds: List[dict]) -> List[NewsItem]:
    """从权威 KOL 博客的 RSS 采集（如 Simon Willison）"""
    items = []
    
    for feed_cfg in feeds:
        name = feed_cfg.get('name', '')
        try:
            feed = fetch_feed(feed_cfg['url'])
            for entry in feed.entries[:20]:
                if not entry_is_fresh(entry, 48):
                    continue
                title = entry.get('title', '')
                summary = strip_html(entry.get('summary', ''))[:200]
                if not match_keywords(title + ' ' + summary, keywords):
                    continue
                
                items.append(NewsItem(
                    title=title,
                    url=entry.get('link', ''),
                    source=name,
                    source_type='kol',
                    reliability='high',
                    summary=summary,
                    published_at=entry.get('published', ''),
                    score=60,
                    category='community'
                ))
        except Exception as e:
            print(f"KOL 博客 {name} 采集失败: {e}")
        time.sleep(1)
    
    return items[:10]


def deduplicate_items(items: List[NewsItem]) -> List[NewsItem]:
    """去重"""
    seen_urls = set()
    seen_titles = set()
    result = []
    
    for item in items:
        if item.url in seen_urls:
            continue
        
        title_key = item.title[:30].lower()
        if title_key in seen_titles:
            continue
        
        seen_urls.add(item.url)
        seen_titles.add(title_key)
        result.append(item)
    
    return result


def send_admin_alert(config: dict, alert_msg: str) -> bool:
    """通过 lark-cli 给管理员发采集异常告警私信"""
    admin_user_id = config.get('feishu', {}).get('admin_user_id', '')
    if not admin_user_id:
        return False
    
    text = f"""⚠️ Claude Code 资讯采集异常

时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{alert_msg}

请检查采集日志和信息源状态（可运行 test_sources.py 复测）。""".strip()
    
    try:
        result = subprocess.run(
            ['lark-cli', 'im', '+messages-send', '--as', 'bot',
             '--user-id', admin_user_id, '--text', text],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print("   📢 已私信告警给管理员")
            return True
        print(f"   ❌ 告警发送失败: {result.stderr}")
    except Exception as e:
        print(f"   ❌ 告警发送异常: {e}")
    return False


def safe_fetch(fetch_func, *args, source_name: str = "", max_retries: int = 2) -> List[NewsItem]:
    """
    安全采集：失败时自动重试，最终失败返回空列表
    """
    try:
        retry_func = with_retry(fetch_func, max_retries=max_retries)
        return retry_func(*args)
    except Exception as e:
        print(f"   ❌ {source_name} 采集失败: {e}")
        return []


def main():
    """主函数 - 采集原始数据并保存为 JSON"""
    print("🚀 开始采集 Claude Code 相关资讯 v2.1...")
    
    config = load_config()
    keywords = config['keywords']
    sources = config['sources']
    retry_config = config.get('retry', {'max_retries': 2, 'retry_delay': 3})
    
    all_items = []
    
    # 1. 官方博客（高优先级，重试 3 次）
    if sources.get('official_blog', {}).get('enabled'):
        print("📡 采集 Anthropic 官方博客...")
        items = safe_fetch(fetch_anthropic_blog, keywords, 
                          source_name="Anthropic 官方博客", 
                          max_retries=3)
        print(f"   找到 {len(items)} 条")
        all_items.extend(items)
    
    # 2. Claude Code 版本发布（官方，重试 2 次）
    if sources.get('claude_code_releases', {}).get('enabled'):
        print("📡 采集 Claude Code Releases...")
        items = safe_fetch(fetch_claude_code_releases, keywords,
                          sources['claude_code_releases']['url'],
                          source_name="Claude Code Releases",
                          max_retries=retry_config['max_retries'])
        print(f"   找到 {len(items)} 条")
        all_items.extend(items)
    
    # 3. GitHub（高优先级，重试 2 次）
    if sources.get('github', {}).get('enabled'):
        print("📡 采集 GitHub...")
        items = safe_fetch(fetch_github_trending, keywords,
                          source_name="GitHub",
                          max_retries=retry_config['max_retries'])
        print(f"   找到 {len(items)} 条")
        all_items.extend(items)
    
    # 4. Hacker News（Algolia API，重试 2 次）
    if sources.get('hackernews', {}).get('enabled'):
        print("📡 采集 Hacker News...")
        items = safe_fetch(fetch_hackernews, keywords,
                          source_name="Hacker News",
                          max_retries=retry_config['max_retries'])
        print(f"   找到 {len(items)} 条")
        all_items.extend(items)
    
    # 5. TechCrunch（重试 2 次）
    if sources.get('techcrunch', {}).get('enabled'):
        print("📡 采集 TechCrunch...")
        items = safe_fetch(fetch_techcrunch, keywords,
                          source_name="TechCrunch",
                          max_retries=retry_config['max_retries'])
        print(f"   找到 {len(items)} 条")
        all_items.extend(items)
    
    # 6. The Verge（重试 2 次）
    if sources.get('theverge', {}).get('enabled'):
        print("📡 采集 The Verge...")
        items = safe_fetch(fetch_theverge, keywords,
                          source_name="The Verge",
                          max_retries=retry_config['max_retries'])
        print(f"   找到 {len(items)} 条")
        all_items.extend(items)
    
    # 7. Ars Technica（重试 2 次）
    if sources.get('arstechnica', {}).get('enabled'):
        print("📡 采集 Ars Technica...")
        items = safe_fetch(fetch_arstechnica, keywords,
                          source_name="Ars Technica",
                          max_retries=retry_config['max_retries'])
        print(f"   找到 {len(items)} 条")
        all_items.extend(items)
    
    # 8. Reddit（RSS 方式，重试 1 次）
    if sources.get('reddit', {}).get('enabled'):
        print("📡 采集 Reddit...")
        items = safe_fetch(fetch_reddit, keywords, sources['reddit']['subreddits'],
                          source_name="Reddit",
                          max_retries=1)
        print(f"   找到 {len(items)} 条")
        all_items.extend(items)
    
    # 9. V2EX（默认禁用，重试 1 次）
    if sources.get('v2ex', {}).get('enabled'):
        print("📡 采集 V2EX...")
        items = safe_fetch(fetch_v2ex, keywords, sources['v2ex']['nodes'],
                          source_name="V2EX",
                          max_retries=1)
        print(f"   找到 {len(items)} 条")
        all_items.extend(items)
    
    # 10. X (Twitter) 账号（API 优先 + nitter 回退，重试 1 次）
    if sources.get('twitter', {}).get('enabled'):
        print("📡 采集 X (Twitter) 账号...")
        items = safe_fetch(fetch_twitter, keywords, sources['twitter'],
                          source_name="X (Twitter)",
                          max_retries=1)
        print(f"   找到 {len(items)} 条")
        all_items.extend(items)
        
        # X 采集健康检查：全部账号失败 → 告警；部分失败且 0 条 → 也告警
        total = TWITTER_STATS['total_accounts']
        failed = TWITTER_STATS['failed_accounts']
        if total > 0:
            if failed >= total:
                send_admin_alert(config,
                    f"X 信息源采集全部失败（{failed}/{total} 个账号，方式：{TWITTER_STATS['method']}），"
                    f"twitterapi.io 和 nitter 可能都已失效。")
            elif failed > 0 and len(items) == 0:
                send_admin_alert(config,
                    f"X 信息源采集 0 条，且 {failed}/{total} 个账号采集失败（方式：{TWITTER_STATS['method']}），"
                    f"请确认采集途径是否部分失效。")
    
    # 11. KOL 博客（重试 2 次）
    if sources.get('kol_blogs', {}).get('enabled'):
        print("📡 采集 KOL 博客...")
        items = safe_fetch(fetch_kol_blogs, keywords,
                          sources['kol_blogs'].get('feeds', []),
                          source_name="KOL 博客",
                          max_retries=retry_config['max_retries'])
        print(f"   找到 {len(items)} 条")
        all_items.extend(items)
    
    # 去重
    print(f"\n🔍 去重前: {len(all_items)} 条")
    all_items = deduplicate_items(all_items)
    print(f"🔍 去重后: {len(all_items)} 条")
    
    # 按分类整理
    categorized = {}
    for item in all_items:
        cat = item.category
        if cat not in categorized:
            categorized[cat] = []
        categorized[cat].append(asdict(item))
    
    # 按分数排序
    for cat in categorized:
        categorized[cat] = sorted(categorized[cat], key=lambda x: x['score'], reverse=True)
    
    # 保存原始数据为 JSON，供 AI 整理使用
    today = datetime.now().strftime('%Y%m%d')
    raw_data = {
        'date': today,
        'total_count': len(all_items),
        'items': [asdict(item) for item in all_items],
        'categorized': categorized
    }
    
    output_file = f"raw_news_{today}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 原始数据采集完成！已保存到: {output_file}")
    print(f"   总计: {len(all_items)} 条资讯")
    
    # 打印统计
    print("\n📊 分类统计:")
    for cat, items in categorized.items():
        print(f"   {cat}: {len(items)} 条")
    
    return raw_data


if __name__ == '__main__':
    main()
