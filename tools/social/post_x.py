#!/usr/bin/env python3
"""
post_x.py — Post to X (Twitter) via API v2 using Tweepy.

Usage:
    python post_x.py "Your tweet text here"
    python post_x.py --thread "Tweet 1" "Tweet 2" "Tweet 3"
    python post_x.py --file tweet.txt
    echo "Some text" | python post_x.py

Credentials:
    Set these environment variables (or add to .env):
        X_API_KEY
        X_API_SECRET
        X_ACCESS_TOKEN
        X_ACCESS_TOKEN_SECRET

    Get credentials at: https://developer.x.com/en/portal/dashboard
    App permissions must have "Read and Write" enabled.
"""

import os
import sys
import argparse
import time
from pathlib import Path

try:
    import tweepy
except ImportError:
    print("ERROR: tweepy not installed. Run: pip install tweepy python-dotenv")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass  # python-dotenv optional — can set env vars directly


def get_client() -> tweepy.Client:
    """Build authenticated Tweepy client from environment variables."""
    required = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Set them in .env or export them before running.")
        sys.exit(1)

    return tweepy.Client(
        consumer_key=os.getenv("X_API_KEY"),
        consumer_secret=os.getenv("X_API_SECRET"),
        access_token=os.getenv("X_ACCESS_TOKEN"),
        access_token_secret=os.getenv("X_ACCESS_TOKEN_SECRET"),
    )


def post_tweet(client: tweepy.Client, text: str, reply_to_id: str = None) -> dict:
    """Post a single tweet. Optionally reply to a tweet ID for threading."""
    kwargs = {"text": text}
    if reply_to_id:
        kwargs["reply"] = {"in_reply_to_tweet_id": reply_to_id}

    response = client.create_tweet(**kwargs)
    tweet_id = response.data["id"]
    return {"id": tweet_id, "url": f"https://x.com/i/web/status/{tweet_id}"}


def post_thread(client: tweepy.Client, tweets: list[str], delay: float = 1.5) -> list[dict]:
    """
    Post a list of strings as a reply thread.
    Returns list of {id, url} dicts for each tweet.
    """
    results = []
    reply_to_id = None

    for i, text in enumerate(tweets):
        result = post_tweet(client, text, reply_to_id=reply_to_id)
        results.append(result)
        reply_to_id = result["id"]
        print(f"  [{i+1}/{len(tweets)}] Posted: {result['url']}")
        if i < len(tweets) - 1:
            time.sleep(delay)  # avoid rate limit between thread tweets

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Post to X via API v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("text", nargs="*", help="Tweet text (or first tweet if --thread)")
    parser.add_argument("--thread", action="store_true", help="Post multiple args as a thread")
    parser.add_argument("--file", type=Path, help="Read tweet text from file")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between thread tweets (default: 1.5)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be posted without posting")

    args = parser.parse_args()

    # Collect tweet content
    if args.file:
        content = args.file.read_text().strip()
        tweets = [content]
    elif not sys.stdin.isatty() and not args.text:
        content = sys.stdin.read().strip()
        tweets = [content]
    elif args.text:
        tweets = args.text
    else:
        parser.print_help()
        sys.exit(1)

    # Validate lengths
    for i, tweet in enumerate(tweets):
        if len(tweet) > 280:
            print(f"WARNING: Tweet {i+1} is {len(tweet)} chars (max 280). It will be truncated by X.")

    # Dry run
    if args.dry_run:
        print("=== DRY RUN ===")
        for i, tweet in enumerate(tweets):
            print(f"\n[{i+1}] ({len(tweet)} chars):\n{tweet}")
        return

    client = get_client()

    if args.thread and len(tweets) > 1:
        print(f"Posting thread of {len(tweets)} tweets...")
        results = post_thread(client, tweets, delay=args.delay)
        print(f"\nThread posted. First tweet: {results[0]['url']}")
    else:
        if len(tweets) > 1 and not args.thread:
            print("NOTE: Multiple texts provided without --thread. Posting first only.")
        result = post_tweet(client, tweets[0])
        print(f"Posted: {result['url']}")


if __name__ == "__main__":
    main()
