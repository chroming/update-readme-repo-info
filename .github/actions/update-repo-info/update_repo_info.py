import os
import re
import requests
import logging
import subprocess
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

# Use three invisible Unicode characters as a marker (e.g., ZERO WIDTH SPACE, ZERO WIDTH NON-JOINER, ZERO WIDTH JOINER)
REPO_INFO_MARK = '\u200B\u200C\u200D'  # Invisible marker for processed links

# Improved GitHub repo link regex: only match valid owner/repo, not subpaths or issues
REPO_LINK_RE = re.compile(r'(https://github.com/([\w.-]+)/([\w.-]+))(?![\w./-])')

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
    Formats the repository info for display after the link, with an invisible marker for update detection.
    """
    if not info:
        return ''  # If fetch failed, do not add anything
    updated = info['updated']
    if updated:
        try:
            updated = datetime.strptime(updated, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d')
        except Exception:
            pass
    return f'(⭐ {info["stars"]}, ⏰ {updated}){REPO_INFO_MARK}'

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
    updated_links = []  # Track which links are updated
    for full_url, owner, repo in links:
        if full_url in seen:
            continue
        seen.add(full_url)
        info = fetcher.fetch(owner, repo)
        info_str = format_info(info)
        def replace_info(match):
            url = match.group(1)
            info_part = match.group(2)
            # Only update if marker exists, else add if info_str is not empty
            if info_part and REPO_INFO_MARK in info_part:
                if info_str:
                    updated_links.append(url)
                    return f'{url} {info_str}'
                else:
                    # If fetch failed, remove the old info
                    return url
            elif info_part:
                if info_str:
                    updated_links.append(url)
                    return f'{url} {info_str}'
                else:
                    return url
            else:
                if info_str:
                    updated_links.append(url)
                    return f'{url} {info_str}'
                else:
                    return url
        updated_content = re.sub(
            rf'({re.escape(full_url)})(\s*\(⭐.*?\){REPO_INFO_MARK}|\s*\(⭐.*?\)|)',
            replace_info,
            updated_content
        )

    if updated_content != content:
        with open(README_PATH, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        logging.info('README updated successfully.')
        if updated_links:
            logging.info('Updated repo links:')
            for link in updated_links:
                logging.info(f'  {link}')
    else:
        logging.info('No changes made to README.')

def git_commit_and_push(branch_name, commit_message):
    # Set git user info for CI
    subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
    subprocess.run(['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'], check=True)
    try:
        subprocess.run(['git', 'add', README_PATH], check=True)
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)
        subprocess.run(['git', 'push', 'origin', branch_name], check=True)
        logging.info(f'Pushed changes to {branch_name}')
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f'Git push failed: {e}')
        return False

def create_branch_and_pr(base_branch, pr_branch, commit_message, pr_title, pr_body, github_token, repo_full_name):
    # Set git user info for CI
    subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
    subprocess.run(['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'], check=True)
    try:
        subprocess.run(['git', 'checkout', '-b', pr_branch], check=True)
        subprocess.run(['git', 'add', README_PATH], check=True)
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)
        subprocess.run(['git', 'push', 'origin', pr_branch], check=True)
        logging.info(f'Pushed changes to {pr_branch}')
    except subprocess.CalledProcessError as e:
        logging.error(f'Git branch/push failed: {e}')
        return False
    # Create PR via GitHub API
    api_url = f'https://api.github.com/repos/{repo_full_name}/pulls'
    headers = {'Authorization': f'Bearer {github_token}', 'Accept': 'application/vnd.github+json'}
    data = {
        'title': pr_title,
        'head': pr_branch,
        'base': base_branch,
        'body': pr_body
    }
    resp = requests.post(api_url, headers=headers, json=data)
    if resp.status_code == 201:
        logging.info(f'Pull request created: {resp.json().get("html_url")}')
        return True
    else:
        logging.error(f'Failed to create PR: {resp.text}')
        return False

if __name__ == '__main__':
    update_readme()
    mode = os.getenv('UPDATE_MODE', 'direct')
    repo_full_name = os.getenv('GITHUB_REPOSITORY')
    base_branch = os.getenv('GITHUB_REF_NAME', 'master')
    commit_message = 'chore: update repo info in README'
    pr_branch = f'update-repo-info-{datetime.now().strftime("%Y%m%d%H%M%S")}'
    pr_title = 'chore: update repo info in README'
    pr_body = 'Automated update of repo info in README.'
    if mode == 'direct':
        git_commit_and_push(base_branch, commit_message)
    elif mode == 'pr' and repo_full_name:
        create_branch_and_pr(base_branch, pr_branch, commit_message, pr_title, pr_body, GITHUB_TOKEN, repo_full_name)
