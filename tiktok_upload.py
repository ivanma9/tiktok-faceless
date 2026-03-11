"""Upload and publish a video to TikTok via Content Posting API."""

import argparse
import json
import sys
from pathlib import Path

import requests

from tiktok_auth import load_tokens, refresh_token, save_tokens


API_BASE = "https://open.tiktokapis.com/v2"


def get_access_token() -> str:
    tokens = load_tokens()
    if not tokens:
        print("No tokens found. Run tiktok_auth.py first.")
        sys.exit(1)
    return tokens["access_token"]


def init_video_upload(access_token: str, video_path: Path, privacy: str = "SELF_ONLY") -> dict:
    """Initialize a direct post video upload."""
    file_size = video_path.stat().st_size

    resp = requests.post(
        f"{API_BASE}/post/publish/video/init/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={
            "post_info": {
                "title": "Uploaded via API",
                "privacy_level": privacy,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        },
    )
    resp.raise_for_status()
    return resp.json()


def upload_video_chunk(upload_url: str, video_path: Path) -> int:
    """Upload the video file to TikTok's upload URL."""
    file_size = video_path.stat().st_size

    with open(video_path, "rb") as f:
        resp = requests.put(
            upload_url,
            headers={
                "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
                "Content-Type": "video/mp4",
            },
            data=f,
        )
    resp.raise_for_status()
    return resp.status_code


def check_publish_status(access_token: str, publish_id: str) -> dict:
    """Check the status of a published video."""
    resp = requests.post(
        f"{API_BASE}/post/publish/status/fetch/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={"publish_id": publish_id},
    )
    resp.raise_for_status()
    return resp.json()


def upload_and_publish(video_path: str, privacy: str = "SELF_ONLY", title: str | None = None):
    """Full flow: init upload, send file, report status."""
    path = Path(video_path)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    access_token = get_access_token()

    # Step 1: Initialize upload
    print(f"Initializing upload for {path.name} ({path.stat().st_size / 1024 / 1024:.1f} MB)...")
    init_resp = init_video_upload(access_token, path, privacy)

    if init_resp.get("error", {}).get("code") != "ok":
        print(f"Init failed: {json.dumps(init_resp, indent=2)}")
        sys.exit(1)

    data = init_resp["data"]
    publish_id = data["publish_id"]
    upload_url = data["upload_url"]
    print(f"Publish ID: {publish_id}")

    # Step 2: Upload video chunk
    print("Uploading video...")
    upload_video_chunk(upload_url, path)
    print("Upload complete.")

    # Step 3: Check status
    print("Checking publish status...")
    status = check_publish_status(access_token, publish_id)
    print(json.dumps(status, indent=2))

    return publish_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload a video to TikTok")
    parser.add_argument("video", help="Path to video file (mp4)")
    parser.add_argument(
        "--privacy",
        default="SELF_ONLY",
        choices=["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"],
        help="Privacy level (default: SELF_ONLY for sandbox)",
    )
    parser.add_argument("--title", default=None, help="Video title/description")
    args = parser.parse_args()

    upload_and_publish(args.video, args.privacy, args.title)
