import os
import re
from mcp.types import Tool, TextContent
from app.repo_mapper import ast_parser

# Directories that never contain the source under review — skip to keep the
# diagram focused and readable on real repos.
_SKIP_DIRS = {
    ".venv", "venv", "__pycache__", ".git", "node_modules",
    "build", "dist", ".tox", ".eggs", ".mypy_cache", ".pytest_cache",
    "test", "tests", "docs", "examples",
}

# Non-source files that bloat the diagram (packaging, conftest, test modules).
# __init__.py is skipped too: it re-exports the whole package, so it links to
# every module and becomes a hub that hides the real dependency structure.
# __main__.py is deliberately kept — it's a genuine entry point (and was the
# very file fixed in the python-slugify demo).
_SKIP_FILES = {"setup.py", "conftest.py", "test.py", "tests.py", "__init__.py"}


def _is_test_or_noise(filename: str) -> bool:
    if filename in _SKIP_FILES:
        return True
    stem = filename.rsplit(".", 1)[0]
    return stem.startswith("test_") or stem.endswith("_test") or stem.endswith("_tests")


def get_tool() -> Tool:
    return Tool(
        name="map_architecture",
        description=(
            "Builds a module dependency graph of a repository: a Mermaid flowchart "
            "whose nodes are source modules (grouped into package subgraphs) and whose "
            "edges are intra-repo imports. Each module is annotated with a "
            "'%% file: <absolute_path>' comment so the agent can open it with read_file."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "local_dir": {"type": "string", "description": "Absolute path to the repository directory"}
            },
            "required": ["local_dir"]
        }
    )


def _node_id(key: str) -> str:
    """Mermaid-safe node id (can't start with a digit / contain punctuation)."""
    return "n_" + re.sub(r"\W", "_", key)


async def execute(arguments: dict) -> list[TextContent]:
    directory = os.path.abspath(arguments["local_dir"])

    # Pass 1 — collect one entry per source module: where it lives (group =
    # immediate parent dir, used for subgraphs) and its raw import targets.
    modules: dict[str, dict] = {}
    for root, dirs, files in os.walk(directory):
        # Prune skip-dirs in place so os.walk never descends into them.
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for file in files:
            if not file.endswith((".py", ".java", ".go", ".ts")) or _is_test_or_noise(file):
                continue
            path = os.path.join(root, file)
            abs_path = os.path.abspath(path)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    source = f.read()
            except Exception:
                continue
            basename = os.path.basename(path).rsplit(".", 1)[0].replace("-", "_")
            group = os.path.basename(os.path.dirname(abs_path)) or "root"
            imports = ast_parser.extract_imports_from_string(source, path)

            # Disambiguate the rare case of two modules sharing a basename.
            key, i = basename, 2
            while key in modules and modules[key]["abs_path"] != abs_path:
                key, i = f"{basename}_{i}", i + 1
            modules[key] = {"abs_path": abs_path, "group": group, "imports": imports}

    if not modules:
        return [TextContent(type="text", text="No source files found.")]

    # Pass 2 — keep only edges whose target is another module in THIS repo.
    # (Matching import basenames against known modules filters out stdlib /
    # third-party imports, which never resolve to a node.)
    known = set(modules)
    edges: set[tuple[str, str]] = set()
    for key, info in modules.items():
        for target in info["imports"]:
            tgt = target.replace("-", "_")
            if tgt in known and tgt != key:
                edges.add((key, tgt))

    # Emit a dependency flowchart: package subgraphs of module nodes, then the
    # import edges. `%% file:` comments preserve the agent's navigation contract.
    lines = ["flowchart LR"]
    groups: dict[str, list[str]] = {}
    for key, info in modules.items():
        groups.setdefault(info["group"], []).append(key)
    for group in sorted(groups):
        safe_group = re.sub(r"\W", "_", group) or "root"
        lines.append(f"  subgraph {safe_group}")
        for key in sorted(groups[group]):
            lines.append(f'    {_node_id(key)}["{key}"]')
        lines.append("  end")

    for key in sorted(modules):
        lines.append(f"  %% file: {modules[key]['abs_path']}")

    for src, dst in sorted(edges):
        lines.append(f"  {_node_id(src)} --> {_node_id(dst)}")

    return [TextContent(type="text", text="\n".join(lines))]
