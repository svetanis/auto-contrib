import ast
import re

def extract_signatures_from_string(source_code: str, file_path: str = ".py") -> list[str]:
    """Parses source code and extracts class and function signatures."""
    if file_path.endswith(".java"): return _extract_java(source_code)
    if file_path.endswith(".go"): return _extract_go(source_code)
    if file_path.endswith(".ts"): return _extract_ts(source_code)
    return _extract_python(source_code)


def extract_imports_from_string(source_code: str, file_path: str = ".py") -> list[str]:
    """Returns candidate imported module basenames, for building a dependency graph.

    Only Python is supported for now (the AST makes intra-repo import resolution
    reliable). Each returned name is the *last dotted component* of an import
    target, e.g. `from .domain import x` and `from pkg.domain import x` both yield
    "domain". The caller keeps only names that match a known repo module, which
    naturally filters out stdlib/third-party imports.
    """
    if not file_path.endswith(".py"):
        return []
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # `from .domain import x` -> module "domain"; `from . import a, b` ->
            # module is None, so the imported names themselves are the modules.
            if node.module:
                targets.append(node.module.split(".")[-1])
            if node.level:  # relative import: names may be sibling submodules
                targets.extend(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.Import):
            targets.extend(alias.name.split(".")[-1] for alias in node.names)
    return targets

def _extract_python(source_code: str) -> list[str]:
    signatures = []
    try:
        tree = ast.parse(source_code)
    except SyntaxError: return signatures
    # Walk top-level nodes in source order so each class is immediately followed
    # by its own methods. ast.walk() is breadth-first and would emit all classes
    # first, then all methods, mis-assigning methods in multi-class files.
    def _func_sig(fn) -> str:
        args = [a.arg for a in fn.args.args]
        return f"def {fn.name}({', '.join(args)})"
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            signatures.append(f"class {node.name}")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    signatures.append(_func_sig(item))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            signatures.append(_func_sig(node))
    return signatures

def _extract_java(source_code: str) -> list[str]:
    signatures = []
    class_rx = re.compile(r'(?:public|protected|private)?\s*(?:static\s+)?class\s+(\w+)')
    method_rx = re.compile(r'(?:public|protected|private)\s+(?:static\s+)?[\w<>\[\]]+\s+(\w+)\s*\(')
    for line in source_code.splitlines():
        if class_rx.search(line): signatures.append(f"class {class_rx.search(line).group(1)}")
        elif method_rx.search(line): signatures.append(f"def {method_rx.search(line).group(1)}()")
    return signatures

def _extract_go(source_code: str) -> list[str]:
    signatures = []
    type_rx = re.compile(r'type\s+(\w+)\s+(?:struct|interface)')
    func_rx = re.compile(r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(')
    for line in source_code.splitlines():
        if type_rx.search(line): signatures.append(f"class {type_rx.search(line).group(1)}")
        elif func_rx.search(line): signatures.append(f"def {func_rx.search(line).group(1)}()")
    return signatures

def _extract_ts(source_code: str) -> list[str]:
    signatures = []
    class_rx = re.compile(r'(?:export\s+)?(?:default\s+)?(?:class|interface)\s+(\w+)')
    method_rx = re.compile(r'(?:public|protected|private)?\s*(?:static\s+)?(?:async\s+)?(\w+)\s*\(')
    for line in source_code.splitlines():
        if class_rx.search(line): signatures.append(f"class {class_rx.search(line).group(1)}")
        elif method_rx.search(line):
            match = method_rx.search(line).group(1)
            if match not in ["if", "for", "while", "catch", "switch"]:
                signatures.append(f"def {match}()")
    return signatures
