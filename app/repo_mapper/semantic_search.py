import os
from mcp.types import Tool, TextContent
from app.repo_mapper import vector_store

# Global in-memory store for the session
_store = vector_store.VectorStore()
_indexed_directories = set()

def get_tool() -> Tool:
    return Tool(
        name="semantic_search",
        description="Indexes a directory (if not already indexed) and performs a semantic search over its code.",
        inputSchema={
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Absolute path to index"},
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "description": "Number of results (default 5)"}
            },
            "required": ["directory", "query"]
        }
    )

async def execute(arguments: dict) -> list[TextContent]:
    directory = arguments["directory"]
    query = arguments["query"]
    top_k = arguments.get("top_k", 5)
    
    if directory not in _indexed_directories:
        for root, _, files in os.walk(directory):
            if ".venv" in root or "__pycache__" in root or ".git" in root: continue
            for file in files:
                if file.endswith((".py", ".md", ".txt")):
                    path = os.path.join(root, file)
                    try:
                        with open(path, "r", encoding="utf-8") as f: _store.add_document(path, f.read())
                    except Exception: pass
        _indexed_directories.add(directory)
        
    results = _store.search(query, top_k)
    if not results: return [TextContent(type="text", text="No results found.")]
        
    output = []
    for i, doc in enumerate(results):
        output.append(f"Result {i+1}:\nFile: {doc['file_path']}\nContent Preview:\n{doc['content'][:200]}...\n")
        
    return [TextContent(type="text", text="\n".join(output))]
