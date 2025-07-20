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
  workflow_dispatch:
jobs:
  update-readme:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Update repo info in README
        uses: ./.github/actions/update-repo-info
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          mode: pr  # or 'direct' for direct commit & push
          base_branch: master  # or 'main' or your custom branch name
```

> **Note:**
> - If you use `mode: pr`, your workflow must have `pull-requests: write` permission (see above).
> - If you use `mode: direct`, your workflow must have `contents: write` permission (see above).
> - In forked repositories or PR workflows, GitHub's default GITHUB_TOKEN may not have permission to create PRs. Use in the main repository for full functionality.
> - You must enable **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests** in your repository settings, otherwise PR creation will fail with a 403 error.
> - You can set the PR/commit base branch by adding `BASE_BRANCH` to the workflow env (default is `master`).

### 2. Inputs

| Name          | Description                  | Required | Default                |
|---------------|-----------------------------|----------|------------------------|
| github_token  | GitHub Token for API access | false     | ${{ github.token }}    |
| mode          | Update mode: pr (pull request) or direct (commit & push) | false | pr |
| base_branch   | PR/commit base branch name (e.g. main/master/other)      | false | master |


### 3. Output

- Updates your README.md in-place with repo star and last update info after each GitHub repo link.

## Example

```
- https://github.com/octocat/Hello-World (⭐ 3014, ⏰ 2025-07-12)​‌‍
- https://github.com/chroming/pdfdir (⭐ 712, ⏰ 2025-07-07)​‌‍
- https://github.com/microsoft/vscode (⭐ 174481, ⏰ 2025-07-13)​‌‍
```

## License
MIT
