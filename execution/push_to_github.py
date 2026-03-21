#!/usr/bin/env python3
"""
Script: push_to_github.py
Purpose: Create a GitHub repo and push the kd-amazon-fba-funnel project.
         Also enables GitHub Pages for live funnel URL.
Inputs:  GITHUB_TOKEN env var or prompted interactively
         GITHUB_USERNAME env var or prompted interactively
Outputs: Public GitHub repo + GitHub Pages URL
"""

import os
import sys
import subprocess
import json
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
FUNNEL_DIR   = PROJECT_ROOT / "clients" / "kd-amazon-fba"
REPO_NAME    = "kd-amazon-fba-funnel"

def api_call(method: str, path: str, token: str, data: dict = None):
    """Make a GitHub REST API call. Returns response dict."""
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"\n❌ GitHub API error {e.code}: {error_body}")
        return None


def run(cmd: str, cwd: Path = None, env: dict = None) -> bool:
    """Run a shell command. Returns True on success."""
    result = subprocess.run(cmd, shell=True, cwd=cwd, env=env,
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()}")
        return False
    if result.stdout.strip():
        print(f"  {result.stdout.strip()}")
    return True


def main():
    print("\n🐙 GitHub Repo Setup — KD Amazon FBA Funnel")
    print("─" * 50)

    # Get token
    token = os.getenv("GITHUB_TOKEN") or input("\nPaste your GitHub Personal Access Token: ").strip()
    if not token:
        print("❌ No token provided. Exiting.")
        sys.exit(1)

    # Get username
    username = os.getenv("GITHUB_USERNAME")
    if not username:
        print("\n🔍 Looking up your GitHub username...")
        user_data = api_call("GET", "/user", token)
        if not user_data:
            print("❌ Could not authenticate. Check your token and try again.")
            sys.exit(1)
        username = user_data["login"]
        print(f"   Logged in as: {username}")

    # Check if repo already exists
    existing = api_call("GET", f"/repos/{username}/{REPO_NAME}", token)
    if existing and "id" in existing:
        repo_url = existing["html_url"]
        clone_url = existing["clone_url"]
        print(f"\n📦 Repo already exists: {repo_url}")
    else:
        # Create repo
        print(f"\n📦 Creating repo: {REPO_NAME}...")
        repo_data = api_call("POST", "/user/repos", token, {
            "name": REPO_NAME,
            "description": "KD Amazon FBA VSL Call Funnel — VSL script, emails, SMS, ads, and HTML pages",
            "private": False,
            "auto_init": False,
        })
        if not repo_data or "id" not in repo_data:
            print("❌ Failed to create repo. Check token permissions (needs 'repo' scope).")
            sys.exit(1)
        repo_url = repo_data["html_url"]
        clone_url = repo_data["clone_url"]
        print(f"   ✅ Created: {repo_url}")

    # Set up git remote using token in URL (HTTPS auth)
    auth_remote = clone_url.replace("https://", f"https://{token}@")

    print(f"\n📤 Pushing to GitHub...")

    # Check if remote already set
    check = subprocess.run("git remote get-url origin", shell=True, cwd=FUNNEL_DIR,
                           capture_output=True, text=True)
    if check.returncode == 0:
        # Update remote
        run(f"git remote set-url origin {auth_remote}", cwd=FUNNEL_DIR)
    else:
        run(f"git remote add origin {auth_remote}", cwd=FUNNEL_DIR)

    if not run("git push -u origin main", cwd=FUNNEL_DIR):
        print("❌ Push failed. Is the repo empty on GitHub? Try:")
        print("   git pull origin main --rebase --allow-unrelated-histories")
        sys.exit(1)

    print("   ✅ Pushed successfully")

    # Rename remote to strip token from stored URL (security hygiene)
    clean_remote = f"https://github.com/{username}/{REPO_NAME}.git"
    run(f"git remote set-url origin {clean_remote}", cwd=FUNNEL_DIR)

    # Enable GitHub Pages (serve from /funnel subfolder on main branch)
    print(f"\n🌐 Enabling GitHub Pages...")
    pages = api_call("POST", f"/repos/{username}/{REPO_NAME}/pages", token, {
        "source": {"branch": "main", "path": "/funnel"},
    })
    if pages and "html_url" in pages:
        pages_url = pages["html_url"]
    else:
        # Pages may already be enabled — try GET
        pages_get = api_call("GET", f"/repos/{username}/{REPO_NAME}/pages", token)
        pages_url = pages_get.get("html_url", f"https://{username}.github.io/{REPO_NAME}/") if pages_get else f"https://{username}.github.io/{REPO_NAME}/"

    print(f"   ✅ Pages enabled")
    print(f"\n" + "─" * 60)
    print("✅ ALL DONE")
    print("─" * 60)
    print(f"📦 GitHub repo:      {repo_url}")
    print(f"🌐 Live funnel URL:  {pages_url}")
    print(f"   (Pages can take 1–2 minutes to go live after first push)")
    print("─" * 60)


if __name__ == "__main__":
    main()
