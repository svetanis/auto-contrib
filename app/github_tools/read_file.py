from mcp.types import Tool, TextContent


def get_tool() -> Tool:
    return Tool(
        name="read_file",
        description=(
            "Reads and returns the full contents of a file. "
            "Use this to inspect source code before proposing edits so you can copy old_text verbatim."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Absolute path to the file to read"},
            },
            "required": ["filepath"],
        },
    )


async def execute(arguments: dict) -> list[TextContent]:
    try:
        with open(arguments["filepath"], "r", encoding="utf-8") as f:
            return [TextContent(type="text", text=f.read())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]
