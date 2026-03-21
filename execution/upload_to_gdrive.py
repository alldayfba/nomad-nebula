#!/usr/bin/env python3
"""
Script: upload_to_gdrive.py
Purpose: Create Google Docs from KD Amazon FBA funnel markdown files and
         upload HTML files to a Google Drive folder — using service account auth.
Inputs:  service_account.json (from Google Cloud → IAM → Service Accounts → Keys)
Outputs: Google Drive folder "KD Amazon FBA Funnel" shared with SHARE_WITH_EMAIL
"""

import os
import sys
import json
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ── Config ────────────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]

PROJECT_ROOT      = Path(__file__).parent.parent
CLIENT_DIR        = PROJECT_ROOT / "clients" / "kd-amazon-fba"
SA_FILE           = PROJECT_ROOT / "service_account.json"
RESULTS_FILE      = PROJECT_ROOT / ".tmp" / "gdrive_upload_results.json"
DRIVE_FOLDER_NAME = "KD Amazon FBA Funnel"

# Email to share the Drive folder with (set via env or hardcoded)
SHARE_WITH_EMAIL = os.getenv("GOOGLE_SHARE_EMAIL", "")

# Files → Google Docs (markdown source, display title)
MD_FILES = [
    (CLIENT_DIR / "README.md",                               "KD Amazon FBA — Overview & Setup Checklist"),
    (CLIENT_DIR / "scripts" / "vsl-script.md",              "VSL Script — Full 15–18 Min"),
    (CLIENT_DIR / "scripts" / "closing-call-script.md",     "Closing Call Script"),
    (CLIENT_DIR / "scripts" / "setter-outreach-script.md",  "Setter Outreach Script"),
    (CLIENT_DIR / "emails"  / "all-email-sequences.md",     "All Email Sequences"),
    (CLIENT_DIR / "sms"     / "sms-workflows.md",           "SMS Workflows"),
    (CLIENT_DIR / "ads"     / "ad-copy.md",                 "Ad Copy — Meta & YouTube"),
]

# Files → raw Drive upload
RAW_FILES = [
    (CLIENT_DIR / "funnel" / "index.html",        "index.html — VSL Landing Page"),
    (CLIENT_DIR / "funnel" / "confirmation.html", "confirmation.html — Post-Booking Page"),
    (CLIENT_DIR / "funnel" / "drop-sell.html",    "drop-sell.html — Disqualified Page"),
]

# ── Auth ──────────────────────────────────────────────────────────────────────

def get_services():
    if not SA_FILE.exists():
        print(f"\n❌ service_account.json not found at:\n   {SA_FILE}")
        print("\n   Steps:")
        print("   1. console.cloud.google.com → IAM & Admin → Service Accounts")
        print("   2. Create Service Account → name it 'antigravity-uploader' → Done")
        print("   3. Click the service account → Keys → Add Key → JSON → Create")
        print(f"   4. Save the downloaded file as: {SA_FILE}")
        sys.exit(1)

    creds = service_account.Credentials.from_service_account_file(str(SA_FILE), scopes=SCOPES)
    drive = build("drive", "v3", credentials=creds)
    docs  = build("docs",  "v1", credentials=creds)
    return drive, docs

# ── Drive Helpers ─────────────────────────────────────────────────────────────

def get_or_create_folder(drive, name):
    q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    existing = drive.files().list(q=q, fields="files(id,name)").execute().get("files", [])
    if existing:
        fid = existing[0]["id"]
        print(f"📁 Using existing folder: {name}")
        return fid
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    f = drive.files().create(body=meta, fields="id").execute()
    print(f"📁 Created folder: {name}")
    return f["id"]


def share_folder(drive, folder_id, email=None):
    # Make accessible to anyone with the link (writer)
    drive.permissions().create(
        fileId=folder_id,
        body={"type": "anyone", "role": "writer"},
    ).execute()
    print(f"🔗 Folder shared: anyone with the link can edit")


def move_to_folder(drive, file_id, folder_id):
    f = drive.files().get(fileId=file_id, fields="parents").execute()
    prev = ",".join(f.get("parents", []))
    drive.files().update(
        fileId=file_id,
        addParents=folder_id,
        removeParents=prev,
        fields="id,parents",
    ).execute()


def create_doc(docs, drive, title: str, md_path: Path, folder_id: str) -> str:
    """Upload markdown as a Google Doc using Drive import (no Docs API needed)."""
    media = MediaFileUpload(str(md_path), mimetype="text/plain", resumable=False)
    f = drive.files().create(
        body={
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [folder_id],
        },
        media_body=media,
        fields="id,webViewLink",
    ).execute()
    url = f.get("webViewLink", f"https://docs.google.com/document/d/{f['id']}/edit")
    print(f"  ✅ {title}")
    print(f"     {url}")
    return url


def upload_file(drive, path: Path, name: str, folder_id: str) -> str:
    media = MediaFileUpload(str(path), mimetype="text/html")
    f = drive.files().create(
        body={"name": name, "parents": [folder_id]},
        media_body=media,
        fields="id,webViewLink",
    ).execute()
    url = f.get("webViewLink", "")
    print(f"  ✅ {name}")
    print(f"     {url}")
    return url

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n🔐 Authenticating with Google (service account)...")
    drive, _ = get_services()
    print("   ✅ Authenticated")

    print(f"\n📁 Setting up Drive folder: '{DRIVE_FOLDER_NAME}'...")
    folder_id = get_or_create_folder(drive, DRIVE_FOLDER_NAME)
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"

    share_folder(drive, folder_id)

    results = {"folder": folder_url, "docs": [], "files": []}

    print(f"\n📝 Creating Google Docs ({len(MD_FILES)} files)...")
    for md_path, title in MD_FILES:
        if not md_path.exists():
            print(f"  ⚠️  Not found: {md_path.name}")
            continue
        url = create_doc(None, drive, title, md_path, folder_id)
        results["docs"].append({"title": title, "url": url})

    print(f"\n🌐 Uploading HTML pages ({len(RAW_FILES)} files)...")
    for path, name in RAW_FILES:
        if not path.exists():
            print(f"  ⚠️  Not found: {path.name}")
            continue
        url = upload_file(drive, path, name, folder_id)
        results["files"].append({"name": name, "url": url})

    RESULTS_FILE.parent.mkdir(exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(results, indent=2))

    print(f"\n{'─'*60}")
    print("✅ ALL DONE")
    print(f"{'─'*60}")
    print(f"📁 Drive folder:  {folder_url}")
    for d in results["docs"]:
        print(f"📄 {d['title']}")
        print(f"   {d['url']}")
    for f in results["files"]:
        print(f"🌐 {f['name']}")
        print(f"   {f['url']}")
    print(f"{'─'*60}")


if __name__ == "__main__":
    main()
