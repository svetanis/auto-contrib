---
name: architecture-mapper
description: Generates visual Mermaid.js dependency graphs of target codebases by utilizing the repo-mapper-mcp server to extract class and function signatures.
---

# Architecture Mapper Skill

When you are asked to map or visualize the architecture of a repository, follow these steps exactly:

1. **Extract Signatures**: Call the `repo-mapper-mcp` server's `map_architecture` tool on the target directory to extract all class definitions and function signatures.
2. **Generate Mermaid Graph**: Use the `scripts/generate_mermaid.py` helper script to automatically convert the AST signatures into a Mermaid class diagram. If the helper script is unavailable, write the Mermaid diagram manually using `classDiagram` syntax.
3. **Format Output**: Present the result to the user as a Markdown artifact. Use a fenced code block with the `mermaid` language identifier so the user interface automatically renders it as a visual graph.

## Mermaid Syntax Rules:
- Always use `classDiagram`.
- Do not use HTML tags in labels.
- If a method or class has special characters, ensure it is properly quoted.

For a perfect example of what the final output should look like, review `examples/diagram_example.md`.
