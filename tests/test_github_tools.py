import unittest
from unittest.mock import patch, MagicMock
import asyncio
import json
import os

# Import the modules to test
from app.github_tools import sync_fork, feature_branch, push_wip, poll_logs, submit_pr

class TestGithubTools(unittest.IsolatedAsyncioTestCase):

    @patch("app.github_tools.sync_fork.subprocess.run")
    async def test_sync_fork(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Forked successfully"
        mock_run.return_value = mock_result
        
        args = {"upstream_repo": "owner/repo", "local_dir": "/tmp/repo"}
        result = await sync_fork.execute(args)
        
        mock_run.assert_called_once_with("gh repo fork owner/repo --clone=true -- /tmp/repo", shell=True, capture_output=True, text=True)
        self.assertIn("Fork result:", result[0].text)

    @patch("app.github_tools.push_wip.subprocess.run")
    async def test_push_wip(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_run.return_value = mock_result
        
        args = {"local_dir": "/tmp/repo", "commit_message": "Fix \"bug\""}
        result = await push_wip.execute(args)
        
        # Verify that three commands were run (add, commit, push)
        self.assertEqual(mock_run.call_count, 3)
        
        # Verify the commit message escaping
        commit_cmd = mock_run.call_args_list[1][0][0]
        self.assertIn('git commit -m "Fix \\"bug\\""', commit_cmd)

    @patch("app.github_tools.feature_branch.subprocess.run")
    async def test_feature_branch(self, mock_run):
        mock_sha_result = MagicMock()
        mock_sha_result.returncode = 0
        mock_sha_result.stdout = json.dumps({"object": {"sha": "12345abcdef"}})
        
        mock_success = MagicMock()
        mock_success.returncode = 0
        mock_success.stdout = "Branch created"
        
        # Return SHA for the first call, success for the rest
        mock_run.side_effect = [mock_sha_result, mock_success, mock_success]
        
        args = {
            "upstream_repo": "owner/repo",
            "forked_repo": "user/repo",
            "branch_name": "feature-1",
            "local_dir": "/tmp/repo"
        }
        result = await feature_branch.execute(args)
        
        # The first call should fetch the SHA
        sha_cmd = mock_run.call_args_list[0][0][0]
        self.assertIn("gh api repos/owner/repo/git/refs/heads/main", sha_cmd)
        
        # The second call should create the branch using the exact SHA
        create_cmd = mock_run.call_args_list[1][0][0]
        self.assertIn("sha='12345abcdef'", create_cmd)
        
        self.assertIn("Branch feature-1 created cleanly", result[0].text)

if __name__ == "__main__":
    unittest.main()
