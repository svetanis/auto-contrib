import unittest
from unittest.mock import patch, MagicMock
import os

class TestSquashCommits(unittest.TestCase):

    @patch("subprocess.run")
    def test_squash(self, mock_run):
        script_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), 
            "../skills/pr-compliance-formatter/scripts/squash_wip_commits.py"
        ))
        
        if not os.path.exists(script_path):
            self.fail("Script squash_wip_commits.py does not exist yet! (TDD failure)")
            
        # Mock subprocess returns
        mock_merge_base = MagicMock()
        mock_merge_base.returncode = 0
        mock_merge_base.stdout = "abcdef123456"
        
        mock_success = MagicMock()
        mock_success.returncode = 0
        
        mock_run.side_effect = [mock_merge_base, mock_success, mock_success, mock_success]
        
        # Dynamically load the script
        import importlib.util
        spec = importlib.util.spec_from_file_location("squasher", script_path)
        squasher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(squasher)
        
        result = squasher.squash_commits("/tmp/repo", "feat(auth): add login", "main")
        self.assertTrue(result)
        
        # Verify it found the merge base and ran the soft reset
        self.assertIn("git merge-base main HEAD", mock_run.call_args_list[0][0][0])
        self.assertIn("git reset --soft abcdef123456", mock_run.call_args_list[1][0][0])
        self.assertIn('git commit -m "feat(auth): add login"', mock_run.call_args_list[2][0][0])

if __name__ == "__main__":
    unittest.main()
