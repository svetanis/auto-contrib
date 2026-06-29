import unittest
import subprocess
import os
import sys

class TestGenerateMermaid(unittest.TestCase):
    def test_cli_conversion(self):
        script_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), 
            "../skills/architecture-mapper/scripts/generate_mermaid.py"
        ))
        
        # If the script doesn't exist yet, this will raise FileNotFoundError
        if not os.path.exists(script_path):
            self.fail("Script generate_mermaid.py does not exist yet (TDD failure)")
            
        input_data = "class MyClass\ndef method(self)\n"
        result = subprocess.run(
            [sys.executable, script_path], 
            input=input_data, 
            text=True, 
            capture_output=True
        )
        
        output = result.stdout
        self.assertIn("classDiagram", output)
        self.assertIn("class MyClass {", output)
        self.assertIn("+method()", output)

if __name__ == "__main__":
    unittest.main()
