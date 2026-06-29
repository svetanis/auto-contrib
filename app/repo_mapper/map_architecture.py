import os
from mcp.types import Tool, TextContent
from app.repo_mapper import ast_parser

def get_tool() -> Tool:
    return Tool(
        name="map_architecture",
        description="Extracts class and function signatures from all Python, Java, Go, and TypeScript files in a directory.",
        inputSchema={
            "type": "object",
            "properties": {
                "local_dir": {"type": "string", "description": "Absolute path to the repository directory"}
            },
            "required": ["local_dir"]
        }
    )

async def execute(arguments: dict) -> list[TextContent]:
    directory = arguments["local_dir"]
    # Resolve to an absolute path so agents always receive real paths
    directory = os.path.abspath(directory)
    mermaid_lines = ["classDiagram"]
    
    for root, _, files in os.walk(directory):
        if ".venv" in root or "__pycache__" in root or ".git" in root:
            continue
        for file in files:
            if file.endswith((".py", ".java", ".go", ".ts")):
                path = os.path.join(root, file)
                abs_path = os.path.abspath(path)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        source = f.read()
                    sigs = ast_parser.extract_signatures_from_string(source, path)
                    if sigs:
                        basename = os.path.basename(path).split('.')[0].replace('-', '_')
                        current_class = f"File_{basename}"
                        # Embed the absolute path as a note so the agent knows where the file is
                        mermaid_lines.append(f"  %% file: {abs_path}")
                        mermaid_lines.append(f"  class {current_class} {{")
                        for sig in sigs:
                            if sig.startswith("class "):
                                mermaid_lines.append("  }")
                                current_class = sig.replace("class ", "").strip()
                                mermaid_lines.append(f"  class {current_class} {{")
                            elif sig.startswith("def "):
                                method = sig.replace("def ", "").strip()
                                mermaid_lines.append(f"    +{method}")
                        mermaid_lines.append("  }")
                except Exception as e:
                    pass
                    
    if len(mermaid_lines) <= 1:
        return [TextContent(type="text", text="No source files found.")]
        
    mermaid_str = "\n".join(mermaid_lines)
    return [TextContent(type="text", text=mermaid_str)]
