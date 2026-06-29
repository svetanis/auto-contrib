import unittest
from app.repo_mapper import ast_parser

class TestASTParser(unittest.TestCase):
    def test_extract_signatures(self):
        source_code = """
class MyClass:
    def method_one(self):
        pass

def global_function(arg1, arg2):
    return arg1 + arg2
"""
        signatures = ast_parser.extract_signatures_from_string(source_code)
        
        # Verify that the parser extracts class and method signatures
        self.assertIn("class MyClass", signatures)
        self.assertIn("def method_one(self)", signatures)
        self.assertIn("def global_function(arg1, arg2)", signatures)

if __name__ == "__main__":
    unittest.main()
