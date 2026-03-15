"""TikTok OAuth 2.0 flow with GitHub Pages callback."""

import json
import os
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_KEY = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]
REDIRECT_URI = os.environ.get(
    "TIKTOK_REDIRECT_URI",
    "https://ivanma9.github.io/tiktok-faceless/callback.html",
)
TOKEN_FILE = Path(__file__).parent / "tokens.json"
SCOPES = "user.info.basic,video.publish,video.upload"


def get_auth_url() -> str:
    params = {
        "client_key": CLIENT_KEY,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
    }
    return f"https://www.tiktok.com/v2/auth/authorize/?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
    )
    resp.raise_for_status()
    return resp.json()


def refresh_token(token: str) -> dict:
    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": token,
        },
    )
    resp.raise_for_status()
    return resp.json()


def save_tokens(data: dict):
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    print(f"Tokens saved to {TOKEN_FILE}")


def load_tokens() -> dict | None:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return None


def run_auth_flow():
    """Open browser for OAuth, then prompt user to paste the code."""
    auth_url = get_auth_url()
    print(f"Opening browser for TikTok authorization...\n{auth_url}\n")
    webbrowser.open(auth_url)

    print("After authorizing, you'll be redirected to a page showing your code.")
    raw = input("Paste the full redirect URL or just the code here: ").strip()
    if "code=" in raw:
        from urllib.parse import urlparse, parse_qs
        parsed = parse_qs(urlparse(raw).query)
        code = parsed["code"][0]
    else:
        code = raw

    print("Exchanging code for tokens...")
    token_data = exchange_code(code)
    save_tokens(token_data)
    print("Done! You can now use tiktok_upload.py")


if __name__ == "__main__":
    run_auth_flow()
