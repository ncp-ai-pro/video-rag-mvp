#!/usr/bin/env python3
"""Create a synthetic KakaoTalk export containing YouTube URLs for import tests.

The generated identifiers are synthetic; the file is for parser/queue load tests
and must not be used to trigger real YouTube analysis.
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path


ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def video_id(number: int) -> str:
    """Return a deterministic, YouTube-shaped 11-character synthetic ID."""
    chars: list[str] = []
    value = number
    for _ in range(11):
        chars.append(ALPHABET[value % len(ALPHABET)])
        value //= len(ALPHABET)
    return "".join(chars)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/kakao-youtube-load.txt"))
    parser.add_argument("--links", type=int, default=5000, help="total YouTube URL lines (default: 5000)")
    parser.add_argument(
        "--duplicate-rate",
        type=float,
        default=0.20,
        help="fraction of URL lines that repeat an earlier URL, 0.0 to <1.0 (default: 0.20)",
    )
    parser.add_argument("--seed", type=int, default=20260813, help="random seed for reproducible output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.links < 1:
        raise SystemExit("--links must be at least 1")
    if not 0 <= args.duplicate_rate < 1:
        raise SystemExit("--duplicate-rate must be in the range 0.0 <= rate < 1.0")

    duplicate_count = min(args.links - 1, round(args.links * args.duplicate_rate))
    unique_count = args.links - duplicate_count
    rng = random.Random(args.seed)
    urls = [f"https://www.youtube.com/watch?v={video_id(index)}" for index in range(unique_count)]
    links = urls + [rng.choice(urls) for _ in range(duplicate_count)]
    rng.shuffle(links)

    start = datetime(2026, 8, 13, 9, 0)
    lines = ["KakaoTalk Chat Export", "Synthetic fixture — do not submit with analyze=true outside a test environment.", ""]
    for index, url in enumerate(links):
        timestamp = start + timedelta(seconds=index * 3)
        sender = "테스트 사용자" if index % 2 == 0 else "부하테스트 봇"
        lines.append(f"{timestamp:%Y. %m. %d. %p %I:%M}, {sender} : 공유 영상 #{index + 1}")
        lines.append(url)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote={args.output}")
    print(f"total_urls={args.links} unique_urls={unique_count} duplicate_url_lines={duplicate_count} seed={args.seed}")


if __name__ == "__main__":
    main()
