# Publications & Citations Page — Spec

## Overview
A single self-contained `index.html`, opened directly in any browser (no
server needed), showing Michael J. MacCoss's publications and citation
growth. Data comes from OpenAlex (ORCID `0000-0003-1853-0256`), fetched by
`fetch_openalex_works.py` and refreshed monthly by a GitHub Action.

## Data loading
- `build_page.py` reduces `openalex_works.json` to the fields the page needs
  and embeds them into `index.html` as an inline JS array — no runtime
  `fetch()`, so the file works standalone via `file://`.
- **Preprints are excluded** from the whole page (`is_preprint` in
  `build_page.py`): OpenAlex `type: preprint`, or a source that is a preprint
  server (bioRxiv, arXiv, medRxiv, ChemRxiv, …). They inflate the per-year
  counts and are usually preprint versions of papers already counted from
  their published journal. The raw `openalex_works.json` still contains them;
  the filter is applied at build time so every panel and the totals are
  consistent.
- Chart.js, `chartjs-plugin-zoom`, and Hammer.js (which the zoom plugin needs
  for drag-to-pan gestures) load from a CDN (needs internet for charts; the
  table works offline).

## Header
- Title: **Michael J. MacCoss**. Affiliation: University of Washington,
  Department of Genome Sciences.
- Links: **ORCID**, **Google Scholar**, **Lab website**.
- **Theme dropdown** with six themes. Each defines three accent colours —
  `--accent` (headings, links, tile borders, publications bars, word cloud),
  `--accent-2` (citations-per-year bars), `--accent-3` (cumulative line) —
  plus `--accent-soft` (table header, type badges):
  - **Classic navy** (default) — `#1e3a70` / `#6f97d6` / `#d97757`
  - **Charcoal** — `#374151` / `#9aa5b1` / `#10b981`
  - **Indigo** — `#4f46e5` / `#a5b4fc` / `#f472b6`
  - **Emerald** — `#047857` / `#6ee7b7` / `#0ea5e9`
  - **Midnight (dark)** — `#8ab4f8` / `#38bdf8` / `#f472b6`
  - **Carbon (dark)** — `#a78bfa` / `#c4b5fd` / `#34d399`
- All surfaces/text are CSS variables, so the dark themes flip the whole page
  (background, cards, text, borders), not just the accents. Chart.js reads the
  resolved variables at render time so axes stay legible on dark themes.
  Selection need not persist across reloads.

## Summary stat tiles
Three tiles: **Total papers**, **Total citations**, **h-index** (h-index
computed client-side from each paper's citation count).

## Charts
A 2×2 grid of panels, then two full-width panels above the table. Chart.js
canvases except where noted; each panel has a fixed compact height.

1. **Publications per year** — single-series bar chart of papers per year,
   full year range.
2. **Citations over time** — bars = citations received per year, line =
   cumulative citations. Limited to OpenAlex's ~10-year `counts_by_year`
   window (captioned), so a shorter x-axis than chart 1. The line is drawn
   over the bars with a heavier stroke to stay visible.
3. **Top 20 collaborators** — word cloud (themed HTML): each co-author's
   surname sized by number of shared papers, exact count printed after the
   name, full name on hover. Co-authors keyed by OpenAlex author ID (not name);
   MacCoss himself excluded. Uses `--accent` at graduated opacity.
4. **Top journals** — word cloud (same renderer as collaborators), each journal
   sized by number of papers published there. Non-journal sources (preprint
   servers, data repositories like Figshare) are excluded.
5. **Top 50 papers — impact over time** — full-width bubble scatter. Each
   bubble is a top-50 paper positioned by publication year (x) and citations
   (y), sized by citations and coloured by its OpenAlex primary topic. The top
   topics by citation weight get a colour + short label in a legend (short names
   from a hand-written `TOPIC_SHORT` map; unmapped topics use their full OpenAlex
   name); the rest are grey "Other". Papers are labelled on the plot as
   `first-author-lastname, year` — candidates are those currently in view, ranked
   by citations, with a label budget that grows as you zoom in, so zooming a
   region labels more of its papers than just the global top-10 (highest-cited
   placed first, any that can't fit without overlap are skipped). Hover shows
   author, year, citations and the title (first 50 chars); click opens the DOI.
   Zoomable/pannable via `chartjs-plugin-zoom`: drag to zoom a region, Shift+drag
   to pan, scroll to zoom, with a "Reset zoom" button. Topic colours are a fixed
   categorical palette; data is `compute_top_papers` in `build_page.py`.
6. **Citation growth of top 10 most-cited papers** — full-width panel above the
   table. One cumulative line per paper over the ~10-year window. Fixed
   10-colour palette (legible on light and dark). Legend labels are
   `first-author-lastname (year)`.

## Papers table
- Paginated, 25 rows/page. Default sort: citations descending; sortable by any
  column.
- Column filters: text/substring for Title, Journal, Authors; numeric
  `<x` / `>x` / `x-y` for Year and Citations; **Type** is a checkbox dropdown
  (one entry per distinct type, with counts, plus All/None) so the user picks
  the types to show instead of typing.
- Columns: **Title** (DOI link when present), **Year**, **Citations**,
  **Journal**, **Authors** (first + last only when >7 authors, expandable),
  **Type**.

## Visual style
Modern dashboard — cards, subtle shadows, rounded corners. Content centered in
a `max-width: 1180px` column. Desktop-optimized only.

## Data quality
OpenAlex's author clustering merged **Malcolm MacCoss** (a Merck chemist, raw
name "MacCoss, M.") into this ORCID's Author ID, pulling in two crystal-
structure deposits (CCDC 117932, CCDC 245444). `fetch_openalex_works.py`
excludes those work IDs (`EXCLUDED_WORK_IDS`). `flag_outlier_papers.py` flags
further possible misattributions for manual review.

## Files
- `fetch_openalex_works.py` — fetch/refresh OpenAlex data; excludes known
  misattributions.
- `flag_outlier_papers.py` — flag papers that may not be MacCoss's.
- `build_page.py` — build `index.html` from `openalex_works.json`.
- `openalex_works.json` — fetched data.
- `index.html` — the built page.
- `.github/workflows/update-publications.yml` — monthly auto-refresh.
- `spec.md` — this file.

## Verification (after build)
- `index.html` and its inline JS are well-formed (no syntax errors).
- Embedded paper count and total citations are the post-preprint-filter totals
  (currently 397 papers / 46,586 citations from 481 fetched; changes as the
  Action runs).
