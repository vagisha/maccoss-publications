"""
Fetch all works for an author from OpenAlex, paging through with cursor
pagination, and save the results to a JSON file.

Usage:
    python fetch_openalex_works.py
"""

import json
import time
import urllib.request
import urllib.error

ORCID = "0000-0003-1853-0256"
MAILTO = "vagisha@gmail.com"  # polite pool for faster/more reliable OpenAlex access
OUTPUT_FILE = "openalex_works.json"

BASE_URL = "https://api.openalex.org/works"


def fetch_all_works(orcid, mailto):
    works = []
    cursor = "*"
    page = 1

    while cursor:
        params = (
            f"filter=author.orcid:https://orcid.org/{orcid}"
            f"&per_page=200"
            f"&cursor={cursor}"
            f"&mailto={mailto}"
        )
        url = f"{BASE_URL}?{params}"

        req = urllib.request.Request(url, headers={"User-Agent": f"mailto:{mailto}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"HTTP error on page {page}: {e.code} {e.reason}")
            raise

        results = data.get("results", [])
        works.extend(results)
        print(f"Page {page}: fetched {len(results)} works (total so far: {len(works)})")

        cursor = data.get("meta", {}).get("next_cursor")
        page += 1
        time.sleep(0.1)  # be polite to the API

    return works


def main():
    print(f"Fetching all works for ORCID {ORCID}...")
    works = fetch_all_works(ORCID, MAILTO)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(works, f, indent=2)

    total_citations = sum(w.get("cited_by_count", 0) for w in works)

    print()
    print(f"Saved {len(works)} works to {OUTPUT_FILE}")
    print(f"Total papers: {len(works)}")
    print(f"Total citations: {total_citations}")


if __name__ == "__main__":
    main()
