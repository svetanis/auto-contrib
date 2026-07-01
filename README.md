# auto-contrib

**An autonomous, human-gated GitHub contribution agent.**

Point it at a repository and a GitHub **issue number** (or a plain bug
description) and auto-contrib fetches the issue, maps the architecture, locates
the offending code, creates a feature branch, and proposes a precise fix — then
**stops and asks a human to approve the exact diff** before anything is written
or pushed. On approval it commits, pushes, opens a Conventional-Commits pull
request, and polls GitHub Actions CI on the PR.

It works on **real repositories**: point it at a fork of an open-source project
and it auto-detects the upstream parent to read the issue, branches from the
repo's real default branch (`main` *or* `master`), and opens the PR back to the
fork — no maintainer risk.

Built for the Kaggle *AI Agents: Intensive Vibe Coding* capstone with
**Google ADK**, **Gemini 2.5 Flash**, the **Model Context Protocol**, and
**Agent Skills**.

📄 Full competition writeup: [kaggle-writeup.md](kaggle-writeup.md)
🚀 How to run it (step-by-step): [USAGE.md](USAGE.md)

---

## What it does

The happy-path trajectory for a single supervised session:

```
get_github_issue → map_architecture → read_file → create_feature_branch
   → request_user_approval  (PAUSE — human approves the diff)
   → edit + push → submit_pull_request → poll_github_actions_logs (on the PR)
```

`get_github_issue` runs only when the prompt references an issue number;
otherwise the prompt itself is the spec. The PR is opened **before** the CI poll
because many real repos only run CI on the `pull_request` event.

The agent cannot edit a file on its own: every change passes through a human
approval gate (the "Vibe Diff") and a policy server before it can run.

---

## Architecture

```
User Prompt
     │
     ▼
auto-contrib Agent  (ADK · Gemini 2.5 Flash, rate-limited)
     │
     ├── Agent Skills  (SkillToolset — progressive disclosure)
     │     ├── architecture-mapper        → "map / visualize"
     │     ├── code-implementer           → test-aware source-fix workflow
     │     ├── test-debugger              → CI/CD polling loop
     │     └── pr-compliance-formatter    → Conventional Commits PR
     │
     ├── MCP Servers   (McpToolset over SSE — FastMCP)
     │     ├── repo-mapper-mcp  :8002  → map_architecture (tests/build filtered),
     │     │                              semantic_search
     │     └── github-mcp       :8001  → get_github_issue, read_file,
     │                                    create_feature_branch, push_wip_commit,
     │                                    submit_pull_request,
     │                                    poll_github_actions_logs
     │
     ├── Security Layer
     │     ├── Policy Server      (before_tool_callback: structural + semantic + scope)
     │     ├── Context Resolver   (secret/PII masking on ingested CI logs)
     │     └── HITL Approval Gate (request_user_approval — the "Vibe Diff")
     │
     └── FastAPI + SSE  (streaming dashboard; live, zoomable Mermaid diagram)
```

### Project structure

```
auto-contrib/
├── app/
│   ├── agent.py                  # Root agent: wires MCP servers + skills + policy gate
│   ├── api.py                    # FastAPI app with HITL + SSE streaming (local dev)
│   ├── fast_api_app.py           # ADK-standard app (telemetry, deploy target)
│   ├── rate_limiter.py           # RateLimitedGemini (per-minute budget + sibling-model failover on 429/503)
│   ├── github_mcp_sse.py         # github-mcp server (SSE / FastMCP)
│   ├── repo_mapper_mcp_sse.py    # repo-mapper-mcp server (SSE / FastMCP)
│   ├── github_tools/             # get_issue, read_file, feature_branch, push_wip,
│   │                             #   poll_logs, submit_pr
│   ├── repo_mapper/              # AST parser + map_architecture + semantic_search
│   ├── templates/                # default_pr_body.md (fallback PR template)
│   └── middleware/
│       ├── policy_server.py      # Structural + semantic + scope gating
│       └── context_resolver.py   # PII / secret masking (Context Hygiene)
├── skills/                       # 4 Agent Skills (SKILL.md + scripts + examples)
├── evals/                        # Golden dataset + trajectory/compliance scoring
├── web/                          # Streaming dashboard (index.html, app.js, dashboard.css)
├── tests/                        # Unit + integration tests
├── Dockerfile                    # Container build (Cloud Run target)
└── agents-cli-manifest.yaml      # Deployment manifest
```

---

## Requirements

- **uv** — Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **git** — on PATH
- A **GitHub token** with repo + workflow scope, exported as one of
  `COPILOT_GITHUB_TOKEN`, `GITHUB_TOKEN`, or `GH_TOKEN`
- A **Gemini API key** (`GOOGLE_API_KEY`) — or Vertex AI credentials via
  `gcloud auth application-default login`

Create a `.env` file in the project root (auto-loaded by `app/api.py`):

```env
GOOGLE_API_KEY=your-gemini-key
GITHUB_TOKEN=your-github-token
# Optional: confine writes to an allowlist (semicolon-separated absolute paths)
AUTOCONTRIB_ALLOWED_DIRS=C:\path\to\your\sandbox
```

---

## Quick start (local)

```bash
uv sync
uv run uvicorn app.api:app --host 127.0.0.1 --port 8080
```

Open <http://127.0.0.1:8080> and enter a prompt. Two modes:

- **Symptom-driven** (the agent diagnoses from the symptom):
  > The calculator tests are failing at ../auto-contrib-sandbox. Investigate and fix.

- **Issue-driven** (the agent fetches the GitHub issue and works from it):
  > Fix issue #175 in the repo at ../python-slugify

In issue-driven mode the agent calls `get_github_issue` first; if the local
clone is a fork, it auto-detects the upstream repo (issues live upstream, not on
the fork) and reads the issue there.

Watch the agent map the repo as a live **dependency graph** (zoomable/pannable
preview, with a **⛶ Fullscreen** view for the whole picture), propose a fix shown
as an **exact red/green code diff**, and pause for your approval. Approve to push;
then **Submit PR** to open the pull request and run CI on it.

> The two MCP servers start automatically in background threads on ports 8001 /
> 8002 when the agent module loads — no separate process to manage.

---

## Security model

auto-contrib implements three Zero-Trust patterns from the capstone white papers:

- **HITL Approval Gate** — `request_user_approval` validates the proposed
  `old_text` exists in the target file, then pauses the run. A separate,
  LLM-free `/api/approve` endpoint applies the edit only after a human approves.
- **Policy Server** — an ADK `before_tool_callback` gates every tool call:
  structural checks (non-empty/non-identical edits, protected branch names,
  Conventional-Commits PR titles), a semantic check that blocks genuinely
  destructive disk operations, and a write-scope check that confines writes to
  `AUTOCONTRIB_ALLOWED_DIRS` using `os.path.commonpath`.
- **Context Hygiene** — `context_resolver.resolve()` masks secrets/PII
  (GitHub tokens, prefix-anchored vendor API keys, emails, IPs, SSH-key blocks)
  on **both** external-data ingestion paths — fetched issue text
  (`get_github_issue`) and CI logs (`poll_github_actions_logs`) — before they
  reach the model's context.

---

## Evaluation

```bash
# Verify the golden dataset loads
uv run python evals/eval_suite.py

# Run all scenarios against the live agent
uv run python evals/eval_suite.py /path/to/local/repo

# Run a single scenario
uv run python evals/eval_suite.py /path/to/local/repo ISSUE-001
```

The suite scores **trajectory quality** (expected tool sequence + ordering bonus)
and **PR compliance** (fractional file-match + Conventional-Commits title), and
ships an LLM-as-a-judge prompt for semantic scoring.

---

## Tests

```bash
uv run pytest tests/unit tests/integration
```

---

## Deployment

Container-ready for Cloud Run. The image is built from `Dockerfile` (which copies
`app/`, `skills/`, `web/`, and `evals/`); `agents-cli-manifest.yaml` targets
Cloud Run.

```bash
gcloud config set project <your-project-id>
agents-cli deploy
```

> **Note:** the local dev server (`app/api.py`) hosts the full HITL + streaming UI
> workflow. `app/fast_api_app.py` is the ADK-standard deploy target and currently
> exposes the approve/reject endpoints + telemetry; porting the remaining HITL
> routes (`/api/run`, `/api/submit-pr`) into it is required before a live hosted
> demo.

---

## Known limitations

- **Fork-to-fork PRs (by design for v1).** On a real OSS repo the PR opens
  within your own fork (feature branch → fork's default branch), never upstream.
  This is deliberate: it exercises the full contribution loop on genuine code
  with **zero risk to any maintainer**. Cross-fork PRs to the original repo are a
  **proposed v2 enhancement** — see [Proposed enhancements (v2)](#proposed-enhancements-v2).
- **Single-file fixes.** `request_user_approval` proposes one file's diff per
  session — well-suited to focused bug fixes, not sweeping multi-file refactors.
- **Session state** (pending edit, branch tracking) is process-scoped — correct
  for the supervised single-session demo, but needs per-session keying before
  multi-tenant hosting.
- **HITL** uses a pause-and-resume exception caught by the API layer; a candidate
  for ADK's native interrupt mechanism as it matures.

---

## Proposed enhancements (v2)

- **Cross-fork upstream PRs (not yet implemented / untested).** Today a real-repo
  run opens the PR inside your own fork. A v2 enhancement would optionally target
  the **upstream** parent repo (the same GitHub `/pulls` API call, but against the
  parent with `head="<your-fork-owner>:<branch>"`), so an approved fix could be
  proposed to the original maintainers. It is intentionally left out of v1 because
  opening a PR on a third party's repository is a real, outward-facing action — it
  belongs behind an explicit, separately-confirmed opt-in and needs live testing
  before it can be trusted. The `closes=` hook in the PR-body builder is already
  wired for the upstream-issue link when this lands.
- **Multi-edit / multi-function changes.** Today the approval gate reviews **one
  contiguous diff per session**. Some real bugs legitimately span **several
  non-adjacent functions** (e.g. validators #440 needs both `_isin_checksum` *and*
  the `isin` format guard) or multiple files, which one block can't express. A v2
  enhancement would let `request_user_approval` accept a **list** of edits, render
  each as its own hunk in the Vibe Diff, and apply them **atomically** under one
  commit. This is not architecturally hard — the tool, approve endpoint, policy
  checks, and diff renderer already exist and would each extend from a single edit
  to a list; the real work is edge cases (apply-ordering so one edit doesn't
  invalidate another's anchor, all-or-nothing application) and re-testing the
  working single-edit path. It is deferred, not skipped, to keep the v1 demo flow
  stable. *Note:* this is distinct from the LLM's capability — the model reasons
  about multi-function fixes fine; it is the single-block **gate** that is the
  scoping limit.
- **Per-session state** for multi-tenant hosting (see limitations above).
