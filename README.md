# Update Repo Info in README Action

This GitHub Action parses all GitHub repository links in your README.md, fetches their star count and last update time, and updates the README accordingly. It is designed for easy reuse and extension.

## Features
- Automatically finds all `https://github.com/owner/repo (fetch failed) <!--repo-info-->` links in your README.md
- Fetches star count and last update time for each repository
- Updates the README in-place, appending info after each link
- Easily extensible for more repository info fields

## Usage

### 1. Add to your workflow

```yaml
name: Update Repo Info in README
on:
  push:
    tags:
      - '*'  # Trigger on any new tag push
jobs:
  update-readme:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Update repo info in README
        uses: ./.github/actions/update-repo-info
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
      - name: Set up Git user
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
      - name: Commit and push changes
        run: |
          git add README.md
          git commit -m "chore: update repo info in README" || echo "No changes to commit"
          git push
```

### 2. Inputs

| Name          | Description                  | Required | Default                |
|---------------|-----------------------------|----------|------------------------|
| github_token  | GitHub Token for API access | true     | ${{ github.token }}    |

### 3. Output

- Updates your README.md in-place with repo star and last update info after each GitHub repo link.

## Example

Before:
```
- https://github.com/octocat/Hello-World (⭐ 3014, ⏰ 2025-07-12) <!--repo-info-->
```
After:
```
- https://github.com/octocat/Hello-World (⭐ 3014, ⏰ 2025-07-12) <!--repo-info-->
```

## License
MIT
