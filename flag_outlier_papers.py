"""
Flag papers in openalex_works.json that might not actually belong to
Michael J. MacCoss: papers whose research area (OpenAlex topic field) is
unlike the bulk of his work, and papers that share no co-authors with any
other paper in the dataset.

Usage:
    python flag_outlier_papers.py
"""

import json
from collections import Counter

SOURCE_FILE = "openalex_works.json"
MACCOSS_ID = "https://openalex.org/A5043959168"


def coauthor_ids(work):
    ids = set()
    for a in work.get("authorships") or []:
        author = a.get("author") or {}
        aid = author.get("id")
        if aid and aid != MACCOSS_ID:
            ids.add(aid)
    return ids


def coauthor_names(work):
    names = []
    for a in work.get("authorships") or []:
        author = a.get("author") or {}
        aid = author.get("id")
        name = author.get("display_name")
        if aid and aid != MACCOSS_ID and name:
            names.append(name)
    return names


def field_of(work):
    pt = work.get("primary_topic") or {}
    field = pt.get("field") or {}
    return field.get("display_name")


def main():
    with open(SOURCE_FILE, encoding="utf-8") as f:
        works = json.load(f)

    # --- co-author overlap analysis ---
    id_to_papers = {}
    for w in works:
        for aid in coauthor_ids(w):
            id_to_papers.setdefault(aid, []).append(w)

    no_shared_coauthors = []
    for w in works:
        ids = coauthor_ids(w)
        if not ids:
            # solo paper (no co-authors besides MacCoss) - can't check overlap
            continue
        shared = False
        for aid in ids:
            if len(id_to_papers.get(aid, [])) > 1:
                shared = True
                break
        if not shared:
            no_shared_coauthors.append(w)

    # --- research field analysis ---
    field_counts = Counter(field_of(w) for w in works if field_of(w))
    total = sum(field_counts.values())
    common_fields = {f for f, c in field_counts.items() if c / total >= 0.02}  # >=2% of corpus
    rare_field = [w for w in works if field_of(w) and field_of(w) not in common_fields]

    print("=== Field distribution ===")
    for f, c in field_counts.most_common():
        flag = "" if f in common_fields else "  <-- rare"
        print(f"  {c:4d}  {f}{flag}")

    print(f"\n=== Papers with NO shared co-authors with any other paper ({len(no_shared_coauthors)}) ===")
    for w in sorted(no_shared_coauthors, key=lambda w: w.get("publication_year") or 0):
        print(f"  [{w.get('publication_year')}] {w.get('display_name')}")
        print(f"       journal: {(((w.get('primary_location') or {}).get('source') or {}).get('display_name'))}")
        print(f"       field:   {field_of(w)}")
        print(f"       authors: {', '.join(coauthor_names(w))}")
        print(f"       doi:     {w.get('doi')}")
        print()

    print(f"\n=== Papers in a RARE research field ({len(rare_field)}) ===")
    for w in sorted(rare_field, key=lambda w: w.get("publication_year") or 0):
        print(f"  [{w.get('publication_year')}] {w.get('display_name')}")
        print(f"       journal: {(((w.get('primary_location') or {}).get('source') or {}).get('display_name'))}")
        print(f"       field:   {field_of(w)}")
        print(f"       authors: {', '.join(coauthor_names(w))}")
        print(f"       doi:     {w.get('doi')}")
        print()

    both = [w for w in no_shared_coauthors if w in rare_field]
    print(f"\n=== Papers flagged on BOTH counts ({len(both)}) ===")
    for w in both:
        print(f"  [{w.get('publication_year')}] {w.get('display_name')}")


if __name__ == "__main__":
    main()
