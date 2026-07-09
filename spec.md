# Publications & Citations Page — Spec

## Overview
A single self-contained `index.html` file, opened directly in a browser (no
server required), showing Michael J. MacCoss's publications and citation
growth, sourced from `openalex_works.json` (483 works, fetched via
`fetch_openalex_works.py` from OpenAlex using ORCID
`0000-0003-1853-0256`).

## Data loading
- `index.html` loads `openalex_works.json` via `fetch()` at page load
  (works when opened via a local web server or `file://` in browsers that
  allow local fetch; if `file://` fetch is blocked by the browser, the JSON
  will be inlined into the HTML as a fallback so the page always works
  standalone).
- Chart.js is loaded from a CDN (`<script src="https://cdn.jsdelivr.net/...">`).
  Requires internet access for charts to render; page structure/table still
  work offline.

## Header
- Page title: just the name, **"Michael J. MacCoss"** (no subtitle).
- Affiliation line: University of Washington, Department of Genome Sciences.
- Three links, small and unobtrusive: **ORCID**, **Google Scholar**,
  **Lab website**.
  - ORCID: https://orcid.org/0000-0003-1853-0256
  - Google Scholar: https://scholar.google.com/citations?user=icweOB0AAAAJ&hl=en
  - Lab website: https://maccosslab.org/maccoss/
- A small, unobtrusive **theme dropdown** in the header corner, offering at
  least two accent-color palettes:
  - **UW Purple/Gold** (#4B2E83 / #B7A57A)
  - **Blue/Teal**
  Switching updates accent colors used in tiles, chart series, and links.
  Selection is not required to persist across reloads.

## Summary stat tiles
Row of tiles below the header, above the charts:
1. **Total papers** — count of all works in the dataset.
2. **Total citations** — sum of `cited_by_count` across all works.
3. **h-index** — computed client-side from each paper's `cited_by_count`.
4. **Most-cited paper** — title + citation count of the single highest-cited
   work, as a highlighted tile (clicking it could scroll to/highlight the row
   in the table — nice-to-have, not required).

## Charts
Two chart panels, side by side or stacked, both using Chart.js:

1. **Publications per year**
   - Combo chart: bar series = number of papers published that year, line
     series (secondary axis) = cumulative total citations by year.
   - X-axis: publication year, full range from earliest to latest paper.

2. **Citations over time**
   - Two series shown together (or as two small charts): cumulative total
     citations by year, and citations received per year.
   - **Data limitation**: OpenAlex's `counts_by_year` field only provides
     per-year citation counts for roughly the last ~10 years (currently
     ~2015/2016–2026), not full history back to each paper's publication
     date. Per your choice, this chart will only cover the years OpenAlex
     actually provides data for (so the x-axis range here will be shorter
     than the publications-per-year chart). A short caption under the chart
     will note this limitation.
   - Cumulative citations = running sum of per-year citation counts across
     all papers, for the years in range.

## Papers table
- Paginated, **25 rows per page**, with page controls (prev/next, page
  numbers).
- Default sort: **citation count, descending**. A sort control lets the
  user switch to sort by year or citations (asc/desc).
- Every column is **filterable**:
  - Title, Journal/venue, Type: text/substring filter.
  - Authors: text/substring filter (matches against author names).
  - Year: numeric filter supporting `<x`, `>x`, and `x-y` range syntax.
  - Citations: numeric filter supporting `<x`, `>x`, and `x-y` range syntax.
- Columns:
  1. **Title** — linked to the DOI (opens in new tab) when a DOI is present.
  2. **Year**
  3. **Citations**
  4. **Journal/venue** (from `primary_location.source.display_name`)
  5. **Authors** — full author list normally; if the paper has **more than 7
     authors**, show only first and last author (e.g. "J. Smith ... M.
     MacCoss") with a way to see the full list (e.g. hover title / small
     "+N more" expandable).
  6. **Type** — OpenAlex `type` field (article, dataset, paratext, etc.),
     shown and filterable so non-article entries (datasets, posters, etc.)
     are visible rather than silently excluded.

## Visual style
- "Modern dashboard" look: card-based sections with subtle shadows/borders,
  rounded corners, generous whitespace, accent color per the theme dropdown
  above.
- Desktop-optimized only — no mobile/responsive layout requirement.

## Files in this folder after this step
- `fetch_openalex_works.py` — script used to fetch/refresh the OpenAlex data.
- `openalex_works.json` — raw fetched data (483 works).
- `spec.md` — this file.
- `index.html` — the built page (created only after this spec is approved).

## Verification (after build)
- Confirm `index.html` and its inline/linked JavaScript are well-formed
  (no syntax errors).
- Confirm the page successfully loads `openalex_works.json` and that the
  loaded paper count matches 483 (and total citations matches 46,964, or
  the current numbers in the file if it's been refreshed).
