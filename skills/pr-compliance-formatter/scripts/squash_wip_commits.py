import subprocess
import sys

def run_cmd(cmd: str, cwd: str) -> str:
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{result.stderr}")
    return result.stdout.strip()

def squash_commits(repo_dir: str, final_message: str, base_branch: str = "main") -> bool:
    try:
        # Find the point where our feature branch split from main
        merge_base = run_cmd(f"git merge-base {base_branch} HEAD", repo_dir)
        
        # Soft reset to that point (keeps all file changes staged)
        run_cmd(f"git reset --soft {merge_base}", repo_dir)
        
        # Commit everything with the compliant Conventional Commit message
        escaped_msg = final_message.replace('"', '\\"')
        run_cmd(f'git commit -m "{escaped_msg}"', repo_dir)
        return True
    except RuntimeError as e:
        print(e)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python squash_wip_commits.py <repo_dir> <commit_message>")
        sys.exit(1)
    squash_commits(sys.argv[1], sys.argv[2])
