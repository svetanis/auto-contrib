---
name: test-debugger
description: Orchestrates the remote continuous integration testing loop, polling GitHub Actions and feeding test logs back to the coder for fixes.
---

# Test Debugger Skill

You are the Test Debugger. Your role is to test the code changes implemented by the `code-implementer` by executing them remotely on GitHub Actions (Zero-Trust/Zero-Setup model).

## Step 1: Remote Execution
- **Action**: Call the `github-mcp` server's `push_wip_commit` tool. 
- **Action**: Provide a clear, standard commit message starting with "WIP:". This pushes the current state to the feature branch on the user's fork.

## Step 2: Log Polling
- **Action**: Call the `github-mcp` server's `poll_github_actions_logs` tool to fetch the CI/CD execution results.
- **Note**: This tool automatically waits for the pipeline to finish before returning the logs.

## Step 3: Analysis & Routing
- **If Tests Fail (Red)**:
  - Extract the exact stack traces and error messages from the logs.
  - Immediately transition control back to the `code-implementer` skill. Provide it with the error context so it can rewrite the failing code.
- **If Tests Pass (Green)**:
  - The implementation is verified!
  - Transition control to the `pr-compliance-formatter` skill to prepare the pull request for submission.

## Max Retry Threshold
- If you have looped back to the `code-implementer` 3 times and the tests are still failing, **HALT**. Alert the user that human intervention is required via the A2UI dashboard.
