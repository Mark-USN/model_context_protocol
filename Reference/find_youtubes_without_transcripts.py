#!/usr/bin/env python3
"""
find_youtubes_without_transcripts.py (v2)

More robust: explicitly uses "ytsearchN:QUERY" (or ytsearchdateN:QUERY)
instead of relying on default_search. Adds better diagnostics.

Usage examples (PowerShell with uv):
  uv run python find_youtubes_without_transcripts.py --show-drops
  uv run python find_youtubes_without_transcripts.py --max 300 --csv out.csv
  uv run python find_youtubes_without_transcripts.py --date-sort
  uv run python find_youtubes_without_transcripts.py --no-strict-english
"""

from __future__ import annotations
import argparse
import csv
import re
import time
from typing import Dict, List, Optional

try:
    from yt_dlp import YoutubeDL
except Exception as e:
    raise SystemExit(
        "yt-dlp is required. Install with:\n"
        "  uv add yt-dlp\n"
        "or\n"
        "  uv pip install yt-dlp\n\n"
        f"Import error: {e}"
    )

# ------------------------- Defaults -------------------------

DEFAULT_QUERIES: List[str] = [
    # Python
    "python lecture", "python course", "python tutorial",
    "python data structures lecture", "python oop lecture", "python programming",
    # Math
    "math lecture", "calculus lecture", "linear algebra lecture",
    "discrete math lecture", "real analysis lecture", "probability lecture",
    "statistics lecture", "numerical methods lecture",
]

DEFAULT_MIN_SECONDS = 30*60          # 30 minutes
DEFAULT_MAX_RESULTS_PER_QUERY = 120 # 50..200 reasonable
DEFAULT_SEARCH_SORT_BY_DATE = False # False => relevance, True => newest
DEFAULT_STRICT_ENGLISH = True       # heuristic; set False to loosen

# ------------------------- Heuristics -----------------------

def looks_english(txt: str) -> bool:
    """ Heuristic to check if text looks like English.
        Args:
            txt: Input text.
        Returns:
            Returns True if text appears to be English.
    """
    if not txt:
        return False
    ascii_ratio = sum(1 for c in txt if ord(c) < 128) / max(1, len(txt))
    if ascii_ratio < 0.88:
        return False
    return bool(re.search(
        # Common English words in educational videos
        # \b = word boundary
        r"\b(the|and|for|with|from|to|in|on|is|are|lecture|course|tutorial|"
        r"introduction|beginner|advanced|chapter|series|lesson|class|university)\b",
        txt, re.I
    ))

def is_english(info: Dict, strict_english: bool) -> bool:
    if not strict_english:
        return True
    title = info.get("title") or ""
    desc  = info.get("description") or ""
    return looks_english(f"{title}\n{desc}")

# ---------------------- Caption checks ----------------------

def _dict_has_nonempty_lists(d: Optional[Dict]) -> bool:
    """ Check if a dict has any non-empty list values.
        Args:
            d: Input dict.
        Returns:
            Returns True if any value is a non-empty list.
    """
    if not isinstance(d, dict) or not d:
        return False
    for v in d.values():
        if isinstance(v, list) and any(v):
            return True
    return False

def has_any_captions(info: Dict) -> bool:
    """ Check if video info has any subtitles or automatic captions.
        Args:
            info: Video info dict from yt-dlp.
        Returns:
            Returns True if any captions/subtitles exist.
    """
    subs  = info.get("subtitles") or {}
    autos = info.get("automatic_captions") or {}
    return _dict_has_nonempty_lists(subs) or _dict_has_nonempty_lists(autos)

# ---------------------- yt-dlp helpers ----------------------

def expand_info(video_url: str) -> Optional[Dict]:
    """ Expand video info using yt-dlp.
        Args:
            video_url: YouTube video URL.
        Returns:
            Returns the info dict, or None on failure.
    """
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        # "extractor_args": {"youtube": {"player_client": ["android"]}},
    }
    with YoutubeDL(ydl_opts) as ydl:
        try:
            return ydl.extract_info(video_url, download=False)
        except Exception:
            return None

def search_query(q: str, max_results_per_query: int, date_sort: bool, verbose: bool=False) -> List[str]:
    """
    Explicitly use ytsearchN:QUERY or ytsearchdateN:QUERY.
        Args:
            q: Search query string.
            max_results_per_query: Max number of search results to retrieve.
            date_sort: If True, sort by newest-first.
            verbose: If True, print diagnostics.
        Returns:
            Returns a list of video URLs.
    """
    mode = "ytsearchdate" if date_sort else "ytsearch"
    query_expr = f"{mode}{max_results_per_query}:{q}"
    ydl_opts = {
        "verbose": True if verbose else False       # Print additional info to stdout.
        "quiet": False if verbose else True         # Do not print messages to stdout.
        "no_warnings": True if verbose else False   # Do not print out anything for warnings.
        "skip_download": True,
        "extract_flat": True,
    }
    entries: List[Dict] = []
    with YoutubeDL(ydl_opts) as ydl:
        try:
            res = ydl.extract_info(query_expr, download=False)
            entries = (res or {}).get("entries") or []
        except Exception as e:
            if verbose:
                print(f"search_query error for {q!r}: {e}")
            return []

    urls: List[str] = []
    for e in entries:
        u = e.get("url")
        if not u:
            continue
        if "youtube.com" in u or "youtu.be" in u:
            urls.append(u)
        else:
            urls.append(f"https://www.youtube.com/watch?v={u}")
    if verbose:
        print(f"  Found {len(urls)} results for {q!r}")
    return urls

# --------------------------- Main ---------------------------

def run_search(queries: List[str],
               min_seconds: int,
               max_results_per_query: int,
               date_sort: bool,
               strict_english: bool,
               out_csv: Optional[str],
               show_drops: bool,
               verbose_search: bool) -> int:
    """ Run the search and filtering process.
        Args:
            queries: List of search query strings.
            min_seconds: Minimum video duration in seconds.
            max_results_per_query: Max number of search results to retrieve per query.
            date_sort: If True, sort search results by newest-first.
            strict_english: If True, apply English heuristic filtering.
            out_csv: If provided, path to output CSV file.
            show_drops: If True, print reasons for dropping non-matching videos.
            verbose_search: If True, print verbose search diagnostics.
        Returns:            
            Returns the number of matching videos found.
    """
    seen_urls = set()
    hits: List[Dict] = []
    total_checked = 0

    for q in queries:
        print(f"Searching: {q}", flush=True)
        urls = search_query(q, max_results_per_query, date_sort, verbose=verbose_search or show_drops)
        if (verbose_search or show_drops) and not urls:
            print(f"  No search results for {q!r}")
        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            info = expand_info(url)
            if not info:
                if verbose_search or show_drops:
                    print(f"  WARN: expand_info failed for {url}")
                continue

            total_checked += 1
            dur = info.get("duration") or 0

            reason = None
            if dur < min_seconds:
                reason = f"short ({dur}s)"
            elif has_any_captions(info):
                reason = "has captions"
            elif not is_english(info, strict_english):
                reason = "not english"

            if reason:
                if show_drops:
                    title = (info.get("title") or "").strip()
                    print(f"DROP: {title!r} -> {reason}")
                continue

            hits.append({
                "title": info.get("title") or "",
                "url": info.get("webpage_url") or url,
                "duration_min": round(dur/60, 1),
                "uploader": info.get("uploader") or "",
                "upload_date": info.get("upload_date") or "",
            })

            if total_checked % 25 == 0:
                time.sleep(0.5)

    uniq: List[Dict] = []
    seen_titles = set()
    for h in hits:
        t = h["title"].strip().lower()
        if t and t not in seen_titles:
            seen_titles.add(t)
            uniq.append(h)

    if not uniq:
        print("\nNo matches found with current settings.")
        print("Tips:")
        print("  • Use specific queries (e.g., 'python lecture', 'calculus lecture')")
        print("  • Try relevance search (default) instead of newest-first")
        print("  • Set --no-strict-english to loosen language filtering")
        print("  • Increase --max to scan more results per query")
        print("  • Add --verbose-search to see search counts and failures")
        return 0

    print(f"\n=== Candidates (≥{int(round(float(min_seconds) / 60.0))} min, no captions/transcripts) ===")
    for h in uniq:
        d = h["upload_date"]
        pretty = f"{d[0:4]}-{d[4:6]}-{d[6:8]}" if d and len(d) == 8 else "—"
        print(f"- {h['title']}  ({h['duration_min']} min)")
        print(f"  {h['url']}")
        print(f"  by {h['uploader'] or '—'} on {pretty}")

    if out_csv:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["title","url","duration_min","uploader","upload_date"])
            w.writeheader()
            w.writerows(uniq)
        print(f"\nSaved CSV: {out_csv}  (rows: {len(uniq)})")

    return len(uniq)

def parse_args() -> argparse.Namespace:
    """ Parse command-line arguments. """
    p = argparse.ArgumentParser(description="Find YouTube videos ≥30 min with no captions/transcripts (via yt-dlp).")
    p.add_argument("--query", "-q", action="append", help="Add a search query (can repeat). If omitted, uses Python/Math presets.")
    p.add_argument("--max", type=int, default=DEFAULT_MAX_RESULTS_PER_QUERY, help=f"Max results per query (default: {DEFAULT_MAX_RESULTS_PER_QUERY})")
    p.add_argument("--min-mins", type=float, default=DEFAULT_MIN_SECONDS/60.0, help=f"Minimum duration in minutes (default: {DEFAULT_MIN_SECONDS/60:.0f})")
    p.add_argument("--date-sort", action="store_true", help="Sort by newest-first (ytsearchdate) instead of relevance (ytsearch).")
    p.add_argument("--no-strict-english", action="store_true", help="Disable English heuristic (accept all).")
    p.add_argument("--csv", metavar="FILE", help="Write results to CSV.")
    p.add_argument("--show-drops", action="store_true", help="Explain why non-matching videos were dropped.")
    p.add_argument("--verbose-search", action="store_true", help="Print search result counts and expand_info failures.")
    return p.parse_args()

def main() -> None:
    """ Main entry point. """
    args = parse_args()

    queries = args.query if args.query else list(DEFAULT_QUERIES)
    min_seconds = int(round(float(args.min_mins) * 60))
    max_results_per_query = max(1, int(args.max))
    date_sort = bool(args.date_sort)
    strict_english = not bool(args.no_strict_english)
    out_csv = args.csv
    show_drops = bool(args.show_drops)
    verbose_search = bool(args.verbose_search)

    run_search(
        queries=queries,
        min_seconds=min_seconds,
        max_results_per_query=max_results_per_query,
        date_sort=date_sort,
        strict_english=strict_english,
        out_csv=out_csv,
        show_drops=show_drops,
        verbose_search=verbose_search,
    )

if __name__ == "__main__":
    main()
