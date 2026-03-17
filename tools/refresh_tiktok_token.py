"""
Auto-refresh TikTok access token using the refresh token stored in .env.

Run on VPS every 23h via systemd timer (tiktok-token-refresh.timer).

Requirements in .env:
    TIKTOK_CLIENT_KEY
    TIKTOK_CLIENT_SECRET
    TIKTOK_REFRESH_TOKEN   ← set this after first manual auth

On success, rewrites TIKTOK_ACCESS_TOKEN and TIKTOK_REFRESH_TOKEN in .env.
"""

import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_PATH)

CLIENT_KEY = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ.get("TIKTOK_REFRESH_TOKEN", "")


def do_refresh(refresh_token: str) -> dict:
    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_env(key: str, value: str) -> None:
    """Replace KEY=... line in .env, or append if missing."""
    text = ENV_PATH.read_text()
    pattern = rf"^{re.escape(key)}=.*$"
    replacement = f"{key}={value}"
    if re.search(pattern, text, flags=re.MULTILINE):
        text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
    else:
        text = text.rstrip("\n") + f"\n{replacement}\n"
    ENV_PATH.write_text(text)


def main():
    if not REFRESH_TOKEN:
        print(
            "ERROR: TIKTOK_REFRESH_TOKEN not set in .env.\n"
            "Run python tiktok_auth.py locally, then copy the refresh_token value\n"
            "into .env as TIKTOK_REFRESH_TOKEN=<value> and re-deploy.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Refreshing TikTok access token...")
    data = do_refresh(REFRESH_TOKEN)

    new_access = data.get("access_token")
    new_refresh = data.get("refresh_token")
    expires_in = data.get("expires_in", "unknown")

    if not new_access:
        print(f"ERROR: no access_token in response: {data}", file=sys.stderr)
        sys.exit(1)

    update_env("TIKTOK_ACCESS_TOKEN", new_access)
    if new_refresh:
        update_env("TIKTOK_REFRESH_TOKEN", new_refresh)

    print(f"✓ Access token refreshed (expires_in={expires_in}s)")
    print(f"✓ .env updated at {ENV_PATH}")


if __name__ == "__main__":
    main()
