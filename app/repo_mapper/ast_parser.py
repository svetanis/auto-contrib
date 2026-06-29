import ast
import re

def extract_signatures_from_string(source_code: str, file_path: str = ".py") -> list[str]:
    """Parses source code and extracts class and function signatures."""
    if file_path.endswith(".java"): return _extract_java(source_code)
    if file_path.endswith(".go"): return _extract_go(source_code)
    if file_path.endswith(".ts"): return _extract_ts(source_code)
    return _extract_python(source_code)

def _extract_python(source_code: str) -> list[str]:
    signatures = []
    try:
        tree = ast.parse(source_code)
    except SyntaxError: return signatures
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            signatures.append(f"class {node.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            signatures.append(f"def {node.name}({', '.join(args)})")
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
