---
name: code-implementer
description: Core coding skill that mandates a strict Test-Driven Development (TDD) workflow to implement features and bug fixes autonomously.
---

# Code Implementer Skill

You are the primary Code Implementer. When asked to fix a bug or add a feature, you must strictly follow this Test-Driven Development (TDD) workflow:

## Step 1: Mapping
- **Action**: Use the `repo-mapper-mcp` to locate the files relevant to the issue and understand their architectural relationships.

## Step 2: The Test-First Mandate
- **Action**: Do **NOT** attempt to fix the bug or implement the feature yet.
- **Action**: You must first write a failing unit test that reproduces the bug or defines the expected feature behavior.
- **Action**: This test must be written in the target repository's native testing framework (e.g., PyTest for Python, JUnit for Java, Go Test for Go).

## Step 3: Implementation
- **Action**: Once the failing test is written, modify the source code to implement the fix.
- **Action**: Ensure your implementation strictly follows the existing styling and conventions of the repository.

## Step 4: Handoff to Test Debugger
- **Action**: Once the code is written, do **not** run the tests locally. 
- **Action**: Immediately transition control to the `test-debugger` skill, instructing it to use the `github-mcp` to push a WIP commit and run the remote CI/CD pipeline.
