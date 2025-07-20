import os
import re
import requests
import logging
import subprocess
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# Configuration constants
README_PATH = os.getenv('README_PATH', 'README.md')
GITHUB_API = 'https://api.github.com/repos/'
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPO_INFO_MARK = '\u200B\u200C\u200D'  # Invisible marker for processed links

class UrlContext(Enum):
    """Enum for different URL context types"""
    PLAIN_TEXT = "plain_text"
    MARKDOWN_LINK = "markdown_link"
    HTML_ATTRIBUTE = "html_attribute"
    CODE_BLOCK = "code_block"
    INLINE_CODE = "inline_code"

@dataclass
class UrlMatch:
    """Data class to represent a URL match with context information"""
    start_pos: int
    end_pos: int
    url: str
    owner: str
    repo: str
    context: UrlContext

class RepoInfoFetcher:
    """
    Fetches repository information from GitHub API with caching and error handling.
    """
    
    def __init__(self, token: Optional[str] = None):
        self.session = requests.Session()
        if token:
            self.session.headers['Authorization'] = f'Bearer {token}'
        self.session.headers['Accept'] = 'application/vnd.github+json'
        self._cache: Dict[str, Optional[Dict[str, Any]]] = {}
    
    def fetch(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Fetch repository information with caching"""
        cache_key = f"{owner}/{repo}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        url = f'{GITHUB_API}{owner}/{repo}'
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            result = {
                'stars': data.get('stargazers_count', 0),
                'updated': data.get('updated_at', '')
            }
            self._cache[cache_key] = result
            return result
        except requests.RequestException as e:
            logging.warning(f'Failed to fetch {owner}/{repo}: {e}')
            self._cache[cache_key] = None
            return None

class ContextDetector:
    """Handles detection of URL contexts in content"""
    
    @staticmethod
    def detect_inline_code_context(content: str, pos: int) -> bool:
        """Check if position is within inline code (backticks)"""
        before_content = content[:pos]
        backtick_count = before_content.count('`')
        return backtick_count % 2 == 1
    
    @staticmethod
    def detect_code_block_context(content: str, pos: int) -> bool:
        """Check if position is within a code block (triple backticks)"""
        lines_before = content[:pos].split('\n')
        in_code_block = False
        
        for line in lines_before:
            stripped_line = line.strip()
            if stripped_line.startswith('```'):
                in_code_block = not in_code_block
                
        return in_code_block
    
    @staticmethod
    def detect_markdown_link_context(content: str, start_pos: int, end_pos: int) -> bool:
        """Check if URL is within Markdown link syntax [text](url)"""
        before_content = content[:start_pos]
        bracket_pos = before_content.rfind('](')
        if bracket_pos == -1:
            return False
        
        after_content = content[end_pos:]
        paren_pos = after_content.find(')')
        if paren_pos == -1:
            return False
        
        # Ensure it's on the same line to avoid false positives
        text_between = content[bracket_pos:end_pos + paren_pos + 1]
        return '\n' not in text_between
    
    @staticmethod
    def detect_html_attribute_context(content: str, start_pos: int) -> bool:
        """Check if URL is within HTML attribute (href, src, etc.)"""
        before_content = content[:start_pos]
        url_attributes = [r'href\s*=\s*["\']', r'src\s*=\s*["\']', r'action\s*=\s*["\']']
        
        for pattern in url_attributes:
            matches = list(re.finditer(pattern, before_content, re.IGNORECASE))
            if matches:
                last_match = matches[-1]
                attr_start = last_match.end()
                text_to_check = content[attr_start:start_pos]
                if '"' not in text_to_check and "'" not in text_to_check:
                    return True
        
        return False
    
    def get_url_context(self, content: str, start_pos: int, end_pos: int) -> UrlContext:
        """Determine the context type for a URL match"""
        if self.detect_inline_code_context(content, start_pos):
            return UrlContext.INLINE_CODE
        
        if self.detect_code_block_context(content, start_pos):
            return UrlContext.CODE_BLOCK
            
        if self.detect_markdown_link_context(content, start_pos, end_pos):
            return UrlContext.MARKDOWN_LINK
            
        if self.detect_html_attribute_context(content, start_pos):
            return UrlContext.HTML_ATTRIBUTE
            
        return UrlContext.PLAIN_TEXT

class RepoLinkParser:
    """Handles parsing of GitHub repository links from content"""
    
    # Improved GitHub repo link regex: only match valid owner/repo, not subpaths or issues
    REPO_LINK_RE = re.compile(r'(https://github\.com/([\w.-]+)/([\w.-]+))(?![\w./-])')
    
    @classmethod
    def parse_repo_links(cls, text: str) -> List[Tuple[str, str, str]]:
        """
        Returns a list of (full_url, owner, repo) tuples for all GitHub repo links in the text.
        """
        links = set()
        for match in cls.REPO_LINK_RE.finditer(text):
            full_url = match.group(1)
            parts = full_url.rstrip('/').split('/')
            if len(parts) >= 5:
                owner, repo = parts[3], parts[4]
                links.add((full_url, owner, repo))
        return list(links)

class RepoInfoFormatter:
    """Handles formatting of repository information"""
    
    def __init__(self, repo_info_mark: str):
        self.repo_info_mark = repo_info_mark
    
    def format_info(self, info: Optional[Dict[str, Any]]) -> str:
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
        
        return f'(⭐ {info["stars"]}, ⏰ {updated}){self.repo_info_mark}'

class RepoInfoProcessor:
    """Handles processing and updating of repository information"""
    
    def __init__(self, fetcher: RepoInfoFetcher, formatter: RepoInfoFormatter):
        self.fetcher = fetcher
        self.formatter = formatter
        self.context_detector = ContextDetector()
    
    def find_url_matches(self, content: str, links: List[Tuple[str, str, str]]) -> List[UrlMatch]:
        """Find all URL matches with their context information"""
        url_matches = []
        seen_urls = set()
        
        for full_url, owner, repo in links:
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            
            # Find all occurrences of this URL
            for match in re.finditer(re.escape(full_url), content):
                context = self.context_detector.get_url_context(content, match.start(), match.end())
                url_matches.append(UrlMatch(
                    start_pos=match.start(),
                    end_pos=match.end(),
                    url=full_url,
                    owner=owner,
                    repo=repo,
                    context=context
                ))
        
        # Sort by position (reverse order for safe replacement)
        return sorted(url_matches, key=lambda x: x.start_pos, reverse=True)
    
    def should_process_url(self, url_match: UrlMatch) -> bool:
        """Determine if a URL should be processed based on its context"""
        skip_contexts = {UrlContext.CODE_BLOCK, UrlContext.INLINE_CODE, UrlContext.HTML_ATTRIBUTE}
        return url_match.context not in skip_contexts
    
    def extract_existing_info(self, content: str, url_end_pos: int) -> Tuple[str, int]:
        """Extract existing repo info after URL, return (info_text, total_length)"""
        remaining_content = content[url_end_pos:]
        
        # Match existing repo info pattern
        info_pattern = rf'(\s*\(⭐.*?\)(?:{re.escape(self.formatter.repo_info_mark)})?)'
        match = re.match(info_pattern, remaining_content)
        
        if match:
            return match.group(1), len(match.group(1))
        return "", 0
    
    def process_url_match(self, content: str, url_match: UrlMatch) -> Tuple[str, bool]:
        """Process a single URL match and return updated content and whether it was updated"""
        if not self.should_process_url(url_match):
            logging.debug(f'Skipping URL in {url_match.context.value}: {url_match.url}')
            return content, False
        
        # Handle special case for Markdown links
        if url_match.context == UrlContext.MARKDOWN_LINK:
            return self._process_markdown_link(content, url_match)
        
        # Handle plain text URLs
        return self._process_plain_text_url(content, url_match)
    
    def _process_markdown_link(self, content: str, url_match: UrlMatch) -> Tuple[str, bool]:
        """Process URL within Markdown link by adding info to link text"""
        info = self.fetcher.fetch(url_match.owner, url_match.repo)
        info_str = self.formatter.format_info(info)
        
        if not info_str:
            return content, False
        
        # Find the Markdown link pattern around this URL
        before_content = content[:url_match.start_pos]
        bracket_pos = before_content.rfind('](')
        text_start = before_content[:bracket_pos].rfind('[') + 1
        
        after_content = content[url_match.end_pos:]
        paren_pos = after_content.find(')')
        
        if text_start > 0 and paren_pos != -1:
            # Extract current link text
            current_text = content[text_start:bracket_pos]
            
            # Check if info already exists in link text
            if '⭐' not in current_text and info_str:
                new_text = f"{current_text} {info_str.strip('()')}"
                new_content = (content[:text_start] + new_text + 
                             content[bracket_pos:url_match.end_pos + paren_pos + 1] + 
                             content[url_match.end_pos + paren_pos + 1:])
                return new_content, True
        
        return content, False
    
    def _process_plain_text_url(self, content: str, url_match: UrlMatch) -> Tuple[str, bool]:
        """Process plain text URL by adding/updating info after the URL"""
        info = self.fetcher.fetch(url_match.owner, url_match.repo)
        info_str = self.formatter.format_info(info)
        
        # Extract existing info
        existing_info, existing_length = self.extract_existing_info(content, url_match.end_pos)
        
        if existing_info:
            # Replace existing info
            if info_str:
                replacement = f"{url_match.url} {info_str}"
            else:
                replacement = url_match.url
            
            old_text_end = url_match.end_pos + existing_length
            new_content = content[:url_match.start_pos] + replacement + content[old_text_end:]
            return new_content, bool(info_str)
        else:
            # Add new info
            if info_str:
                new_content = (content[:url_match.end_pos] + 
                             f" {info_str}" + 
                             content[url_match.end_pos:])
                return new_content, True
        
        return content, False

class GitOperations:
    """Handles git operations for committing and pushing changes"""
    
    @staticmethod
    def configure_git_user():
        """Configure git user for CI environment"""
        subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
        subprocess.run(['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'], check=True)
    
    @staticmethod
    def commit_and_push(file_path: str, branch_name: str, commit_message: str) -> bool:
        """Commit and push changes to specified branch"""
        GitOperations.configure_git_user()
        try:
            subprocess.run(['git', 'add', file_path], check=True)
            subprocess.run(['git', 'commit', '-m', commit_message], check=True)
            subprocess.run(['git', 'push', 'origin', branch_name], check=True)
            logging.info(f'Pushed changes to {branch_name}')
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f'Git push failed: {e}')
            return False
    
    @staticmethod
    def create_branch_and_pr(file_path: str, base_branch: str, pr_branch: str, 
                           commit_message: str, pr_title: str, pr_body: str, 
                           github_token: str, repo_full_name: str) -> bool:
        """Create a new branch, commit changes, and create a pull request"""
        GitOperations.configure_git_user()
        try:
            subprocess.run(['git', 'checkout', '-b', pr_branch], check=True)
            subprocess.run(['git', 'add', file_path], check=True)
            subprocess.run(['git', 'commit', '-m', commit_message], check=True)
            subprocess.run(['git', 'push', 'origin', pr_branch], check=True)
            logging.info(f'Pushed changes to {pr_branch}')
        except subprocess.CalledProcessError as e:
            logging.error(f'Git branch/push failed: {e}')
            return False
        
        # Create PR via GitHub API
        return GitOperations._create_pull_request(
            github_token, repo_full_name, pr_title, pr_branch, base_branch, pr_body
        )
    
    @staticmethod
    def _create_pull_request(github_token: str, repo_full_name: str, 
                           pr_title: str, head_branch: str, base_branch: str, 
                           pr_body: str) -> bool:
        """Create a pull request via GitHub API"""
        api_url = f'https://api.github.com/repos/{repo_full_name}/pulls'
        headers = {'Authorization': f'Bearer {github_token}', 'Accept': 'application/vnd.github+json'}
        data = {
            'title': pr_title,
            'head': head_branch,
            'base': base_branch,
            'body': pr_body
        }
        
        try:
            resp = requests.post(api_url, headers=headers, json=data, timeout=10)
            if resp.status_code == 201:
                logging.info(f'Pull request created: {resp.json().get("html_url")}')
                return True
            else:
                logging.error(f'Failed to create PR: {resp.text}')
                return False
        except requests.RequestException as e:
            logging.error(f'Failed to create PR: {e}')
            return False

class ReadmeUpdater:
    """Main class orchestrating the README update process"""
    
    def __init__(self, readme_path: str = README_PATH, github_token: Optional[str] = GITHUB_TOKEN,
                 repo_info_mark: str = REPO_INFO_MARK):
        self.readme_path = readme_path
        self.github_token = github_token
        self.repo_info_mark = repo_info_mark
        
        # Initialize components
        self.fetcher = RepoInfoFetcher(github_token)
        self.formatter = RepoInfoFormatter(repo_info_mark)
        self.processor = RepoInfoProcessor(self.fetcher, self.formatter)
        self.parser = RepoLinkParser()
    
    def update_readme(self) -> List[str]:
        """
        Update README file with repository information
        Returns list of updated URLs
        """
        if not os.path.exists(self.readme_path):
            logging.error(f'File not found: {self.readme_path}')
            return []
        
        # Read content
        try:
            with open(self.readme_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logging.error(f'Error reading file: {e}')
            return []
        
        # Parse and process links
        links = self.parser.parse_repo_links(content)
        if not links:
            logging.info('No GitHub repository links found.')
            return []
        
        url_matches = self.processor.find_url_matches(content, links)
        
        updated_content = content
        updated_links = []
        
        # Process each URL match
        for url_match in url_matches:
            new_content, was_updated = self.processor.process_url_match(updated_content, url_match)
            
            if was_updated:
                updated_content = new_content
                updated_links.append(url_match.url)
        
        # Write updated content back to file
        if updated_content != content:
            try:
                with open(self.readme_path, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                logging.info('README updated successfully.')
                
                if updated_links:
                    logging.info('Updated repo links:')
                    for link in updated_links:
                        logging.info(f'  {link}')
            except Exception as e:
                logging.error(f'Error writing file: {e}')
                return []
        else:
            logging.info('No changes made to README.')
        
        return updated_links

def main():
    """Main function with improved configuration and error handling"""
    updater = ReadmeUpdater()
    updated_links = updater.update_readme()
    
    # Only proceed with git operations if there were updates
    if not updated_links:
        logging.info('No updates made, skipping git operations.')
        return
    
    # Get configuration
    mode = os.getenv('UPDATE_MODE', 'direct')
    repo_full_name = os.getenv('GITHUB_REPOSITORY')
    base_branch = os.getenv('BASE_BRANCH', 'master')
    
    commit_message = 'chore: update repo info in README'
    pr_branch = f'update-repo-info-{datetime.now().strftime("%Y%m%d%H%M%S")}'
    pr_title = 'chore: update repo info in README'
    pr_body = f'Automated update of repo info in README.\n\nUpdated {len(updated_links)} repository links.'
    
    try:
        if mode == 'direct':
            success = GitOperations.commit_and_push(README_PATH, base_branch, commit_message)
            if not success:
                logging.error('Direct push failed')
        elif mode == 'pr' and repo_full_name and GITHUB_TOKEN:
            success = GitOperations.create_branch_and_pr(
                README_PATH, base_branch, pr_branch, commit_message, 
                pr_title, pr_body, GITHUB_TOKEN, repo_full_name
            )
            if not success:
                logging.error('Pull request creation failed')
        else:
            logging.error(f'Invalid mode "{mode}" or missing required environment variables')
    except Exception as e:
        logging.error(f'Git operations failed: {e}')

if __name__ == '__main__':
    main()