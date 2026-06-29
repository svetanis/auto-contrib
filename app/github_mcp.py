import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from app.github_tools import sync_fork
from app.github_tools import feature_branch
from app.github_tools import push_wip
from app.github_tools import poll_logs
from app.github_tools import submit_pr
from app.github_tools import read_file

server = Server("github-mcp")

TOOL_HANDLERS = {
    "sync_upstream_and_fork": sync_fork.execute,
    "create_feature_branch": feature_branch.execute,
    "push_wip_commit": push_wip.execute,
    "poll_github_actions_logs": poll_logs.execute,
    "submit_pull_request": submit_pr.execute,
    "read_file": read_file.execute,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        sync_fork.get_tool(),
        feature_branch.get_tool(),
        push_wip.get_tool(),
        poll_logs.get_tool(),
        submit_pr.get_tool(),
        read_file.get_tool(),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name in TOOL_HANDLERS:
        return await TOOL_HANDLERS[name](arguments)
    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
