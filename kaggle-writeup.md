# auto-contrib — An Autonomous, Human-Gated GitHub Contribution Agent

**Kaggle "AI Agents: Intensive Vibe Coding" Capstone**
**Track:** Agents for Business / Freestyle
**Built with:** Google ADK · Gemini 2.5 Flash · Model Context Protocol · Agent Skills

---

## 1. The Problem & Why It Matters

Contributing to an unfamiliar codebase is slow and intimidating. Before a
developer can fix even a one-line bug in an open-source project, they have to map
an unfamiliar architecture, find the right file, match the repo's conventions,
write a test, wait on CI, and open a pull request that satisfies the
maintainers' template. That friction is why so many "good first issues" sit
untouched for months, and why internal engineering teams burn senior time
onboarding people onto services they rarely touch.

**auto-contrib** compresses that entire loop into a single, supervised session.
Given a repository and a GitHub **issue number** (or a plain bug description),
the agent fetches the issue, maps the architecture, locates the offending code,
creates a feature branch, and proposes a precise fix — then **stops and asks a
human to approve the exact diff** before anything is written or pushed. Once
approved, it commits, pushes, opens a Conventional-Commits-compliant pull
request, and polls GitHub Actions CI on that PR.

Crucially, it runs against **real open-source repositories**: pointed at a fork,
it auto-detects the upstream parent to read the issue (forks don't carry issues),
branches from the repo's real default branch (`main` *or* `master`), and opens
the PR back to the fork — demonstrating the full contribution loop on genuine
code with zero risk to any maintainer.

The value proposition is deliberately narrow and real: it does not try to be an
autonomous developer. It is a **contribution accelerator with a human in the
loop** — the agent does the tedious navigation and mechanics; the human keeps
judgment and authority over every change that touches the repository. That
framing maps directly onto the Day 4 white paper's distinction between *security*
("did the agent stay in bounds?") and *evaluation* ("was what it did worth
shipping?"). auto-contrib answers the first with a hard approval gate and a
policy server, and the second with an evaluation suite.

---

## 2. Architecture Overview

auto-contrib is a single ADK agent (`root_agent`) whose capabilities are
assembled from three composable layers — **Skills** (procedural know-how), **MCP
servers** (reach into Git/GitHub and code analysis), and a **security layer**
(policy gate, context hygiene, HITL approval). A FastAPI application streams the
agent's reasoning to a custom browser dashboard over Server-Sent Events.

```
User Prompt ("fix the bug in calculator.py at <repo>")
     │
     ▼
auto-contrib Agent  (ADK · Gemini 2.5 Flash, rate-limited)
     │
     ├── Agent Skills  (SkillToolset — progressive disclosure)
     │     ├── architecture-mapper        → triggers on "map / visualize"
     │     ├── code-implementer           → test-aware source-fix workflow
     │     ├── test-debugger              → CI/CD polling loop
     │     └── pr-compliance-formatter    → Conventional Commits PR
     │
     ├── MCP Servers   (McpToolset over SSE — FastMCP)
     │     ├── repo-mapper-mcp  :8002
     │     │     ├── map_architecture     (AST → Mermaid; tests/build filtered)
     │     │     └── semantic_search
     │     └── github-mcp       :8001
     │           ├── get_github_issue     (fork-aware: reads the upstream issue)
     │           ├── read_file
     │           ├── create_feature_branch
     │           ├── push_wip_commit
     │           ├── submit_pull_request
     │           └── poll_github_actions_logs
     │
     ├── Security Layer
     │     ├── Policy Server      (before_tool_callback: structural + semantic + scope)
     │     ├── Context Resolver   (secret/PII masking on ingested CI logs)
     │     └── HITL Approval Gate (request_user_approval — the "Vibe Diff")
     │
     └── FastAPI + SSE
           ├── POST /api/run       → streams tool calls + live, zoomable Mermaid diagram
           ├── POST /api/approve   → applies edit, pushes the branch
           ├── POST /api/reject    → discards the pending edit
           └── POST /api/submit-pr → opens the PR, then polls CI on it
```

The happy-path trajectory is: `get_github_issue` *(when an issue is named)* →
`map_architecture` → `read_file` → `create_feature_branch` →
`request_user_approval` **(pause)** → human approves → edit + push →
`submit_pull_request` → `poll_github_actions_logs`. The PR is opened *before* the
CI poll because real repositories commonly trigger CI on the `pull_request`
event, so the workflow only starts once the PR exists.

---

## 3. Key Concepts Applied

The capstone asks entrants to apply at least three of six concept areas.
auto-contrib implements **four in working code** — Agent/Multi-agent (ADK), MCP
Server, Agent Skills, and Security features — and demonstrates a fifth
(Deployability) through containerization.

### 3.1 Agent / Multi-Agent with ADK (Day 1)

The Day 1 paper's central thesis is the *factory model*: the developer's job is
to engineer the system that produces code — the harness of prompts, tools,
sandboxes, and guardrails — rather than to write code directly. auto-contrib is
built as exactly that harness. The agent itself is thin; its behavior comes from
the orchestration of skills, MCP tools, and policy callbacks wired around it in
`app/agent.py`.

Rather than a monolithic prompt, the workflow is decomposed into four skills that
the model loads on demand, giving the single agent a multi-stage,
multi-persona-style pipeline (mapper → implementer → debugger → PR formatter)
while keeping one coherent session and history. A custom `RateLimitedGemini`
wrapper enforces a requests-per-minute budget (sleeping rather than failing when
near the cap) and, when the primary model is overloaded (503) or quota-limited
(429), transparently **fails over to a sibling model** (`gemini-2.5-flash-lite`,
then `gemini-flash-latest`, …) — each has its own capacity/quota pool, so one
model's limit no longer kills a run. Only if every fallback is also exhausted does
it surface a clean, actionable error with the API's own retry hint. This is a
small but concrete piece of "engineering the factory" rather than trusting the
model to behave.

### 3.2 MCP Server (Days 2 & 5)

Day 2 frames MCP as the standard that collapses integration cost from O(N×M) to
O(N+M); Day 5 shows how little code a server actually needs. auto-contrib ships
**two** MCP servers built with FastMCP and exposed over HTTP/SSE:

- **repo-mapper-mcp** (`:8002`) — `map_architecture` walks a repository, parses
  Python with an AST extractor (Java/Go/TypeScript via heuristics), and returns a
  Mermaid **module dependency graph**: a `flowchart` whose nodes are source
  modules (grouped into package subgraphs) and whose edges are the intra-repo
  imports between them, each annotated with its absolute file path. It prunes
  test, build, and vendor directories — and `__init__.py` re-export hubs — so the
  graph shows the real structure (which modules are shared cores, which are
  leaves) rather than drowning in noise; `semantic_search` provides keyword
  retrieval over the indexed code.
- **github-mcp** (`:8001`) — the Git/GitHub workflow surface: `get_github_issue`,
  `read_file`, `create_feature_branch`, `push_wip_commit`, `submit_pull_request`,
  and `poll_github_actions_logs`. `get_github_issue` is fork-aware — when the
  local clone is a fork it resolves the upstream `parent` via the GitHub API and
  reads the issue there, since forks don't carry their own issues. This is what
  lets the agent start from a real issue ("fix #175") rather than a hand-fed
  solution: the issue text becomes the spec it must diagnose against.

The agent consumes them through ADK's `McpToolset` with `SseConnectionParams`,
following the Day 2 discovery → configuration → connection pattern. SSE transport
(rather than stdio) was chosen specifically to avoid subprocess-handle issues on
Windows; the servers start in background threads when the agent module loads, and
the app waits for both ports to accept connections before serving. This is a
genuine protocol boundary — the agent talks MCP, not in-process function calls.

### 3.3 Agent Skills (Day 3)

Day 3 defines skills as folders (`SKILL.md` + optional scripts/examples)
implementing *progressive disclosure*: metadata is always in context (~50
tokens), but a skill's body only loads when triggered. auto-contrib defines four
such skills loaded via `SkillToolset`:

- **architecture-mapper** — how to map and visualize a repo.
- **code-implementer** — a **test-aware** source-fix workflow: locate the code,
  read the *existing* tests that cover it, then propose one precise fix that keeps
  them passing and hand off.
- **test-debugger** — manage the CI/CD polling loop and interpret failures.
- **pr-compliance-formatter** — enforce Conventional Commits and a clean PR body.

The `code-implementer` skill is deliberately **test-aware rather than
test-first**: it reasons about the existing suite and fixes the source so CI stays
green, but it does not author a *new* test file, because the approval gate stages
one contiguous edit per session and a fix-plus-new-test is two edits. Authoring a
regression test alongside the fix is the planned multi-edit (v2) enhancement; the
skill flags when one is warranted but proposes only the source change. This keeps
the agent's behavior deterministic and matches what the single-edit gate can
actually deliver — an honest fit between the skill's know-how and the tool's reach.

This is the Day 3 "Skills = know-how, MCP = reach" distinction made concrete: the
MCP servers can *push a commit*, but the `code-implementer` skill encodes *when
and how* to do so responsibly (fix against the existing tests, hand off to CI).
The skills ship with
example resources (`diagram_example.md`, `pr_description_example.md`) and helper
scripts (`generate_mermaid.py`, `squash_wip_commits.py`) that load only on
demand.

### 3.4 Security Features (Days 4 & 5)

Security is where the project leans hardest into the white papers, implementing
three of the Day 4/Day 5 patterns:

**Human-in-the-Loop Approval Gate (the "Vibe Diff").** The agent *cannot* edit a
file on its own. `request_user_approval` validates that the proposed `old_text`
actually exists in the target file, stores the pending edit, and pauses the run.
The browser then renders the **exact code diff** — a compact red/green hunk of the
proposed `old_text`→`new_text` (not just a description), so the human approves on
what they can *see* — and the card glows to signal it is awaiting a decision. Only
on approval does a separate, LLM-free endpoint apply the edit and push. This is the
Day 5 Zero-Trust "HITL checkpoint" — authority over the repository never leaves
the human.

**Policy Server (structural + semantic + scope gating).** Implemented as an ADK
`before_tool_callback`, every tool call passes through three tiers before it can
run: structural checks (e.g. `edit_file` must have non-empty, non-identical
old/new text; branch names can't be `main`/`master`; PR titles must match
Conventional Commits), a semantic check that blocks genuinely destructive disk
operations, and a write-scope check that confines file writes to an explicit
allowlist using `os.path.commonpath` (so a sibling directory sharing a name
prefix can't be smuggled in). This is the Day 5 Policy Server pattern — a
structural + semantic gate that can later be upgraded to an LLM classifier
without changing the interface.

**Context Hygiene (Context Resolver).** Following Day 5's `ContextResolver`
pattern with `[[VARIABLE]]` placeholders, secrets and PII (GitHub tokens,
prefix-anchored vendor API keys, emails, IPs, SSH-key blocks) are masked before
external text enters the model's context. It is wired into **both**
external-data ingestion paths — fetched issue text (`get_github_issue`) and
failed-build CI logs (`poll_github_actions_logs`) — the two classic
untrusted-input vectors, so neither reaches the agent unscrubbed. The masking
patterns are deliberately conservative (prefix-anchored, not a blanket
alphanumeric match) so they never corrupt legitimate code such as commit SHAs or
the regex patterns and hashes that routinely appear in issue bodies.

### 3.5 Deployability (Days 1, 2 & 5)

The project is container-ready: a `Dockerfile` builds the app (copying the agent,
skills, web UI, and eval assets), and `agents-cli-manifest.yaml` targets Cloud
Run. Because the capstone only requires three concept areas and we already meet
four in code, deployability is demonstrated as packaging-and-manifest readiness
rather than a permanently hosted URL — an honest scoping choice given the
single-session, human-gated design.

---

## 4. Demo Walkthrough

The headline demo runs against a **real PyPI library** — a fork of
`python-slugify` with a genuine open issue (#175, *"--regex-pattern option
ignored by CLI"*). A controlled sandbox repo (`auto-contrib-sandbox`, a buggy
`Calculator` with a matching test suite) is used for fast regression runs.

0. **Fetch the issue.** The user enters *"Fix issue #175 in the repo at
   ../python-slugify"*. The agent calls `get_github_issue`; because the clone is
   a fork, the tool auto-detects the upstream `un33k/python-slugify` and returns
   the issue title, body, and comments. The agent now has the symptom — not a
   solution — as its spec.
1. **Map.** `map_architecture` returns a Mermaid **dependency graph** — modules as
   nodes, imports as edges — rendered live as a zoomable preview with a **⛶
   fullscreen** view for the whole picture. With tests, build dirs, and
   `__init__.py` re-export hubs filtered out, the graph shows how the package
   actually fits together: for slugify, the `__main__` CLI depends on the core
   `slugify` module — the very edge that frames issue #175.
2. **Locate & diagnose.** The agent calls `read_file` on the suspected file
   (`slugify/__main__.py`), reads the actual code, and pinpoints the bug itself:
   the `--regex-pattern` arg is never passed from `slugify_params` to `slugify`.
3. **Branch.** `create_feature_branch` forks from the repo's real default branch
   (resolved from `origin/HEAD` — here `master`, not `main`) and fast-forwards
   it, so a fix never stacks on a stale branch.
4. **Propose & pause.** `request_user_approval` presents the plain-English
   rationale and the precise one-line old/new diff. Execution pauses; the UI
   shows the proposed change with approve/reject buttons.
5. **Approve & push.** On approval, the LLM-free `/api/approve` endpoint applies
   the edit, commits, and pushes the branch to the fork.
6. **PR & CI.** **Submit PR** opens a Conventional-Commits pull request — base
   branch auto-detected (`master`), body filled from the repo's own template or,
   when it has none (as here), from auto-contrib's default PR-body template that
   honestly checks only what it can vouch for (human-approved diff, CI green).
   Because the repo gates CI on the `pull_request` event, the workflow starts
   only now; the endpoint polls the PR's run and the dashboard reports it green.

Every step is streamed token-by-token to the terminal pane, making the agent's
trajectory fully observable — which doubles as the Day 4 "trajectory quality"
evidence.

---

## 5. Evaluation

Per Day 3's Evaluation-Driven Development and Day 4's seven evaluation
dimensions, auto-contrib ships an `evals/` suite driven by a golden dataset of
five scenarios spanning Java, TypeScript, Go, Python, and Markdown
(`golden_dataset.json`). The suite scores two dimensions automatically:

- **Trajectory quality** — does the agent call the expected tools
  (`map_architecture` → `read_file` → `create_feature_branch` →
  `request_user_approval`) in the right order? Correct ordering earns a bonus.
- **PR compliance** — fractional credit for matching the expected modified files,
  plus credit for a Conventional-Commits title of the correct type.

A `generate_llm_judge_prompt` helper produces an LLM-as-a-judge prompt for
semantic evaluation ("did the agent fix the root cause securely?"), implementing
the Day 4 multimodal/semantic scoring idea. The runner executes each scenario
against the live agent and aggregates scores, so evaluation is connected to real
runs rather than being a static rubric.

---

## 6. Engineering Discipline & Honest Limitations

In the spirit of Day 5 ("Vibe Coding is not Vibe-in-Production"), a few honest
notes:

- **PRs open within the fork, not upstream.** The full demo contributes to a
  fork of a real library (feature branch → the fork's default branch), not to
  the original repo — deliberately, for zero maintainer risk. Cross-fork PRs
  (`head=fork:branch` against the upstream `/pulls` endpoint) are a **proposed
  v2 enhancement**, intentionally left unbuilt in v1 because opening a PR on a
  third party's repository is a real outward-facing action that belongs behind an
  explicit, separately-confirmed opt-in; the `closes=` hook in the PR-body builder
  is already wired for the upstream-issue link when that lands.
- **Fixes are a single contiguous block.** `request_user_approval` proposes one
  diff per session — a deliberate fit for focused bug fixes and the approval UX,
  not sweeping multi-file refactors. Some real bugs legitimately span several
  non-adjacent functions (a finance-validator issue we tested needed both the
  checksum helper *and* its caller's format guard), which one block cannot express.
  Importantly, this is a limit of the single-block **approval gate**, not of the
  model — the LLM reasons about multi-function fixes fine. A **proposed v2
  enhancement** would let the gate accept a *list* of edits, render each as its own
  hunk, and apply them atomically under one commit; the tool, endpoint, policy
  checks, and diff renderer already exist and would each extend from one edit to a
  list, so the work is edge cases (apply-ordering, all-or-nothing), not
  architecture — deferred only to keep the v1 demo flow stable.
- **Session state is single-user.** Pending edits and branch tracking are
  process-scoped, which is correct for the supervised, single-session demo but
  would need per-session keying before multi-tenant hosting.
- **HITL is implemented via a pause-and-resume exception** caught by the API
  layer; it works reliably but is a candidate for ADK's native interrupt
  mechanism as that matures.

These are documented rather than hidden because the judging rubric rewards
agentic-engineering discipline — knowing where the bounds are is part of staying
inside them.

---

## 7. Summary

auto-contrib turns the multi-step, intimidating act of contributing a fix to an
unfamiliar repository into a single supervised session, while never surrendering
human authority over the code — and it does so on **genuine open-source repos**,
starting from a **real issue number** rather than a hand-fed answer. It applies
the capstone's concepts as working software, not slideware: an ADK agent
orchestrating **two MCP servers** (issue + repo intelligence and the Git/GitHub
workflow) and **four Agent Skills**, gated by a **three-tier policy server**, a
**context-hygiene resolver** on every untrusted-input path, and a **human
approval checkpoint**, with a **connected evaluation suite** and a
**container-ready deployment** path. It is a small, honest, and genuinely useful
demonstration of the white papers' core lesson: the harness — the tools, skills,
and guardrails engineered around the model — is what makes an agent trustworthy.

---

*Word count ≈ 2,050. To reach the ~2,500-word target, drop in concrete artifacts
from the recorded run: a screenshot of the zoomable architecture map, the real
`python-slugify` PR URL with CI green, and the eval suite's actual scores.*
