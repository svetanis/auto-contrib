# Running auto-contrib

A practical guide to starting the agent and driving a fix end-to-end. For the
architecture and concepts, see [README.md](README.md) and
[kaggle-writeup.md](kaggle-writeup.md).

---

## 1. One-time setup

Create a `.env` file in `auto-contrib/` (auto-loaded by `app/api.py`):

```env
GOOGLE_API_KEY=your-gemini-key
GITHUB_TOKEN=your-github-token        # needs repo + workflow scope
# Optional: confine writes to an allowlist (semicolon-separated absolute paths)
AUTOCONTRIB_ALLOWED_DIRS=C:\path\to\your\sandbox
```

Requirements: `uv`, `git` on PATH, a Gemini API key, and a GitHub token
(`COPILOT_GITHUB_TOKEN`, `GITHUB_TOKEN`, or `GH_TOKEN`).

---

## 2. Start the server

From the `auto-contrib/` directory:

```bash
uv run uvicorn app.api:app --host 127.0.0.1 --port 8080
```

(or directly: `..\.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8080`)

The two MCP servers start automatically in background threads on ports 8001 /
8002 — no separate process to manage. Open <http://127.0.0.1:8080>.

---

## 3. Two ways to use it

The agent accepts **either** an issue number **or** a bug you describe yourself.
The only thing that switches modes is whether your prompt contains an issue
number like `#175`.

### A. Symptom-driven — a bug you found yourself (no issue needed)

Describe the symptom and the repo path. The agent diagnoses it from the code.

```
The calculator tests are failing at ../auto-contrib-sandbox. Investigate and fix.
```

```
There's a bug in slugify.py at ../python-slugify — trailing underscores are
dropped. Please find and fix it.
```

> Don't hand it the solution — describe what's wrong, not how to fix it. Letting
> the agent diagnose is the point.

### B. Issue-driven — point it at an open GitHub issue

Reference the issue number; the agent calls `get_github_issue` first and uses the
issue text as its spec.

```
Fix issue #413 in the repo at ../validators
```

```
Fix issue #175 in the repo at ../python-slugify
```

Both have been run end-to-end (real fork, real issue, PR opened, CI green). If
the local clone is a **fork**, the agent auto-detects the upstream repo and reads
the issue there (forks don't carry their own issues).

---

## 4. The approval flow (same for both modes)

1. **Run** — the agent fetches the issue (if any), maps the repo (live, zoomable
   diagram — scroll to zoom, drag to pan), reads the code, and proposes a fix.
2. **Approve / Reject** — the run pauses and shows the exact diff. Nothing is
   written or pushed until you click **Approve**.
3. **Submit PR** — after the push, click **Submit PR**. The PR opens on the repo
   (base branch auto-detected: `main` or `master`), then CI is polled on the PR.
4. **New Task** — clears the session so the next fix starts fresh.

---

## 5. Running against a real repo (fork workflow)

1. **Fork** the target repo (e.g. `python-validators/validators` or
   `un33k/python-slugify`) to your GitHub account.
2. On your fork: **Settings → Actions → enable workflows.** Forks have Actions
   disabled by default — this is the #1 reason CI never runs.
3. **Clone your fork** locally. Its `origin` is your fork (you have push access).
4. Point the agent at the clone and use either mode above. The PR opens within
   your fork (feature branch → fork's default branch) — zero risk to the
   upstream maintainer.

> Working reference forks from actual test runs:
> [svetanis/validators](https://github.com/svetanis/validators) (issue #413,
> PR [#1](https://github.com/svetanis/validators/pull/1)) and
> [svetanis/python-slugify](https://github.com/svetanis/python-slugify)
> (issue #175).

> **The PR always targets your fork, never the upstream repo.** Opening a PR
> against the original maintainers' repo is a *proposed v2 enhancement* and is
> not implemented or tested — see "Proposed enhancements (v2)" in the README.
> For the demo, a PR to your fork is sufficient and safe.

---

## 6. Troubleshooting

- **"No CI/CD runs found yet"** — expected on repos that only run CI on the
  `pull_request` event. Click **Submit PR**; CI runs on the PR, not the bare
  branch push.
- **CI never runs on a fork** — Actions aren't enabled on the fork (step 5.2).
- **`429` / quota exceeded** — the Gemini API key hit its quota. Wait, or enable
  pay-as-you-go billing for the recording day. The local rate limiter only throttles
  per-minute; daily quota is enforced by Gemini itself.
- **"old_text not found"** — the agent will re-read the file and retry; if it
  persists, the file changed under it — start a New Task.
- **PR opened with a plain body** — the target repo has no
  `.github/PULL_REQUEST_TEMPLATE.md`, so auto-contrib's default template
  ([app/templates/default_pr_body.md](app/templates/default_pr_body.md)) was used.
