"""Evaluation suite for auto-contrib agent.

Runs golden scenarios and scores trajectory quality + PR compliance.
Usage:
    python evals/eval_suite.py /path/to/local/repo [ISSUE-001]
"""
import asyncio
import json
import os
import sys

# ── Dataset ───────────────────────────────────────────────────────────────────

def load_dataset() -> list[dict]:
    path = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_compliance(expected: dict, actual_files: list[str], actual_pr_title: str) -> float:
    """Scores PR compliance based on modified files and Conventional Commits title.

    File matching is fractional (partial credit) rather than all-or-nothing: the
    HITL flow proposes one file per approval, so demanding every expected file at
    once would force the score to 0 on any multi-file scenario.
    """
    score = 0.0

    expected_files = expected["expected_files_modified"]
    if expected_files:
        matched_files = set(expected_files).intersection(set(actual_files))
        score += 0.5 * (len(matched_files) / len(expected_files))

    if actual_pr_title.startswith(f"{expected['expected_pr_type']}(") or \
       actual_pr_title.startswith(f"{expected['expected_pr_type']}:"):
        score += 0.5

    return round(score, 2)


def score_trajectory(tool_calls: list[str]) -> float:
    """Scores the agent's tool call sequence against the expected workflow."""
    expected = ["map_architecture", "read_file", "create_feature_branch", "request_user_approval"]
    hit = sum(1 for t in expected if t in tool_calls)
    order_bonus = 0.0
    if all(t in tool_calls for t in expected):
        indices = [tool_calls.index(t) for t in expected]
        if indices == sorted(indices):
            order_bonus = 0.2
    return min(1.0, round((hit / len(expected)) + order_bonus, 2))


def generate_llm_judge_prompt(issue: dict, actual_diff: str) -> str:
    """Generates the prompt for the LLM-as-a-judge Semantic Evaluation."""
    return f"""You are an expert Code Reviewer.
The original issue was: '{issue["description"]}'

Review the following Git Diff and score the semantic resolution from 0.0 to 1.0.
Did the autonomous agent actually fix the root cause of the issue securely?

Diff:
{actual_diff}
"""


# ── Runner ────────────────────────────────────────────────────────────────────

async def _run_scenario(agent, local_dir: str, scenario: dict) -> dict:
    """Runs a single eval scenario and returns trajectory + scores."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="eval_user", app_name="eval")
    runner = Runner(agent=agent, session_service=session_service, app_name="eval")

    prompt = (
        f"Fix this issue in the repo at {local_dir}: {scenario['description']}"
    )
    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])

    tool_calls: list[str] = []
    proposed_files: list[str] = []
    pr_title = ""
    error = None

    try:
        async for event in runner.run_async(
            new_message=message, user_id="eval_user", session_id=session.id
        ):
            if not (event.content and event.content.parts):
                continue
            for part in event.content.parts:
                if part.function_call:
                    tool_calls.append(part.function_call.name)
                    args = part.function_call.args or {}
                    if part.function_call.name == "request_user_approval":
                        fp = args.get("filepath", "")
                        if fp:
                            proposed_files.append(os.path.basename(fp))
                    if part.function_call.name == "submit_pull_request":
                        pr_title = str(args.get("title", ""))
    except Exception as e:
        err_str = str(e)
        if err_str.startswith("ApprovalRequired:"):
            # Normal HITL pause — score based on trajectory captured so far
            pass
        else:
            error = err_str

    traj_score = score_trajectory(tool_calls)
    comp_score = score_compliance(scenario, proposed_files, pr_title)

    return {
        "scenario_id": scenario["id"],
        "description": scenario["description"],
        "tool_calls": tool_calls,
        "proposed_files": proposed_files,
        "pr_title": pr_title,
        "trajectory_score": traj_score,
        "compliance_score": comp_score,
        "overall_score": round((traj_score + comp_score) / 2, 2),
        "error": error,
    }


async def run_eval(local_dir: str, scenario_id: str | None = None) -> list[dict]:
    """Runs golden scenarios against the live agent and returns scored results.

    Args:
        local_dir: Path to the local test repository.
        scenario_id: If given, only run this scenario (e.g. "ISSUE-001").
    """
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.agent import root_agent

    dataset = load_dataset()
    if scenario_id:
        dataset = [s for s in dataset if s["id"] == scenario_id]

    results = []
    for scenario in dataset:
        print(f"\n→ Running {scenario['id']}: {scenario['description'][:60]}...")
        result = await _run_scenario(root_agent, local_dir, scenario)
        print(f"  trajectory_score={result['trajectory_score']}  "
              f"compliance_score={result['compliance_score']}  "
              f"overall={result['overall_score']}")
        results.append(result)

    return results


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python evals/eval_suite.py /path/to/local/repo [ISSUE-ID]")
        print("\nLoading dataset to verify setup...")
        dataset = load_dataset()
        print(f"  Loaded {len(dataset)} golden scenarios:")
        for s in dataset:
            print(f"    {s['id']}: {s['description'][:60]}")
        sys.exit(0)

    local_dir = sys.argv[1]
    scenario_id = sys.argv[2] if len(sys.argv) > 2 else None

    results = asyncio.run(run_eval(local_dir, scenario_id))
    print("\n=== Evaluation Results ===")
    print(json.dumps(results, indent=2))

    avg_overall = sum(r["overall_score"] for r in results) / len(results) if results else 0
    print(f"\nAggregate overall score: {avg_overall:.2f}")
