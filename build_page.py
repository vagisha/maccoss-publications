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
import re
from collections import Counter

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

# ---- top papers scatter (citations vs. year, coloured by OpenAlex topic) ----
TOP_PAPERS_N = 50
TOP_PAPERS_MAX_TOPICS = 6   # colour+label this many topics; rest are "Other"
# Categorical palette (saturated mid-tones that stay legible on both the light
# and dark theme card backgrounds).
TOPIC_COLORS = [
    "#2a78d6", "#1baf7a", "#eda100", "#7c5cd6", "#e34948", "#2f9e44",
]
TOPIC_OTHER_COLOR = "#8a8f98"
# Short display names for the (long) OpenAlex topic labels; unknown topics fall
# back to their full OpenAlex name.
TOPIC_SHORT = {
    "Advanced Proteomics Techniques and Applications": "Proteomics methods",
    "Genetics, Aging, and Longevity in Model Organisms": "Genetics & aging",
    "Bacterial biofilms and quorum sensing": "Microbiology",
    "Genomics and Chromatin Dynamics": "Genomics",
    "Ubiquitin and proteasome pathways": "Ubiquitin/proteasome",
    "Metabolomics and Mass Spectrometry Studies": "Metabolomics",
    "Mass Spectrometry Techniques and Applications": "Mass spectrometry",
}


def _topic_of(w):
    return (w.get("primary_topic") or {}).get("display_name") or "Uncategorized"


def _first_author(w):
    for a in w.get("authorships") or []:
        name = (a.get("author") or {}).get("display_name") or a.get("raw_author_name")
        if name:
            return name
    return "Unknown"


def compute_top_papers(raw_works):
    """The top-N cited papers for the scatter chart: publication year vs.
    citation count, coloured by OpenAlex primary topic. The top few topics by
    total citation weight get a colour + short label; the rest are "Other"."""
    top = sorted(raw_works, key=lambda w: w.get("cited_by_count", 0), reverse=True)
    top = [w for w in top[:TOP_PAPERS_N] if w.get("publication_year")]

    topic_weight = Counter()
    for w in top:
        topic_weight[_topic_of(w)] += w.get("cited_by_count", 0)
    named = [t for t, _ in topic_weight.most_common(TOP_PAPERS_MAX_TOPICS)]
    topic_color = {t: TOPIC_COLORS[k % len(TOPIC_COLORS)] for k, t in enumerate(named)}

    def short(t):
        return TOPIC_SHORT.get(t, t)

    nodes = []
    for w in top:
        topic = _topic_of(w)
        nodes.append({
            "title": w.get("display_name") or w.get("title"),
            "firstAuthor": _first_author(w),
            "year": w.get("publication_year"),
            "citations": w.get("cited_by_count", 0),
            "doi": w.get("doi"),
            "topic": topic,
            "topicShort": short(topic) if topic in topic_color else "Other",
            "color": topic_color.get(topic, TOPIC_OTHER_COLOR),
        })

    legend = [{"label": short(t), "color": topic_color[t]} for t in named]
    legend.append({"label": "Other", "color": TOPIC_OTHER_COLOR})
    return {"nodes": nodes, "legend": legend}


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
    top_papers_json = json.dumps(compute_top_papers(raw_works), ensure_ascii=False)

    # Earliest year OpenAlex provides per-year citation counts for (the window
    # slides over time, so read it from the data rather than hard-coding it).
    cite_years = [c["year"] for w in works for c in w["countsByYear"] if c["year"]]
    cite_start_year = str(min(cite_years)) if cite_years else "recent years"

    html = (HTML_TEMPLATE
            .replace("__WORKS_DATA__", data_json)
            .replace("__TOP_PAPERS_DATA__", top_papers_json)
            .replace("__CITE_START_YEAR__", cite_start_year))

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
<script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
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
  .card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .card-head h2 { margin: 0; }
  .reset-zoom {
    font-size: 12px;
    padding: 4px 10px;
    border-radius: 6px;
    border: 1px solid var(--border-strong);
    background: var(--card);
    color: var(--text);
    cursor: pointer;
  }
  .reset-zoom:hover { background: var(--accent-soft); }
  .topic-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
    margin-bottom: 10px;
    margin-top: 10px;
    font-size: 12px;
    color: var(--text-dim);
  }
  .topic-legend span { display: inline-flex; align-items: center; gap: 5px; }
  .topic-legend .sw { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
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
    cursor: pointer;
  }
  .collab-cloud .collab-item:hover .collab-name { text-decoration: underline; }
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
      The chart starts at __CITE_START_YEAR__ since OpenAlex reports per-year
      citations only from then on.
    </div>
  </div>
  <div class="card">
    <h2>Top 20 collaborators</h2>
    <div id="collabCloud" class="collab-cloud" style="height:280px"></div>
    <div class="caption">Text size shows shared papers, with the count after each name. Click a name to filter the table.</div>
  </div>
  <div class="card">
    <h2>Top journals</h2>
    <div id="journalCloud" class="collab-cloud" style="height:280px"></div>
    <div class="caption">Text size shows papers in each journal, preprints excluded. Click a journal to filter the table.</div>
  </div>
</div>

<div class="card">
  <div class="card-head">
    <h2>Top 50 most-cited papers</h2>
    <button id="resetZoom" class="reset-zoom" hidden>Reset zoom</button>
  </div>
  <div id="topicLegend" class="topic-legend"></div>
  <div class="chart-wrap" style="height:380px"><canvas id="scatterChart"></canvas></div>
  <div class="caption">
    Bubble = a paper, by year and citations, coloured by OpenAlex topic. Drag to
    zoom, Shift+drag to pan, scroll to zoom. Hover for details, click to open.
  </div>
</div>

<div class="card">
  <h2>Citation growth of top 10 most-cited papers</h2>
  <div class="chart-wrap" style="height:320px"><canvas id="topPapersChart"></canvas></div>
  <div class="caption">
    Cumulative citations per year, from __CITE_START_YEAR__ on.
  </div>
</div>

<div class="card">
  <div class="card-head">
    <h2>Papers (<span id="rowCount"></span>)</h2>
    <button id="clearFilters" class="reset-zoom" hidden>Clear filters</button>
  </div>
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
const TOP_PAPERS = __TOP_PAPERS_DATA__;

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
let pubsChart, citesChart, topPapersChart, scatterChart;

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

// Set a papers-table column filter and jump to the table. Reuses the existing
// filter <input> (dispatching "input" runs the normal filter/render path).
function applyColumnFilter(col, value) {
  const input = document.querySelector(`input[data-filter="${col}"]`);
  if (!input) return;
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  const card = document.getElementById("tableBody").closest(".card");
  if (card) card.scrollIntoView({ behavior: "smooth", block: "start" });
}

// Generic word cloud: font size scales with count, exact count printed after
// each label, theme accent colour at graduated opacity so it re-themes.
// entries: [{ text, count, title, filter: { col, value } }]; clicking an item
// applies that column filter to the table. minF/maxF bound the label font size.
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
    if (e.filter) item.addEventListener("click", () => applyColumnFilter(e.filter.col, e.filter.value));
    container.appendChild(item);
  });
}

function renderCollaborators(collab, accent) {
  renderWordCloud("collabCloud", collab.map(c => ({
    text: lastNameOf(c.name),
    count: c.count,
    title: `${c.name}: ${c.count} shared paper${c.count === 1 ? "" : "s"} — click to filter table`,
    filter: { col: "authors", value: c.name },
  })), accent, 15, 48);
}

function renderJournals(journals, accent) {
  renderWordCloud("journalCloud", journals.map(j => ({
    text: j.name,
    count: j.count,
    title: `${j.name}: ${j.count} paper${j.count === 1 ? "" : "s"} — click to filter table`,
    filter: { col: "journal", value: j.name },
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
  if (scatterChart) scatterChart.destroy();

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

  renderScatter(text, textMuted, grid);
}

// ---------- top-papers scatter: year vs citations, coloured by topic ----------
function renderTopicLegend() {
  const host = document.getElementById("topicLegend");
  host.innerHTML = "";
  TOP_PAPERS.legend.forEach(l => {
    const s = document.createElement("span");
    s.innerHTML = `<span class="sw" style="background:${l.color}"></span>${escapeHtml(l.label)}`;
    host.appendChild(s);
  });
}

function renderScatter(text, textMuted, grid) {
  renderTopicLegend();
  document.getElementById("resetZoom").hidden = true;   // fresh chart starts unzoomed
  const nodes = TOP_PAPERS.nodes;
  const maxC = Math.max(...nodes.map(n => n.citations), 1);
  const years = nodes.map(n => n.year);
  const minYr = Math.min(...years) - 1, maxYr = Math.max(...years) + 1;

  // One dataset per legend entry so the built-in legend toggles by topic.
  const byLabel = {};
  TOP_PAPERS.legend.forEach(l => { byLabel[l.label] = { label: l.label, color: l.color, data: [] }; });
  nodes.forEach((n, i) => {
    const key = byLabel[n.topicShort] ? n.topicShort : "Other";
    byLabel[key].data.push({ x: n.year, y: n.citations, r: 4 + Math.sqrt(n.citations / maxC) * 15, i });
  });
  const datasets = Object.values(byLabel).map(d => ({
    label: d.label, data: d.data,
    backgroundColor: d.color + "cc", borderColor: d.color, borderWidth: 1,
    hoverBackgroundColor: d.color,
  }));

  const cardColor = getComputedStyle(document.documentElement).getPropertyValue("--card").trim() || "#fff";
  const labelPlugin = {
    id: "pointLabels",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      ctx.save();
      ctx.font = "600 11px -apple-system, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.lineWidth = 3;
      ctx.lineJoin = "round";

      // Candidates = every point currently inside the plot area, ranked by
      // citations. The label budget grows as you zoom in (smaller visible year
      // range → more room), so more papers get labelled the further you zoom.
      const area = chart.chartArea;
      const xs = chart.scales.x;
      const zoomF = Math.max(1, (maxYr - minYr) / Math.max(0.001, xs.max - xs.min));
      const budget = Math.min(30, Math.round(10 * Math.sqrt(zoomF)));

      const cands = [];
      chart.data.datasets.forEach((ds, di) => {
        const meta = chart.getDatasetMeta(di);
        ds.data.forEach((pt, pi) => {
          const el = meta.data[pi];
          if (!el) return;
          if (el.x < area.left || el.x > area.right || el.y < area.top || el.y > area.bottom) return;
          const n = nodes[pt.i];
          cands.push({ x: el.x + el.options.radius + 4, y: el.y,
            text: `${lastNameOf(n.firstAuthor)}, ${n.year}`, cites: n.citations });
        });
      });
      cands.sort((a, b) => b.cites - a.cites);

      // Place highest-cited first; try the point's own line then a couple of
      // small nudges, and skip a label entirely if it can't fit without overlap.
      const placed = [];
      for (const it of cands) {
        if (placed.length >= budget) break;
        const w = ctx.measureText(it.text).width;
        let chosen = null;
        for (const dy of [0, 14, -14, 28, -28]) {
          const y = it.y + dy;
          if (y < area.top + 6 || y > area.bottom - 6) continue;
          let ok = true;
          for (const q of placed) {
            if (Math.abs(y - q.y) < 14 && it.x < q.x + q.w + 12 && q.x < it.x + w + 12) { ok = false; break; }
          }
          if (ok) { chosen = y; break; }
        }
        if (chosen === null) continue;
        placed.push({ x: it.x, y: chosen, w });
        ctx.strokeStyle = cardColor;
        ctx.strokeText(it.text, it.x, chosen);
        ctx.fillStyle = text;
        ctx.fillText(it.text, it.x, chosen);
      }
      ctx.restore();
    },
  };

  scatterChart = new Chart(document.getElementById("scatterChart"), {
    type: "bubble",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { right: 70, top: 10 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              const n = nodes[c.raw.i];
              return `${lastNameOf(n.firstAuthor)}, ${n.year} — ${n.citations.toLocaleString()} citations`;
            },
            // second line: the paper title, truncated to 50 characters
            afterLabel: (c) => {
              const t = nodes[c.raw.i].title || "";
              return t.length > 50 ? t.slice(0, 49).trimEnd() + "…" : t;
            },
          },
        },
        zoom: {
          pan: { enabled: true, mode: "xy", modifierKey: "shift", onPanComplete: showResetBtn },
          zoom: {
            wheel: { enabled: true, speed: 0.2 },
            drag: { enabled: true, backgroundColor: "rgba(90,120,200,0.15)",
                    borderColor: "rgba(90,120,200,0.6)", borderWidth: 1 },
            mode: "xy",
            onZoomComplete: showResetBtn,
          },
          // Limits are padded a little beyond the data so the data boundary
          // itself never clamps a wheel gesture (which would stall zoom-out);
          // they only stop runaway zoom-out / pan drift.
          limits: {
            x: { min: minYr - 4, max: maxYr + 4 },
            y: { min: -maxC * 0.06, max: maxC * 1.15 },
          },
        },
      },
      scales: {
        x: { min: minYr, max: maxYr, title: { display: true, text: "Publication year", color: textMuted },
             ticks: { color: textMuted, precision: 0 }, grid: { color: grid } },
        y: { beginAtZero: true, title: { display: true, text: "Citations", color: textMuted },
             ticks: { color: textMuted }, grid: { color: grid } },
      },
      onClick: (e, els) => {
        if (!els.length) return;
        const pt = scatterChart.data.datasets[els[0].datasetIndex].data[els[0].index];
        const doi = nodes[pt.i].doi;
        if (doi) window.open(doi, "_blank", "noopener");
      },
    },
    plugins: [labelPlugin],
  });
}

// Show the reset button only while the chart is actually zoomed or panned.
function showResetBtn() {
  const b = document.getElementById("resetZoom");
  if (!b || !scatterChart) return;
  b.hidden = scatterChart.isZoomedOrPanned ? !scatterChart.isZoomedOrPanned() : false;
}

document.getElementById("resetZoom").addEventListener("click", () => {
  if (scatterChart && scatterChart.resetZoom) scatterChart.resetZoom();
  document.getElementById("resetZoom").hidden = true;
});

// ---------- table: filter, sort, paginate ----------
const state = {
  filters: { title: "", year: "", citations: "", journal: "", authors: "" },
  types: null,   // Set of selected type keys; null = all types shown
  sortCol: "citations",
  sortDir: "desc",
  page: 1,
  pageSize: 25,
};

let resetTypeFilter = () => {};   // set by initTypeFilter (re-checks all types)
let totalTypeCount = 0;

function hasActiveFilters() {
  const f = state.filters;
  if (f.title || f.year || f.citations || f.journal || f.authors) return true;
  return !!(state.types && totalTypeCount && state.types.size !== totalTypeCount);
}

function updateClearBtn() {
  const b = document.getElementById("clearFilters");
  if (b) b.hidden = !hasActiveFilters();
}

function clearAllFilters() {
  document.querySelectorAll("input[data-filter]").forEach(inp => {
    inp.value = "";
    state.filters[inp.getAttribute("data-filter")] = "";
  });
  resetTypeFilter();
  state.page = 1;
  renderTable();
}

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

  updateClearBtn();
}

document.getElementById("clearFilters").addEventListener("click", clearAllFilters);

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

  // Expose "reset to all types" (without re-rendering) for the Clear filters button.
  totalTypeCount = allTypes.length;
  resetTypeFilter = () => {
    state.types = new Set(allTypes);
    boxes.forEach(cb => { cb.checked = true; });
    updateSummary();
  };

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

// ---------- theme ----------
document.getElementById("themeSelect").addEventListener("change", (e) => {
  document.documentElement.setAttribute("data-theme", e.target.value);
  renderCharts();
});

// ---------- init ----------
renderTiles();
renderCharts();
initTypeFilter();
renderTable();
</script>

</body>
</html>
"""

if __name__ == "__main__":
    build()
