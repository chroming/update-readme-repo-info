import os
import re
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

README_PATH = os.getenv('README_PATH', 'README.md')
GITHUB_API = 'https://api.github.com/repos/'
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

class RepoInfoFetcher:
    """
    Fetches repository information from GitHub API. Easily extensible for more fields.
    """
    def __init__(self, token=None):
        self.session = requests.Session()
        if token:
            self.session.headers['Authorization'] = f'Bearer {token}'
        self.session.headers['Accept'] = 'application/vnd.github+json'

    def fetch(self, owner, repo):
        url = f'{GITHUB_API}{owner}/{repo}'
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            logging.warning(f'Failed to fetch {owner}/{repo}: {e}')
            return None
        data = resp.json()
        return {
            'stars': data.get('stargazers_count', 0),
            'updated': data.get('updated_at', '')
        }

REPO_LINK_RE = re.compile(r'(https://github.com/[\w.-]+/[\w.-]+)')


def parse_repo_links(text):
    """
    Returns a list of (full_url, owner, repo) tuples for all GitHub repo links in the text.
    """
    links = set()
    for match in REPO_LINK_RE.finditer(text):
        full_url = match.group(1)
        parts = full_url.rstrip('/').split('/')
        if len(parts) >= 5:
            owner, repo = parts[3], parts[4]
            links.add((full_url, owner, repo))
    return list(links)

def format_info(info):
    """
    Formats the repository info for display after the link.
    """
    if not info:
        return '(fetch failed)'
    updated = info['updated']
    if updated:
        try:
            updated = datetime.strptime(updated, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d')
        except Exception:
            pass
    return f'(⭐ {info["stars"]}, ⏰ {updated})'

def update_readme():
    if not os.path.exists(README_PATH):
        logging.error(f'File not found: {README_PATH}')
        return
    with open(README_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    fetcher = RepoInfoFetcher(GITHUB_TOKEN)
    links = parse_repo_links(content)
    updated_content = content
    seen = set()
    for full_url, owner, repo in links:
        if full_url in seen:
            continue
        seen.add(full_url)
        info = fetcher.fetch(owner, repo)
        info_str = format_info(info)
        updated_content = re.sub(
            rf'({re.escape(full_url)})(\s*\(⭐.*?\))?',
            rf'\1 {info_str}',
            updated_content
        )

    if updated_content != content:
        with open(README_PATH, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        logging.info('README updated successfully.')
    else:
        logging.info('No changes made to README.')

if __name__ == '__main__':
    update_readme()
