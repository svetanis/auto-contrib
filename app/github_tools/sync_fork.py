import subprocess
from mcp.types import Tool, TextContent

def run_cmd(cmd: str) -> str:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return result.stdout.strip()

def get_tool() -> Tool:
    return Tool(
        name="sync_upstream_and_fork",
        description="Forks the upstream repo (if not already forked) and clones it locally.",
        inputSchema={
            "type": "object",
            "properties": {
                "upstream_repo": {"type": "string", "description": "Format: owner/repo"},
                "local_dir": {"type": "string", "description": "Local directory to clone into"}
            },
            "required": ["upstream_repo", "local_dir"]
        }
    )

async def execute(arguments: dict) -> list[TextContent]:
    repo = arguments["upstream_repo"]
    local_dir = arguments["local_dir"]
    output = run_cmd(f"gh repo fork {repo} --clone=true -- {local_dir}")
    return [TextContent(type="text", text=f"Fork result:\n{output}")]
