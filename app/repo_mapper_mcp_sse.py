"""Repo-mapper MCP server — SSE transport (FastMCP).

Exposes repository analysis tools over HTTP/SSE so ADK's McpToolset can
connect without stdio subprocess issues on Windows.

Start this automatically via agent.py's background thread.
Connect from ADK with:
    SseConnectionParams(url="http://127.0.0.1:8002/sse")
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("repo-mapper-mcp")


@mcp.tool()
async def map_architecture(local_dir: str) -> str:
    """Extracts class and function signatures from all Python, Java, Go, and TypeScript
    files in a directory. Returns a Mermaid classDiagram with %% file: <absolute_path>
    comments — use those absolute paths when calling read_file.

    Args:
        local_dir: Path to the repository directory to analyse.
    """
    from app.repo_mapper import map_architecture as _mod
    results = await _mod.execute({"local_dir": local_dir})
    return results[0].text if results else "No source files found."


@mcp.tool()
async def semantic_search(directory: str, query: str, top_k: int = 5) -> str:
    """Indexes a directory (on first call) and performs a keyword search over its code.

    Args:
        directory: Absolute path to the repository directory to index.
        query: Search query string.
        top_k: Number of results to return (default 5).
    """
    from app.repo_mapper import semantic_search as _mod
    results = await _mod.execute({"directory": directory, "query": query, "top_k": top_k})
    return results[0].text if results else "No results found."
