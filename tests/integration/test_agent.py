# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.skill_toolset import SkillToolset

from app.agent import root_agent, _skills


def test_agent_has_mcp_toolsets() -> None:
    """Agent must expose both MCP servers as McpToolset entries (SSE transport)."""
    mcp_toolsets = [t for t in root_agent.tools if isinstance(t, McpToolset)]
    assert len(mcp_toolsets) == 2, (
        f"Expected 2 McpToolset (github-mcp SSE + repo-mapper-mcp SSE), got {len(mcp_toolsets)}"
    )


def test_agent_has_skill_toolset() -> None:
    """Agent must expose a SkillToolset with all 4 skills loaded."""
    skill_toolsets = [t for t in root_agent.tools if isinstance(t, SkillToolset)]
    assert len(skill_toolsets) == 1, (
        f"Expected 1 SkillToolset, got {len(skill_toolsets)}"
    )


def test_all_four_skills_loaded() -> None:
    """All 4 agent skills must be present in the skill registry."""
    expected = {"architecture-mapper", "code-implementer", "test-debugger", "pr-compliance-formatter"}
    actual = {s.name for s in _skills}
    assert actual == expected, f"Missing skills: {expected - actual}"


def test_hitl_gate_present() -> None:
    """The HITL gate (request_user_approval) must remain as a Python function tool."""
    callable_tools = [t for t in root_agent.tools if callable(t)]
    names = [getattr(t, "__name__", "") for t in callable_tools]
    assert "request_user_approval" in names, (
        "request_user_approval not found in agent tools"
    )


def test_agent_instruction_references_skills() -> None:
    """System instruction must reference load_skill and the skill names."""
    instr = root_agent.instruction
    assert "load_skill" in instr, "Instruction must reference load_skill tool"
    for skill_name in ["architecture-mapper", "code-implementer", "test-debugger", "pr-compliance-formatter"]:
        assert skill_name in instr, f"Skill '{skill_name}' not mentioned in instruction"
