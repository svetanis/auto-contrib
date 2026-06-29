---
name: pr-compliance-formatter
description: Enforces Conventional Commits, squashes WIP commits into a single clean commit, and formats PR descriptions according to the repository's PULL_REQUEST_TEMPLATE.md.
---

# PR Compliance Formatter Skill

When preparing the final Pull Request for submission, you must strictly follow these compliance steps to ensure the PR is not rejected by open-source maintainers.

## Step 1: Commit Squashing
- **Action**: You must squash all the intermediate `WIP:` commits created during the test-debugging loop into a single, mathematically clean commit.
- **Action**: Execute the `scripts/squash_wip_commits.py` helper script passing the local repository directory.

## Step 2: Conventional Commits
- **Action**: Ensure the final squashed commit message adheres to the Conventional Commits standard.
- **Format**: `<type>(<scope>): <description>` (e.g., `fix(auth): resolve null pointer exception in login`).
- **Action**: Ensure the commit contains the required Developer Certificate of Origin (DCO) signature at the bottom: `Signed-off-by: auto-contrib <bot@auto-contrib.dev>`.

## Step 3: PR Description Formatting
- **Action**: Read the `.github/PULL_REQUEST_TEMPLATE.md` file from the repository.
- **Action**: Fill out the template perfectly based on the changes you implemented. 
- **Action**: If no template exists, provide a structured summary including "Motivation", "Changes Made", and "Verification".
- **Reference**: Review `examples/pr_description_example.md` for a perfect implementation.

## Step 4: Final Submission
- **Action**: Call the `github-mcp` server's `submit_pull_request` tool using your generated title and description.
