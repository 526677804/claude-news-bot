#!/usr/bin/env python3
"""
测试所有信息源是否正常工作
"""
import json
import requests
import feedparser
import time
from datetime import datetime

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
}

def test_source(name, test_func, timeout=15):
    """测试单个信息源"""
    print(f"\n{'='*50}")
    print(f"测试: {name}")
    print(f"{'='*50}")
    
    start_time = time.time()
    try:
        result = test_func(timeout)
        elapsed = time.time() - start_time
        count = len(result) if result else 0
        print(f"✅ 成功! 耗时: {elapsed:.1f}s, 获取: {count} 条")
        if result and count > 0:
            print(f"   示例: {result[0]['title'][:60]}...")
        return True, result
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 失败! 耗时: {elapsed:.1f}s, 错误: {e}")
        return False, str(e)

def test_anthropic_blog(timeout):
    """测试 Anthropic 官方博客"""
    # 测试 RSS
    feed_url = "https://www.anthropic.com/news/rss.xml"
    feed = feedparser.parse(feed_url)
    items = []
    for entry in feed.entries[:5]:
        items.append({
            'title': entry.get('title', ''),
            'url': entry.get('link', '')
        })
    return items

def test_github(timeout):
    """测试 GitHub"""
    url = "https://api.github.com/search/repositories?q=claude+code&sort=stars&per_page=5"
    headers = {'Accept': 'application/vnd.github.v3+json'}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    items = []
    for repo in data.get('items', [])[:5]:
        items.append({
            'title': repo['full_name'],
            'url': repo['html_url']
        })
    return items

def test_hackernews(timeout):
    """测试 Hacker News（Algolia 搜索 API）"""
    since = int(time.time()) - 48 * 3600
    url = (f"https://hn.algolia.com/api/v1/search_by_date"
           f"?query=claude&tags=story&numericFilters=created_at_i>{since}&hitsPerPage=5")
    resp = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
    resp.raise_for_status()
    items = []
    for hit in resp.json().get('hits', [])[:5]:
        items.append({
            'title': hit.get('title', ''),
            'url': hit.get('url', '')
        })
    return items

def test_techcrunch(timeout):
    """测试 TechCrunch"""
    feed_url = "https://techcrunch.com/category/artificial-intelligence/feed/"
    feed = feedparser.parse(feed_url)
    items = []
    for entry in feed.entries[:5]:
        items.append({
            'title': entry.get('title', ''),
            'url': entry.get('link', '')
        })
    return items

def test_theverge(timeout):
    """测试 The Verge"""
    feed_url = "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"
    feed = feedparser.parse(feed_url)
    items = []
    for entry in feed.entries[:5]:
        items.append({
            'title': entry.get('title', ''),
            'url': entry.get('link', '')
        })
    return items

def test_arstechnica(timeout):
    """测试 Ars Technica"""
    feed_url = "https://feeds.arstechnica.com/arstechnica/technology-lab"
    feed = feedparser.parse(feed_url)
    items = []
    for entry in feed.entries[:5]:
        items.append({
            'title': entry.get('title', ''),
            'url': entry.get('link', '')
        })
    return items

def test_reddit(timeout):
    """测试 Reddit（RSS 端点）"""
    url = "https://www.reddit.com/r/ClaudeAI/hot.rss?limit=5"
    resp = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries[:5]:
        items.append({
            'title': entry.get('title', ''),
            'url': entry.get('link', '')
        })
    return items

def test_v2ex(timeout):
    """测试 V2EX"""
    url = "https://www.v2ex.com/api/topics/hot.json?node_name=programmer"
    headers = {'User-Agent': 'ClaudeNewsBot/2.0'}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    topics = resp.json()
    items = []
    for topic in topics[:5]:
        items.append({
            'title': topic.get('title', ''),
            'url': topic.get('url', '')
        })
    return items

def test_twitter(timeout):
    """测试 X (Twitter) via nitter（回退途径）"""
    feed_url = "https://nitter.net/claudeai/rss"
    resp = requests.get(feed_url, headers=BROWSER_HEADERS, timeout=timeout)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries[:5]:
        items.append({
            'title': entry.get('title', ''),
            'url': entry.get('link', '')
        })
    return items


def test_twitter_api(timeout):
    """测试 X (Twitter) via twitterapi.io（主途径）"""
    from fetch_news import load_env_var
    api_key = load_env_var('TWITTERAPI_IO_KEY')
    if not api_key:
        raise Exception('未配置 TWITTERAPI_IO_KEY（写入 .env 文件或环境变量）')
    resp = requests.get(
        'https://api.twitterapi.io/twitter/user/last_tweets',
        params={'userName': 'claudeai'},
        headers={'X-API-Key': api_key},
        timeout=timeout
    )
    resp.raise_for_status()
    data = resp.json()
    tweets = data.get('tweets') or data.get('data', {}).get('tweets') or []
    return [{'title': (t.get('text') or '')[:80], 'url': t.get('url', '')} for t in tweets[:5]]


def test_claude_code_releases(timeout):
    """测试 Claude Code GitHub Releases feed"""
    url = "https://github.com/anthropics/claude-code/releases.atom"
    resp = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries[:5]:
        items.append({
            'title': entry.get('title', ''),
            'url': entry.get('link', '')
        })
    return items


def test_simonwillison(timeout):
    """测试 Simon Willison 博客"""
    url = "https://simonwillison.net/atom/everything/"
    resp = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries[:5]:
        items.append({
            'title': entry.get('title', ''),
            'url': entry.get('link', '')
        })
    return items

def main():
    print("🚀 开始测试所有信息源...")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    # 逐个测试
    tests = [
        ("Anthropic 官方博客", test_anthropic_blog),
        ("Claude Code Releases", test_claude_code_releases),
        ("GitHub", test_github),
        ("Hacker News (Algolia)", test_hackernews),
        ("TechCrunch", test_techcrunch),
        ("The Verge", test_theverge),
        ("Ars Technica", test_arstechnica),
        ("Reddit (RSS)", test_reddit),
        ("X (Twitter) via twitterapi.io", test_twitter_api),
        ("X (Twitter) via nitter (回退)", test_twitter),
        ("Simon Willison 博客", test_simonwillison),
    ]
    
    for name, test_func in tests:
        success, result = test_source(name, test_func, timeout=10)
        results[name] = {
            'success': success,
            'result': result
        }
        time.sleep(1)  # 避免请求过快
    
    # 汇总
    print(f"\n\n{'='*60}")
    print("📊 测试结果汇总")
    print(f"{'='*60}")
    
    success_count = 0
    fail_count = 0
    
    for name, data in results.items():
        status = "✅" if data['success'] else "❌"
        if data['success']:
            success_count += 1
            count = len(data['result']) if data['result'] else 0
            print(f"{status} {name}: 成功 ({count} 条)")
        else:
            fail_count += 1
            print(f"{status} {name}: 失败 - {data['result']}")
    
    print(f"\n总计: {success_count} 成功, {fail_count} 失败")

if __name__ == '__main__':
    main()
