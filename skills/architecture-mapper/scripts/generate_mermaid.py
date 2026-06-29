import sys

def convert_to_mermaid(signatures: list[str]) -> str:
    lines = ["classDiagram"]
    current_class = None
    
    for sig in signatures:
        sig = sig.strip()
        if not sig: continue
        
        if sig.startswith("class "):
            if current_class:
                lines.append("  }") # Close previous class
            current_class = sig.replace("class ", "").strip()
            lines.append(f"  class {current_class} {{")
            
        elif sig.startswith("def "):
            method = sig.replace("def ", "").strip()
            method = method.replace("self, ", "").replace("self", "")
            if current_class:
                lines.append(f"    +{method}")
                
    if current_class:
        lines.append("  }")
        
    return "\n".join(lines)

if __name__ == "__main__":
    input_text = sys.stdin.read()
    sigs = input_text.splitlines()
    print(convert_to_mermaid(sigs))
