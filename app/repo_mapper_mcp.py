import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from app.repo_mapper import map_architecture
from app.repo_mapper import semantic_search

server = Server("repo-mapper-mcp")

TOOL_HANDLERS = {
    "map_architecture": map_architecture.execute,
    "semantic_search": semantic_search.execute,
}

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Dynamically loads tool definitions."""
    return [
        map_architecture.get_tool(),
        semantic_search.get_tool(),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Routes execution to the correct handler function."""
    if name in TOOL_HANDLERS:
        return await TOOL_HANDLERS[name](arguments)
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
