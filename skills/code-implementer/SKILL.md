---
name: code-implementer
description: Core coding skill for fixing a bug or implementing a change. Diagnoses from the issue and the existing code, then proposes ONE precise, test-aware source edit for human approval.
---

# Code Implementer Skill

You are the primary Code Implementer. auto-contrib stages exactly **one contiguous
edit per session** for human approval, so your job is to produce a single, precise
**source-code fix** — not to author separate test files. Follow this workflow:

## Step 1: Locate
- Use the `repo-mapper-mcp` dependency graph to find the file(s) involved and how
  they relate. Use `read_file` on the specific source file that contains the bug.

## Step 2: Understand the existing tests (do NOT write new ones)
- Identify which **existing** tests exercise the code you are about to change
  (e.g. `tests/test_<module>.py`). `read_file` them if useful.
- Your fix must keep those existing tests passing. Reason about how the change
  affects them **before** you propose it.
- Do **NOT** create or overwrite a test file. Authoring a new regression test
  alongside the fix requires a second edit, which the single-edit approval gate
  cannot stage in one session — it is a planned multi-edit (v2) enhancement. If a
  new regression test *would* be valuable, say so in your `proposed_solution` text,
  but still propose only the source fix.

## Step 3: Propose the fix
- Modify the source directly to correct the root cause, matching the repository's
  existing style and conventions.
- Keep `old_text` the **smallest contiguous block** that contains your change,
  copied verbatim from the `read_file` output — a single function/method, never
  spanning across other functions.

## Step 4: Hand off
- Do **not** run tests locally and do **not** call edit/push tools yourself.
- After the human approves and the fix is pushed, the `test-debugger` skill uses
  the `github-mcp` to poll the remote CI/CD pipeline, where the **existing** test
  suite validates the change.
