"""
Build index.html from openalex_works.json.

Reads the raw OpenAlex works dump, reduces each work to the fields the
page needs, and embeds that data directly into a self-contained
index.html (no runtime fetch() needed, so it works when opened via
file:// in any browser).

Usage:
    python build_page.py
"""

import json
import math
import random
import re
from collections import Counter, defaultdict

SOURCE_FILE = "openalex_works.json"
OUTPUT_FILE = "index.html"
MACCOSS_ID = "https://openalex.org/A5043959168"

# Preprints (bioRxiv, arXiv, etc.) are excluded from the whole page: they
# inflate the per-year counts and are usually preprint versions of papers
# already counted from their published journal.
PREPRINT_SOURCE = re.compile(
    r"biorxiv|medrxiv|arxiv|chemrxiv|research square|ssrn|authorea|preprints", re.I)


def is_preprint(w):
    if (w.get("type") or "").lower() == "preprint":
        return True
    src = (w.get("primary_location") or {}).get("source") or {}
    return bool(PREPRINT_SOURCE.search(src.get("display_name") or ""))

# ---- constellation (top-N papers grouped into co-author communities) ----
CONSTELLATION_TOP_N = 50
# Edge threshold on the hub-down-weighted shared-co-author score. Two papers
# are linked when they share co-authors whose summed 1/(papers-they-appear-on)
# weight clears this bar, so ubiquitous "hub" authors (who are on many papers)
# contribute little and specialist collaborators drive the grouping.
CONSTELLATION_EDGE_THRESHOLD = 0.5
CONSTELLATION_MAX_NAMED = 6  # colour+label this many communities; rest are "Other"
# Distinct star colours for the named communities (bright on a dark sky).
CONSTELLATION_COLORS = [
    "#8ab4f8", "#5eead4", "#fcd34d", "#c4b5fd", "#fda4af", "#86efac",
]
CONSTELLATION_OTHER_COLOR = "#8b93a7"


def _coauthor_ids(w):
    ids = set()
    for a in w.get("authorships") or []:
        au = a.get("author") or {}
        aid = au.get("id")
        if aid and aid != MACCOSS_ID:
            ids.add(aid)
    return ids


def _topic_of(w):
    return (w.get("primary_topic") or {}).get("display_name") or "Uncategorized"


def _shorten(label, n=30):
    return label if len(label) <= n else label[: n - 1].rstrip() + "…"


def _force_layout(n, edges, weight=None, iters=420, seed=42):
    """Small deterministic Fruchterman-Reingold layout with gravity, returning
    positions normalised into [0, 1]. Disconnected papers drift to the edges;
    densely linked communities clump together. `weight` (0..1 per node, e.g.
    scaled citations) boosts repulsion so the biggest stars spread apart and
    stay individually visible instead of merging into a blob."""
    rng = random.Random(seed)
    pos = [[rng.uniform(0, 1), rng.uniform(0, 1)] for _ in range(n)]
    if n <= 1:
        return [[0.5, 0.5]] * n
    if weight is None:
        weight = [0.0] * n
    k = 1.5 / math.sqrt(n)
    temp = 0.12
    for _ in range(iters):
        disp = [[0.0, 0.0] for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                dx = pos[i][0] - pos[j][0]
                dy = pos[i][1] - pos[j][1]
                d = math.sqrt(dx * dx + dy * dy) + 1e-6
                f = (k * k) / d * (1 + 1.8 * (weight[i] + weight[j]))
                ux, uy = dx / d, dy / d
                disp[i][0] += ux * f
                disp[i][1] += uy * f
                disp[j][0] -= ux * f
                disp[j][1] -= uy * f
        for a, b in edges:
            dx = pos[a][0] - pos[b][0]
            dy = pos[a][1] - pos[b][1]
            d = math.sqrt(dx * dx + dy * dy) + 1e-6
            f = (d * d) / k
            ux, uy = dx / d, dy / d
            disp[a][0] -= ux * f
            disp[a][1] -= uy * f
            disp[b][0] += ux * f
            disp[b][1] += uy * f
        for i in range(n):
            disp[i][0] += (0.5 - pos[i][0]) * 0.06
            disp[i][1] += (0.5 - pos[i][1]) * 0.06
        for i in range(n):
            dx, dy = disp[i]
            dl = math.sqrt(dx * dx + dy * dy) + 1e-9
            step = min(dl, temp)
            pos[i][0] += dx / dl * step
            pos[i][1] += dy / dl * step
        temp = max(0.008, temp * 0.985)

    xs = [p[0] for p in pos]
    ys = [p[1] for p in pos]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    pad = 0.07
    for p in pos:
        p[0] = pad + (1 - 2 * pad) * (p[0] - minx) / (maxx - minx + 1e-9)
        p[1] = pad + (1 - 2 * pad) * (p[1] - miny) / (maxy - miny + 1e-9)
    return pos


def compute_constellation(raw_works):
    """Top-N cited papers as stars, grouped into co-author communities and
    labelled by the OpenAlex topic carrying the most citation weight."""
    top = sorted(raw_works, key=lambda w: w.get("cited_by_count", 0), reverse=True)
    top = top[:CONSTELLATION_TOP_N]
    n = len(top)
    ca = [_coauthor_ids(w) for w in top]

    author_count = Counter()
    for s in ca:
        for a in s:
            author_count[a] += 1

    # Hub-down-weighted shared-co-author graph -> union-find components.
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            shared = ca[i] & ca[j]
            if not shared:
                continue
            score = sum(1.0 / author_count[a] for a in shared)
            if score >= CONSTELLATION_EDGE_THRESHOLD:
                edges.append((i, j))
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)

    members = defaultdict(list)
    for i in range(n):
        members[find(i)].append(i)

    # Rank communities by size, then total citations; name the top few.
    def comm_cites(idxs):
        return sum(top[i].get("cited_by_count", 0) for i in idxs)

    ranked = sorted(members.values(), key=lambda idxs: (len(idxs), comm_cites(idxs)), reverse=True)
    named = [c for c in ranked if len(c) >= 2][:CONSTELLATION_MAX_NAMED]

    comm_id = [-1] * n          # -1 == "Other"
    comm_color = [CONSTELLATION_OTHER_COLOR] * n
    legend = []
    for ci, idxs in enumerate(named):
        color = CONSTELLATION_COLORS[ci % len(CONSTELLATION_COLORS)]
        weight = Counter()
        for i in idxs:
            weight[_topic_of(top[i])] += top[i].get("cited_by_count", 0)
        label = weight.most_common(1)[0][0]
        brightest = max(idxs, key=lambda i: top[i].get("cited_by_count", 0))
        for i in idxs:
            comm_id[i] = ci
            comm_color[i] = color
        legend.append({"label": label, "short": _shorten(label, 42), "color": color,
                       "anchor": brightest})

    max_c = max((top[i].get("cited_by_count", 0) for i in range(n)), default=1) or 1
    weight = [math.sqrt(top[i].get("cited_by_count", 0) / max_c) for i in range(n)]
    pos = _force_layout(n, edges, weight=weight, seed=42)

    nodes = []
    for i, w in enumerate(top):
        nodes.append({
            "title": w.get("display_name") or w.get("title"),
            "year": w.get("publication_year"),
            "citations": w.get("cited_by_count", 0),
            "doi": w.get("doi"),
            "topic": _topic_of(w),
            "comm": comm_id[i],
            "color": comm_color[i],
            "x": round(pos[i][0], 4),
            "y": round(pos[i][1], 4),
            "isAnchor": any(lg["anchor"] == i for lg in legend),
        })
    for lg in legend:
        lg.pop("anchor", None)

    return {"nodes": nodes, "edges": edges, "legend": legend}


def reduce_work(w):
    authorships = w.get("authorships") or []
    authors = []
    coauthors = []
    for a in authorships:
        author = a.get("author") or {}
        name = author.get("display_name") or a.get("raw_author_name")
        if name:
            authors.append(name)
        aid = author.get("id")
        if aid and aid != MACCOSS_ID and name:
            coauthors.append({"id": aid, "name": name})

    primary_location = w.get("primary_location") or {}
    source = primary_location.get("source") or {}
    journal = source.get("display_name")

    counts_by_year = [
        {"year": c.get("year"), "citations": c.get("cited_by_count", 0)}
        for c in (w.get("counts_by_year") or [])
    ]

    return {
        "title": w.get("display_name") or w.get("title"),
        "year": w.get("publication_year"),
        "citations": w.get("cited_by_count", 0),
        "journal": journal,
        "authors": authors,
        "coauthors": coauthors,
        "doi": w.get("doi"),
        "type": w.get("type"),
        "countsByYear": counts_by_year,
    }


def build():
    with open(SOURCE_FILE, encoding="utf-8") as f:
        raw_works = json.load(f)

    n_before = len(raw_works)
    raw_works = [w for w in raw_works if not is_preprint(w)]
    n_preprints = n_before - len(raw_works)

    works = [reduce_work(w) for w in raw_works]
    works = [w for w in works if w["year"] is not None]

    data_json = json.dumps(works, ensure_ascii=False)
    constellation_json = json.dumps(compute_constellation(raw_works), ensure_ascii=False)

    html = (HTML_TEMPLATE
            .replace("__WORKS_DATA__", data_json)
            .replace("__CONSTELLATION_DATA__", constellation_json))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Wrote {OUTPUT_FILE} with {len(works)} works embedded "
          f"(excluded {n_preprints} preprints).")
    print(f"Total citations: {sum(w['citations'] for w in works)}")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" data-theme="classic">
<head>
<meta charset="UTF-8">
<title>Michael J. MacCoss</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
  :root {
    /* Surface + text defaults (light themes inherit these; dark themes override). */
    --bg: #f4f5f7;
    --card: #ffffff;
    --text: #1e1e24;
    --text-dim: #555555;
    --text-muted: #888888;
    --border: #ececec;
    --border-strong: #cccccc;
    --shadow: rgba(0,0,0,0.08);
  }
  /* Each theme sets three accent colours: --accent (primary: headings, links,
     tile borders, publications bars, word cloud), --accent-2 (secondary:
     citations-per-year bars) and --accent-3 (tertiary: cumulative line).
     --accent-soft is a faint tint for the table header and type badges. */
  :root[data-theme="classic"] {
    --accent: #1e3a70; --accent-2: #6f97d6; --accent-3: #d97757; --accent-soft: #e9edf2;
  }
  :root[data-theme="charcoal"] {
    --accent: #374151; --accent-2: #9aa5b1; --accent-3: #10b981; --accent-soft: #eceef1;
  }
  :root[data-theme="indigo"] {
    --accent: #4f46e5; --accent-2: #a5b4fc; --accent-3: #f472b6; --accent-soft: #eae9fb;
  }
  :root[data-theme="emerald"] {
    --accent: #047857; --accent-2: #6ee7b7; --accent-3: #0ea5e9; --accent-soft: #e2f3ec;
  }
  :root[data-theme="midnight"] {
    --accent: #8ab4f8; --accent-2: #38bdf8; --accent-3: #f472b6; --accent-soft: #1e2a44;
    --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --text-dim: #b6c4d8; --text-muted: #8ea2bd;
    --border: rgba(255,255,255,0.09); --border-strong: rgba(255,255,255,0.20); --shadow: rgba(0,0,0,0.35);
  }
  :root[data-theme="carbon"] {
    --accent: #a78bfa; --accent-2: #c4b5fd; --accent-3: #34d399; --accent-soft: #2a2540;
    --bg: #18181b; --card: #26262b; --text: #ededed; --text-dim: #c2c2c8; --text-muted: #9a9aa2;
    --border: rgba(255,255,255,0.09); --border-strong: rgba(255,255,255,0.20); --shadow: rgba(0,0,0,0.40);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 32px 48px 64px;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  .page {
    max-width: 1180px;
    margin: 0 auto;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 24px;
  }
  header h1 {
    margin: 0 0 4px;
    font-size: 30px;
    color: var(--accent);
  }
  header .affiliation {
    color: var(--text-dim);
    font-size: 14px;
    margin-bottom: 8px;
  }
  header .links a {
    color: var(--accent);
    text-decoration: none;
    font-size: 13px;
    margin-right: 16px;
    border-bottom: 1px solid transparent;
  }
  header .links a:hover { border-bottom-color: var(--accent); }
  .theme-picker {
    font-size: 13px;
    color: var(--text-dim);
  }
  .theme-picker select {
    margin-left: 6px;
    padding: 4px 8px;
    border-radius: 6px;
    border: 1px solid var(--border-strong);
    background: var(--card);
    color: var(--text);
  }
  .card {
    background: var(--card);
    border-radius: 12px;
    box-shadow: 0 1px 3px var(--shadow), 0 1px 2px var(--shadow);
    padding: 20px 24px;
    margin-bottom: 24px;
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-bottom: 24px;
  }
  .tile {
    background: var(--card);
    border-radius: 12px;
    box-shadow: 0 1px 3px var(--shadow), 0 1px 2px var(--shadow);
    padding: 18px 20px;
    border-top: 3px solid var(--accent);
  }
  .tile .label {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 6px;
  }
  .tile .value {
    font-size: 26px;
    font-weight: 600;
    color: var(--text);
  }
  .charts {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-bottom: 24px;
  }
  .chart-wrap {
    position: relative;
    width: 100%;
  }
  .constellation-wrap {
    position: relative;
    width: 100%;
    background: #0a0f1e;
    border-radius: 8px;
    overflow: hidden;
  }
  .constellation-wrap svg { display: block; width: 100%; height: 100%; }
  .constellation-wrap .star { cursor: pointer; }
  .constellation-wrap text { font-family: -apple-system, "Segoe UI", sans-serif; }
  .collab-cloud {
    display: flex;
    flex-wrap: wrap;
    align-content: space-evenly;
    justify-content: center;
    gap: 10px 20px;
    overflow: hidden;
  }
  .collab-cloud .collab-item {
    display: inline-flex;
    align-items: baseline;
    gap: 3px;
    line-height: 1;
  }
  .collab-cloud .collab-name { font-weight: 600; }
  .collab-cloud .collab-count { color: var(--text-muted); }
  .card h2 {
    margin-top: 0;
    font-size: 16px;
    color: var(--text);
  }
  .caption {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 8px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  th, td {
    text-align: left;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  th {
    background: var(--accent-soft);
    color: var(--text);
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }
  th .sort-arrow { font-size: 10px; opacity: 0.6; }
  th.title-col { width: 32%; }
  th.authors-col { width: 18%; }
  th.journal-col { width: 16%; }
  td a { color: var(--accent); text-decoration: none; }
  td a:hover { text-decoration: underline; }
  .filter-row input {
    width: 100%;
    padding: 4px 6px;
    font-size: 12px;
    border: 1px solid var(--border-strong);
    border-radius: 4px;
    background: var(--card);
    color: var(--text);
  }
  .authors-more {
    color: var(--accent);
    cursor: pointer;
    font-size: 12px;
  }
  .pagination {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 14px;
    font-size: 13px;
  }
  .pagination button {
    padding: 5px 12px;
    border-radius: 6px;
    border: 1px solid var(--border-strong);
    background: var(--card);
    color: var(--text);
    cursor: pointer;
  }
  .pagination button:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .type-badge {
    display: inline-block;
    padding: 1px 7px;
    border-radius: 10px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 11px;
  }
  .type-filter { position: relative; font-weight: 400; }
  .type-filter summary {
    list-style: none;
    cursor: pointer;
    padding: 4px 22px 4px 6px;
    font-size: 12px;
    border: 1px solid var(--border-strong);
    border-radius: 4px;
    background: var(--card);
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    position: relative;
  }
  .type-filter summary::-webkit-details-marker { display: none; }
  .type-filter summary::after {
    content: "▾";
    position: absolute;
    right: 7px;
    top: 4px;
    font-size: 10px;
    opacity: 0.6;
  }
  .type-menu {
    position: absolute;
    z-index: 20;
    top: 100%;
    left: 0;
    margin-top: 3px;
    min-width: 150px;
    max-height: 220px;
    overflow-y: auto;
    background: var(--card);
    border: 1px solid var(--border-strong);
    border-radius: 6px;
    box-shadow: 0 4px 12px var(--shadow);
    padding: 6px;
  }
  .type-menu label {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 4px;
    font-size: 12px;
    font-weight: 400;
    cursor: pointer;
    white-space: nowrap;
  }
  .type-menu label:hover { background: var(--accent-soft); border-radius: 4px; }
  .type-menu .type-actions {
    display: flex;
    gap: 8px;
    padding: 2px 4px 6px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 4px;
  }
  .type-menu .type-actions a {
    font-size: 11px;
    color: var(--accent);
    cursor: pointer;
    text-decoration: underline;
  }
</style>
</head>
<body>
<div class="page">

<header>
  <div>
    <h1>Michael J. MacCoss</h1>
    <div class="affiliation">University of Washington, Department of Genome Sciences</div>
    <div class="links">
      <a href="https://orcid.org/0000-0003-1853-0256" target="_blank" rel="noopener">ORCID</a>
      <a href="https://scholar.google.com/citations?user=icweOB0AAAAJ&hl=en" target="_blank" rel="noopener">Google Scholar</a>
      <a href="https://maccosslab.org/maccoss/" target="_blank" rel="noopener">Lab website</a>
    </div>
  </div>
  <div class="theme-picker">
    Theme:
    <select id="themeSelect">
      <option value="classic">Classic navy</option>
      <option value="charcoal">Charcoal</option>
      <option value="indigo">Indigo</option>
      <option value="emerald">Emerald</option>
      <option value="midnight">Midnight (dark)</option>
      <option value="carbon">Carbon (dark)</option>
    </select>
  </div>
</header>

<div class="tiles" id="tiles"></div>

<div class="charts">
  <div class="card">
    <h2>Publications per year</h2>
    <div class="chart-wrap" style="height:340px"><canvas id="pubsChart"></canvas></div>
  </div>
  <div class="card">
    <h2>Citations over time</h2>
    <div class="chart-wrap" style="height:340px"><canvas id="citesChart"></canvas></div>
    <div class="caption">
      OpenAlex only reports per-year citation counts for roughly the last
      ~10 years for each paper, not full history back to publication date.
      This chart is limited to the years OpenAlex actually provides data
      for, so its range is shorter than the publications-per-year chart.
    </div>
  </div>
  <div class="card">
    <h2>Top 20 collaborators</h2>
    <div id="collabCloud" class="collab-cloud" style="height:280px"></div>
    <div class="caption">Text size = number of shared papers; exact count shown after each name.</div>
  </div>
  <div class="card">
    <h2>Top journals</h2>
    <div id="journalCloud" class="collab-cloud" style="height:280px"></div>
    <div class="caption">Text size = number of papers published there; preprint servers excluded.</div>
  </div>
</div>

<div class="card">
  <h2>Top 50 papers, by research community</h2>
  <div id="constellation" class="constellation-wrap" style="height:360px"></div>
  <div class="caption">
    Each star is a paper (size = citations); papers sharing co-authors form
    constellations, coloured and named by their dominant OpenAlex topic.
    Hover for details, click to open.
  </div>
</div>

<div class="card">
  <h2>Citation growth of top 10 most-cited papers</h2>
  <div class="chart-wrap" style="height:320px"><canvas id="topPapersChart"></canvas></div>
  <div class="caption">
    Cumulative citations per year for each paper, using OpenAlex's ~10-year
    per-year citation window.
  </div>
</div>

<div class="card">
  <h2>Papers (<span id="rowCount"></span>)</h2>
  <table>
    <thead>
      <tr>
        <th class="title-col" data-col="title">Title <span class="sort-arrow"></span></th>
        <th data-col="year">Year <span class="sort-arrow"></span></th>
        <th data-col="citations">Citations <span class="sort-arrow"></span></th>
        <th class="journal-col" data-col="journal">Journal <span class="sort-arrow"></span></th>
        <th class="authors-col" data-col="authors">Authors <span class="sort-arrow"></span></th>
        <th data-col="type">Type <span class="sort-arrow"></span></th>
      </tr>
      <tr class="filter-row">
        <th><input data-filter="title" placeholder="filter title..."></th>
        <th><input data-filter="year" placeholder="e.g. 2010-2020"></th>
        <th><input data-filter="citations" placeholder="e.g. &gt;100"></th>
        <th><input data-filter="journal" placeholder="filter journal..."></th>
        <th><input data-filter="authors" placeholder="filter authors..."></th>
        <th>
          <details class="type-filter" id="typeFilter">
            <summary id="typeSummary">All types</summary>
            <div class="type-menu" id="typeMenu"></div>
          </details>
        </th>
      </tr>
    </thead>
    <tbody id="tableBody"></tbody>
  </table>
  <div class="pagination">
    <button id="prevPage">Prev</button>
    <span id="pageInfo"></span>
    <button id="nextPage">Next</button>
  </div>
</div>

</div>

<script>
const WORKS = __WORKS_DATA__;
const CONSTELLATION = __CONSTELLATION_DATA__;

// ---------- stat tiles ----------
function computeHIndex(citCounts) {
  const sorted = [...citCounts].sort((a, b) => b - a);
  let h = 0;
  for (let i = 0; i < sorted.length; i++) {
    if (sorted[i] >= i + 1) h = i + 1;
    else break;
  }
  return h;
}

function renderTiles() {
  const totalPapers = WORKS.length;
  const totalCitations = WORKS.reduce((s, w) => s + w.citations, 0);
  const hIndex = computeHIndex(WORKS.map(w => w.citations));

  const tiles = [
    { label: "Total papers", value: totalPapers },
    { label: "Total citations", value: totalCitations.toLocaleString() },
    { label: "h-index", value: hIndex },
  ];

  const container = document.getElementById("tiles");
  container.innerHTML = "";
  tiles.forEach(t => {
    const div = document.createElement("div");
    div.className = "tile";
    div.innerHTML = `<div class="label">${t.label}</div><div class="value">${t.value}</div>`;
    container.appendChild(div);
  });
}

function escapeHtml(s) {
  if (!s) return "";
  return s.replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// ---------- charts ----------
let pubsChart, citesChart, topPapersChart;

// Fixed 10-colour categorical palette for the top-10-papers lines. Chosen as
// mid-tone, saturated hues that stay legible on both the light and dark theme
// backgrounds (independent of the theme accent colours).
const LINE_PALETTE = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#14b8a6",
];

function getAccentColors() {
  const styles = getComputedStyle(document.documentElement);
  return {
    accent: styles.getPropertyValue("--accent").trim(),
    accent2: styles.getPropertyValue("--accent-2").trim(),
    accent3: styles.getPropertyValue("--accent-3").trim(),
    text: styles.getPropertyValue("--text").trim(),
    textMuted: styles.getPropertyValue("--text-muted").trim(),
    grid: styles.getPropertyValue("--border").trim(),
  };
}

function buildPubsPerYear() {
  const byYear = {};
  WORKS.forEach(w => { byYear[w.year] = (byYear[w.year] || 0) + 1; });
  const years = Object.keys(byYear).map(Number).sort((a, b) => a - b);
  return { years, counts: years.map(y => byYear[y]) };
}

function buildCitationsOverTime() {
  const byYear = {};
  WORKS.forEach(w => {
    (w.countsByYear || []).forEach(c => {
      byYear[c.year] = (byYear[c.year] || 0) + c.citations;
    });
  });
  const years = Object.keys(byYear).map(Number).sort((a, b) => a - b);
  let cumulative = 0;
  const cumulativeSeries = years.map(y => {
    cumulative += byYear[y];
    return cumulative;
  });
  return { years, perYear: years.map(y => byYear[y]), cumulativeSeries };
}

function buildTopCollaborators(limit) {
  const counts = {};
  WORKS.forEach(w => {
    (w.coauthors || []).forEach(c => {
      if (!counts[c.id]) counts[c.id] = { name: c.name, count: 0 };
      counts[c.id].count++;
      counts[c.id].name = c.name;
    });
  });
  return Object.values(counts)
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}

function lastNameOf(fullName) {
  return fullName.trim().split(/\s+/).pop();
}

// Preprint servers and data repositories reported by OpenAlex as "sources" —
// excluded from the top-journals cloud since they aren't journals.
const NON_JOURNAL = /biorxiv|medrxiv|arxiv|chemrxiv|figshare|zenodo|research square|ssrn|preprint|authorea|dryad|europe pmc/i;

function buildTopJournals(limit) {
  const counts = {};
  WORKS.forEach(w => {
    const j = w.journal;
    if (!j || NON_JOURNAL.test(j)) return;
    counts[j] = (counts[j] || 0) + 1;
  });
  return Object.entries(counts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}

// Generic word cloud: font size scales with count, exact count printed after
// each label, theme accent colour at graduated opacity so it re-themes.
// entries: [{ text, count, title }]; minF/maxF bound the label font size.
function renderWordCloud(hostId, entries, accent, minF, maxF) {
  const container = document.getElementById(hostId);
  container.innerHTML = "";
  if (!entries.length) return;
  const maxCount = Math.max(...entries.map(e => e.count));
  const minCount = Math.min(...entries.map(e => e.count));
  const span = maxCount - minCount || 1;

  entries.forEach(e => {
    const frac = (e.count - minCount) / span;
    const fontSize = minF + frac * (maxF - minF);
    const alpha = Math.round((0.62 + frac * 0.38) * 255)
      .toString(16).padStart(2, "0");

    const item = document.createElement("span");
    item.className = "collab-item";
    item.title = e.title;
    item.innerHTML =
      `<span class="collab-name" style="font-size:${fontSize.toFixed(0)}px;color:${accent}${alpha};">` +
        `${escapeHtml(e.text)}</span>` +
      `<span class="collab-count" style="font-size:${Math.max(10, fontSize * 0.5).toFixed(0)}px;">` +
        `${e.count}</span>`;
    container.appendChild(item);
  });
}

function renderCollaborators(collab, accent) {
  renderWordCloud("collabCloud", collab.map(c => ({
    text: lastNameOf(c.name),
    count: c.count,
    title: `${c.name}: ${c.count} shared paper${c.count === 1 ? "" : "s"}`,
  })), accent, 15, 48);
}

function renderJournals(journals, accent) {
  renderWordCloud("journalCloud", journals.map(j => ({
    text: j.name,
    count: j.count,
    title: `${j.name}: ${j.count} paper${j.count === 1 ? "" : "s"}`,
  })), accent, 12, 26);
}

function firstAuthorLastName(w) {
  if (!w.authors.length) return "Unknown";
  return w.authors[0].trim().split(/\s+/).pop();
}

function buildTopPapersCitationGrowth(limit) {
  const top = [...WORKS].sort((a, b) => b.citations - a.citations).slice(0, limit);
  const yearsSet = new Set();
  top.forEach(w => (w.countsByYear || []).forEach(c => yearsSet.add(c.year)));
  const years = [...yearsSet].sort((a, b) => a - b);

  const datasets = top.map((w, i) => {
    const byYear = {};
    (w.countsByYear || []).forEach(c => { byYear[c.year] = c.citations; });
    let cumulative = 0;
    const data = years.map(y => {
      cumulative += (byYear[y] || 0);
      return cumulative;
    });
    return {
      label: `${firstAuthorLastName(w)} (${w.year})`,
      data,
      borderColor: LINE_PALETTE[i % LINE_PALETTE.length],
      backgroundColor: LINE_PALETTE[i % LINE_PALETTE.length],
      fill: false,
      tension: 0.2,
    };
  });

  return { years, datasets };
}

function renderCharts() {
  const { accent, accent2, accent3, text, textMuted, grid } = getAccentColors();
  const pubs = buildPubsPerYear();
  const cites = buildCitationsOverTime();
  const collab = buildTopCollaborators(20);
  const journals = buildTopJournals(18);
  const topPapers = buildTopPapersCitationGrowth(10);

  if (pubsChart) pubsChart.destroy();
  if (citesChart) citesChart.destroy();
  if (topPapersChart) topPapersChart.destroy();

  // Canvas can't read CSS variables, so drive Chart.js text/grid colours from
  // the resolved theme values (keeps axes/legends legible on dark themes).
  Chart.defaults.color = textMuted;
  Chart.defaults.borderColor = grid;

  renderCollaborators(collab, accent);
  renderJournals(journals, accent);

  pubsChart = new Chart(document.getElementById("pubsChart"), {
    type: "bar",
    data: {
      labels: pubs.years,
      datasets: [
        {
          label: "Papers published",
          data: pubs.counts,
          backgroundColor: accent,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { type: "linear", position: "left", title: { display: true, text: "Papers" }, beginAtZero: true },
      },
    },
  });

  citesChart = new Chart(document.getElementById("citesChart"), {
    data: {
      labels: cites.years,
      datasets: [
        {
          type: "bar",
          label: "Citations received that year",
          data: cites.perYear,
          backgroundColor: accent2,
          yAxisID: "yPerYear",
          order: 2,
        },
        {
          type: "line",
          label: "Cumulative citations",
          data: cites.cumulativeSeries,
          borderColor: accent3,
          backgroundColor: accent3,
          yAxisID: "yCumulative",
          tension: 0.2,
          borderWidth: 3,
          pointRadius: 2,
          order: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        yPerYear: { type: "linear", position: "left", title: { display: true, text: "Citations that year" } },
        yCumulative: { type: "linear", position: "right", title: { display: true, text: "Cumulative citations" }, grid: { drawOnChartArea: false } },
      },
    },
  });

  topPapersChart = new Chart(document.getElementById("topPapersChart"), {
    type: "line",
    data: {
      labels: topPapers.years,
      datasets: topPapers.datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } },
      },
      scales: {
        y: { title: { display: true, text: "Cumulative citations" } },
      },
    },
  });
}

// ---------- table: filter, sort, paginate ----------
const state = {
  filters: { title: "", year: "", citations: "", journal: "", authors: "" },
  types: null,   // Set of selected type keys; null = all types shown
  sortCol: "citations",
  sortDir: "desc",
  page: 1,
  pageSize: 25,
};

function typeKeyOf(w) {
  return w.type || "(unspecified)";
}

function parseNumericFilter(expr) {
  expr = expr.trim();
  if (!expr) return () => true;
  let m;
  if ((m = expr.match(/^<\s*(-?\d+(\.\d+)?)$/))) {
    const v = parseFloat(m[1]); return (x) => x < v;
  }
  if ((m = expr.match(/^>\s*(-?\d+(\.\d+)?)$/))) {
    const v = parseFloat(m[1]); return (x) => x > v;
  }
  if ((m = expr.match(/^(-?\d+(\.\d+)?)\s*-\s*(-?\d+(\.\d+)?)$/))) {
    const lo = parseFloat(m[1]), hi = parseFloat(m[3]);
    return (x) => x >= lo && x <= hi;
  }
  if ((m = expr.match(/^(-?\d+(\.\d+)?)$/))) {
    const v = parseFloat(m[1]); return (x) => x === v;
  }
  return () => true;
}

function getFilteredSorted() {
  const f = state.filters;
  const titleF = f.title.toLowerCase();
  const journalF = f.journal.toLowerCase();
  const authorsF = f.authors.toLowerCase();
  const yearTest = parseNumericFilter(f.year);
  const citesTest = parseNumericFilter(f.citations);

  let rows = WORKS.filter(w => {
    if (titleF && !(w.title || "").toLowerCase().includes(titleF)) return false;
    if (journalF && !(w.journal || "").toLowerCase().includes(journalF)) return false;
    if (state.types && !state.types.has(typeKeyOf(w))) return false;
    if (authorsF && !w.authors.some(a => a.toLowerCase().includes(authorsF))) return false;
    if (!yearTest(w.year)) return false;
    if (!citesTest(w.citations)) return false;
    return true;
  });

  rows.sort((a, b) => {
    let av = a[state.sortCol], bv = b[state.sortCol];
    if (state.sortCol === "journal") { av = av || ""; bv = bv || ""; }
    if (state.sortCol === "authors") { av = av.join(", "); bv = bv.join(", "); }
    if (typeof av === "string") {
      const cmp = av.localeCompare(bv);
      return state.sortDir === "asc" ? cmp : -cmp;
    }
    return state.sortDir === "asc" ? av - bv : bv - av;
  });

  return rows;
}

function authorsCellHtml(authors) {
  if (authors.length <= 7) return escapeHtml(authors.join(", "));
  const shown = `${escapeHtml(authors[0])} ... ${escapeHtml(authors[authors.length - 1])}`;
  const full = escapeHtml(authors.join(", "));
  const id = "auth-" + Math.random().toString(36).slice(2, 9);
  return `<span id="${id}-short">${shown} <span class="authors-more" onclick="
      document.getElementById('${id}-short').style.display='none';
      document.getElementById('${id}-full').style.display='inline';
    ">+${authors.length - 2} more</span></span>
    <span id="${id}-full" style="display:none">${full}</span>`;
}

function renderTable() {
  const rows = getFilteredSorted();
  document.getElementById("rowCount").textContent = rows.length;

  const totalPages = Math.max(1, Math.ceil(rows.length / state.pageSize));
  if (state.page > totalPages) state.page = totalPages;
  const start = (state.page - 1) * state.pageSize;
  const pageRows = rows.slice(start, start + state.pageSize);

  const tbody = document.getElementById("tableBody");
  tbody.innerHTML = pageRows.map(w => {
    const titleCell = w.doi
      ? `<a href="${w.doi}" target="_blank" rel="noopener">${escapeHtml(w.title)}</a>`
      : escapeHtml(w.title);
    return `<tr>
      <td>${titleCell}</td>
      <td>${w.year}</td>
      <td>${w.citations.toLocaleString()}</td>
      <td>${escapeHtml(w.journal || "")}</td>
      <td>${authorsCellHtml(w.authors)}</td>
      <td><span class="type-badge">${escapeHtml(w.type || "")}</span></td>
    </tr>`;
  }).join("");

  document.getElementById("pageInfo").textContent = `Page ${state.page} of ${totalPages}`;
  document.getElementById("prevPage").disabled = state.page <= 1;
  document.getElementById("nextPage").disabled = state.page >= totalPages;

  document.querySelectorAll("th[data-col]").forEach(th => {
    const col = th.getAttribute("data-col");
    const arrow = th.querySelector(".sort-arrow");
    arrow.textContent = state.sortCol === col ? (state.sortDir === "asc" ? "▲" : "▼") : "";
  });
}

document.querySelectorAll("th[data-col]").forEach(th => {
  th.addEventListener("click", () => {
    const col = th.getAttribute("data-col");
    if (state.sortCol === col) {
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortCol = col;
      state.sortDir = col === "citations" ? "desc" : "asc";
    }
    state.page = 1;
    renderTable();
  });
});

document.querySelectorAll("input[data-filter]").forEach(input => {
  input.addEventListener("input", () => {
    state.filters[input.getAttribute("data-filter")] = input.value;
    state.page = 1;
    renderTable();
  });
});

// ---------- type filter dropdown ----------
function initTypeFilter() {
  const allTypes = [...new Set(WORKS.map(typeKeyOf))].sort();
  state.types = new Set(allTypes);   // start with everything shown

  const menu = document.getElementById("typeMenu");
  const summary = document.getElementById("typeSummary");

  function updateSummary() {
    if (state.types.size === allTypes.length) {
      summary.textContent = "All types";
    } else if (state.types.size === 0) {
      summary.textContent = "None";
    } else if (state.types.size === 1) {
      summary.textContent = [...state.types][0];
    } else {
      summary.textContent = `${state.types.size} of ${allTypes.length} types`;
    }
  }

  const actions = document.createElement("div");
  actions.className = "type-actions";
  const all = document.createElement("a"); all.textContent = "All";
  const none = document.createElement("a"); none.textContent = "None";
  actions.appendChild(all);
  actions.appendChild(none);
  menu.appendChild(actions);

  const boxes = [];
  allTypes.forEach(t => {
    const count = WORKS.filter(w => typeKeyOf(w) === t).length;
    const label = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = true;
    cb.value = t;
    cb.addEventListener("change", () => {
      if (cb.checked) state.types.add(t); else state.types.delete(t);
      updateSummary();
      state.page = 1;
      renderTable();
    });
    boxes.push(cb);
    label.appendChild(cb);
    label.appendChild(document.createTextNode(`${t} (${count})`));
    menu.appendChild(label);
  });

  function setAll(on) {
    state.types = on ? new Set(allTypes) : new Set();
    boxes.forEach(cb => { cb.checked = on; });
    updateSummary();
    state.page = 1;
    renderTable();
  }
  all.addEventListener("click", () => setAll(true));
  none.addEventListener("click", () => setAll(false));

  // Dismiss the dropdown on an outside click or Escape (native <details> only
  // closes when its own summary is clicked again).
  const details = document.getElementById("typeFilter");
  document.addEventListener("click", (e) => {
    if (details.open && !details.contains(e.target)) details.open = false;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") details.open = false;
  });

  updateSummary();
}

document.getElementById("prevPage").addEventListener("click", () => {
  if (state.page > 1) { state.page--; renderTable(); }
});
document.getElementById("nextPage").addEventListener("click", () => {
  state.page++; renderTable();
});

// ---------- constellation ----------
function renderConstellation() {
  const host = document.getElementById("constellation");
  const W = host.clientWidth || 560;
  const H = host.clientHeight || 280;
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  const nodes = CONSTELLATION.nodes;
  const edges = CONSTELLATION.edges;
  const maxC = Math.max(...nodes.map(n => n.citations), 1);
  const px = n => 12 + n.x * (W - 24);
  const py = n => 12 + n.y * (H - 24);
  const rOf = c => 2.4 + Math.sqrt(c / maxC) * 15;

  const mk = (tag, attrs) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  };

  // faint background field stars (deterministic scatter)
  let seed = 7;
  const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
  for (let i = 0; i < 70; i++) {
    svg.appendChild(mk("circle", { cx: rnd() * W, cy: rnd() * H, r: 0.4 + rnd() * 1.0,
      fill: "#ffffff", opacity: (0.04 + rnd() * 0.16).toFixed(2) }));
  }

  // constellation lines (within communities)
  edges.forEach(([a, b]) => {
    const na = nodes[a], nb = nodes[b];
    const col = na.comm >= 0 && na.comm === nb.comm ? na.color : "#8b93a7";
    svg.appendChild(mk("line", { x1: px(na), y1: py(na), x2: px(nb), y2: py(nb),
      stroke: col, "stroke-width": 0.6, opacity: 0.22 }));
  });

  // stars — draw faintest first so the most-cited papers sit on top
  [...nodes].sort((a, b) => a.citations - b.citations).forEach(n => {
    const r = rOf(n.citations);
    const g = mk("g", { class: "star" });
    // Glow halos are non-interactive so a bright star's halo doesn't steal
    // hover/click from a neighbouring star underneath it — only the solid core
    // is the hit target.
    g.appendChild(mk("circle", { cx: px(n), cy: py(n), r: r * 1.9, fill: n.color, opacity: 0.08, "pointer-events": "none" }));
    g.appendChild(mk("circle", { cx: px(n), cy: py(n), r: r * 1.25, fill: n.color, opacity: 0.18, "pointer-events": "none" }));
    g.appendChild(mk("circle", { cx: px(n), cy: py(n), r: r, fill: n.color, stroke: "#0a0f1e", "stroke-width": 0.6 }));
    if (r > 6) g.appendChild(mk("circle", { cx: px(n), cy: py(n), r: r * 0.4, fill: "#ffffff", opacity: 0.9, "pointer-events": "none" }));
    const title = document.createElementNS(NS, "title");
    title.textContent = `${n.title} — ${n.citations.toLocaleString()} citations · ${n.topic}`;
    g.appendChild(title);
    if (n.doi) g.addEventListener("click", () => window.open(n.doi, "_blank", "noopener"));
    svg.appendChild(g);
  });

  // one topic label per named community, at its brightest star
  CONSTELLATION.legend.forEach(lg => {
    const anchor = nodes.find(n => n.isAnchor && n.color === lg.color);
    if (!anchor) return;
    const r = rOf(anchor.citations);
    const right = anchor.x < 0.72;
    const t = mk("text", {
      x: right ? px(anchor) + r + 5 : px(anchor) - r - 5,
      y: py(anchor) + 3.5, "font-size": 11, "font-weight": 600,
      fill: lg.color, "text-anchor": right ? "start" : "end",
    });
    t.textContent = lg.short;
    svg.appendChild(t);
  });

  host.innerHTML = "";
  host.appendChild(svg);
}

// ---------- theme ----------
document.getElementById("themeSelect").addEventListener("change", (e) => {
  document.documentElement.setAttribute("data-theme", e.target.value);
  renderCharts();
});

// ---------- init ----------
renderTiles();
renderCharts();
renderConstellation();
initTypeFilter();
renderTable();
window.addEventListener("resize", renderConstellation);
</script>

</body>
</html>
"""

if __name__ == "__main__":
    build()
