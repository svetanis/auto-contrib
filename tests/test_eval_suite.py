import unittest
import sys
import os

# Import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from evals import eval_suite

class TestEvalSuite(unittest.TestCase):
    
    def test_score_compliance_perfect(self):
        expected = {
            "expected_files_modified": ["foo.py", "bar.py"],
            "expected_pr_type": "fix"
        }
        # Perfect match
        score = eval_suite.score_compliance(expected, ["foo.py", "bar.py"], "fix(auth): solved the bug")
        self.assertEqual(score, 1.0)
        
    def test_score_compliance_partial(self):
        expected = {
            "expected_files_modified": ["foo.py", "bar.py"],
            "expected_pr_type": "feat"
        }
        # Missed a file, but got the PR type right
        score = eval_suite.score_compliance(expected, ["foo.py"], "feat(ui): added button")
        self.assertEqual(score, 0.5)

    def test_generate_prompt(self):
        issue = {"description": "Fix the null bug"}
        prompt = eval_suite.generate_llm_judge_prompt(issue, "+ foo\n- bar")
        self.assertIn("Fix the null bug", prompt)
        self.assertIn("+ foo", prompt)

if __name__ == "__main__":
    unittest.main()
