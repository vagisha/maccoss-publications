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

SOURCE_FILE = "openalex_works.json"
OUTPUT_FILE = "index.html"


def reduce_work(w):
    authorships = w.get("authorships") or []
    authors = []
    for a in authorships:
        author = a.get("author") or {}
        name = author.get("display_name") or a.get("raw_author_name")
        if name:
            authors.append(name)

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
        "doi": w.get("doi"),
        "type": w.get("type"),
        "countsByYear": counts_by_year,
    }


def build():
    with open(SOURCE_FILE, encoding="utf-8") as f:
        raw_works = json.load(f)

    works = [reduce_work(w) for w in raw_works]
    works = [w for w in works if w["year"] is not None]

    data_json = json.dumps(works, ensure_ascii=False)

    html = HTML_TEMPLATE.replace("__WORKS_DATA__", data_json)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Wrote {OUTPUT_FILE} with {len(works)} works embedded.")
    print(f"Total citations: {sum(w['citations'] for w in works)}")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" data-theme="uw">
<head>
<meta charset="UTF-8">
<title>Michael J. MacCoss</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
  :root[data-theme="uw"] {
    --accent: #4B2E83;
    --accent-2: #B7A57A;
    --accent-soft: #ece7f3;
  }
  :root[data-theme="blue"] {
    --accent: #1a5f7a;
    --accent-2: #57c5b6;
    --accent-soft: #e3f2f4;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 32px 48px 64px;
    background: #f4f5f7;
    color: #1e1e24;
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    min-width: 1100px;
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
    color: #555;
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
    color: #555;
  }
  .theme-picker select {
    margin-left: 6px;
    padding: 4px 8px;
    border-radius: 6px;
    border: 1px solid #ccc;
    background: white;
  }
  .card {
    background: white;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
    padding: 20px 24px;
    margin-bottom: 24px;
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
  }
  .tile {
    background: white;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
    padding: 18px 20px;
    border-top: 3px solid var(--accent);
  }
  .tile .label {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #888;
    margin-bottom: 6px;
  }
  .tile .value {
    font-size: 26px;
    font-weight: 600;
    color: #1e1e24;
  }
  .tile.highlight .value {
    font-size: 15px;
    font-weight: 500;
    line-height: 1.35;
  }
  .charts {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-bottom: 24px;
  }
  .card h2 {
    margin-top: 0;
    font-size: 16px;
    color: #333;
  }
  .caption {
    font-size: 12px;
    color: #888;
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
    border-bottom: 1px solid #eee;
    vertical-align: top;
  }
  th {
    background: var(--accent-soft);
    color: #333;
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
    border: 1px solid #ddd;
    border-radius: 4px;
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
    border: 1px solid #ccc;
    background: white;
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
</style>
</head>
<body>

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
      <option value="uw">UW Purple/Gold</option>
      <option value="blue">Blue/Teal</option>
    </select>
  </div>
</header>

<div class="tiles" id="tiles"></div>

<div class="charts">
  <div class="card">
    <h2>Publications per year</h2>
    <canvas id="pubsChart" height="220"></canvas>
  </div>
  <div class="card">
    <h2>Citations over time</h2>
    <canvas id="citesChart" height="220"></canvas>
    <div class="caption">
      OpenAlex only reports per-year citation counts for roughly the last
      ~10 years for each paper, not full history back to publication date.
      This chart is limited to the years OpenAlex actually provides data
      for, so its range is shorter than the publications-per-year chart.
    </div>
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
        <th><input data-filter="type" placeholder="filter type..."></th>
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

<script>
const WORKS = __WORKS_DATA__;

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
  const mostCited = WORKS.reduce((best, w) => (w.citations > (best ? best.citations : -1) ? w : best), null);

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

  const highlight = document.createElement("div");
  highlight.className = "tile highlight";
  highlight.innerHTML = `<div class="label">Most-cited paper</div>
    <div class="value">${escapeHtml(mostCited.title)} (${mostCited.citations.toLocaleString()} citations, ${mostCited.year})</div>`;
  container.appendChild(highlight);
}

function escapeHtml(s) {
  if (!s) return "";
  return s.replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// ---------- charts ----------
let pubsChart, citesChart;

function getAccentColors() {
  const styles = getComputedStyle(document.documentElement);
  return {
    accent: styles.getPropertyValue("--accent").trim(),
    accent2: styles.getPropertyValue("--accent-2").trim(),
  };
}

function buildPubsPerYear() {
  const byYear = {};
  WORKS.forEach(w => { byYear[w.year] = (byYear[w.year] || 0) + 1; });
  const years = Object.keys(byYear).map(Number).sort((a, b) => a - b);

  const byYearCitations = {};
  WORKS.forEach(w => { byYearCitations[w.year] = (byYearCitations[w.year] || 0) + w.citations; });
  let cumulative = 0;
  const cumulativeSeries = years.map(y => {
    cumulative += (byYearCitations[y] || 0);
    return cumulative;
  });

  return { years, counts: years.map(y => byYear[y]), cumulativeSeries };
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

function renderCharts() {
  const { accent, accent2 } = getAccentColors();
  const pubs = buildPubsPerYear();
  const cites = buildCitationsOverTime();

  if (pubsChart) pubsChart.destroy();
  if (citesChart) citesChart.destroy();

  pubsChart = new Chart(document.getElementById("pubsChart"), {
    data: {
      labels: pubs.years,
      datasets: [
        {
          type: "bar",
          label: "Papers published",
          data: pubs.counts,
          backgroundColor: accent,
          yAxisID: "yCount",
        },
        {
          type: "line",
          label: "Cumulative citations",
          data: pubs.cumulativeSeries,
          borderColor: accent2,
          backgroundColor: accent2,
          yAxisID: "yCites",
          tension: 0.2,
        },
      ],
    },
    options: {
      responsive: true,
      scales: {
        yCount: { type: "linear", position: "left", title: { display: true, text: "Papers" } },
        yCites: { type: "linear", position: "right", title: { display: true, text: "Cumulative citations" }, grid: { drawOnChartArea: false } },
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
        },
        {
          type: "line",
          label: "Cumulative citations",
          data: cites.cumulativeSeries,
          borderColor: accent,
          backgroundColor: accent,
          yAxisID: "yCumulative",
          tension: 0.2,
        },
      ],
    },
    options: {
      responsive: true,
      scales: {
        yPerYear: { type: "linear", position: "left", title: { display: true, text: "Citations that year" } },
        yCumulative: { type: "linear", position: "right", title: { display: true, text: "Cumulative citations" }, grid: { drawOnChartArea: false } },
      },
    },
  });
}

// ---------- table: filter, sort, paginate ----------
const state = {
  filters: { title: "", year: "", citations: "", journal: "", authors: "", type: "" },
  sortCol: "citations",
  sortDir: "desc",
  page: 1,
  pageSize: 25,
};

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
  const typeF = f.type.toLowerCase();
  const yearTest = parseNumericFilter(f.year);
  const citesTest = parseNumericFilter(f.citations);

  let rows = WORKS.filter(w => {
    if (titleF && !(w.title || "").toLowerCase().includes(titleF)) return false;
    if (journalF && !(w.journal || "").toLowerCase().includes(journalF)) return false;
    if (typeF && !(w.type || "").toLowerCase().includes(typeF)) return false;
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
renderTable();
</script>

</body>
</html>
"""

if __name__ == "__main__":
    build()
