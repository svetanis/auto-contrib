---
name: architecture-mapper
description: Generates a visual Mermaid.js module dependency graph of a target codebase by calling the repo-mapper-mcp server, which maps intra-repo imports between source modules.
---

# Architecture Mapper Skill

When you are asked to map or visualize the architecture of a repository, follow these steps exactly:

1. **Build the dependency graph**: Call the `repo-mapper-mcp` server's `map_architecture` tool on the target directory. It returns a ready-to-render Mermaid `flowchart` whose nodes are source modules (grouped into package subgraphs) and whose edges are the imports between them. Each module carries a `%% file: <absolute_path>` comment.
2. **Present it**: Show the tool's Mermaid output to the user as a Markdown artifact — a fenced code block with the `mermaid` language identifier so the UI renders it as a visual graph. The tool already emits valid Mermaid; do not rewrite it into a class diagram.
3. **Reason from it**: Use the edges to understand how the code fits together (which modules are shared cores, which are leaves) and the `%% file:` comments to open specific files with `read_file`.

## Notes:
- The output is a `flowchart` (a dependency graph), not a `classDiagram`. Present it as-is.
- Isolated nodes (no edges) are normal — they are modules with no intra-repo imports.
- `__init__.py` re-export files are intentionally omitted so the real structure stays visible.

For an example of the rendered result, review `examples/diagram_example.md`.
