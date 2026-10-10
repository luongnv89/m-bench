# m-bench docs (GitHub Pages)

Static site for measured benchmark results: four pages over one shared design system.

| Page | `<body data-page>` | Suites it renders | Owns |
|---|---|---|---|
| `index.html` | `llm` | `all,agentic-hard,agentic-all` | Machine recommendations, harness comparison, thinking trade-off, campaigns, suites — the coding-agent story |
| `system-one.html` | `system-one` | `system1` | Benchmark v3 (default): 200 scenarios / 200 questions, accuracy, latency, paraphrase stability, accuracy by family |
| `system-one-v2.html` | `system-one-v2` | `system1-v2` | Benchmark v2 reference: 200 scenarios / 400 questions, arithmetic-heavy, superseded by v3 |
| `system-one-v1.html` | `system-one-v1` | `system1-legacy,phishing-eval` | Benchmark v1 reference: 23 scenarios / 49 questions, historical rankings and the phishing workload |

- `assets/site.css` — the one design system: tokens, layout, nav, charts, ledger, responsive and reduced-motion rules
- `assets/site.js` — the one render layer: reads `<body data-page data-suites>` and renders only that page's sections and the suites it owns
- `data.json` — curated scores from `results/**` (regenerate when campaigns land)
- `assets/*.svg` — logo marks and favicon

All pages are shells: no inline `<style>`, no inline `<script>`. Adding a section means adding
markup with an id the renderer already targets, or a renderer keyed on the page; adding a
page means copying a shell, setting `data-page`/`data-suites`, and registering the
page's renderers in `site.js`. `tests/test_landing_page.py` fails if a ledger suite belongs
to no page, or to two pages.

Cross-page links live in the top nav (`aria-current="page"` marks the active page), the hero
cross-link, and the footer. `index.html` and `system-one.html` link to each other by relative
path; the v3, v2 and v1 pages all link to each other. Results require HTTP.

## Serve locally

```bash
python3 -m http.server 8080 --directory docs
# open http://localhost:8080
```

`fetch("data.json")` requires HTTP — opening a page via `file://` will fail (the static
markup and the skip link still render).

## Deploy

Workflow: `.github/workflows/pages.yml` deploys `docs/` on push to `main`.

One-time repo setup: **Settings → Pages → Source: GitHub Actions**.

## Updating data

Edit `data.json` when a new campaign report lands:

| Field | Meaning |
|---|---|
| `machines[].recommendations[]` | The “use this harness + model” cards |
| `harnessComparison` | Same-weights harness bar chart |
| `thinkingTradeoff` | One-shot vs tool-loop cost panels |
| `systemOne` | Current v3 comparison: dataset counts, families, `familyScores` (accuracy per family per model), `groupAcc` (paraphrase pairs), measured 95% intervals |
| `systemOneV2` | v2 reference comparison and its gateway caveats |
| `systemOneV1` / `realUseCase` | Historical v1 and phishing comparisons; retained independently of v2 |
| `results[]` | Filterable ledger rows |
| `campaigns[]` | Timeline verdicts |

Every comparison row's `modelKey` must match a `results[].model` exactly.
v3 and v2 rows carry `sourceJson` and `suiteHash` tied to their measured artifacts;
ledger rows also carry `datasetVersion` (3 for `system1`, 2 for `system1-v2`). Each
page excludes rows whose version or hash does not match its board. v2 runs were
recorded under the suite name `system1`; the ledger labels them `system1-v2`. Historical ledger rows originally
used the name `system1`; the site labels them `system1-legacy` and version 1
without changing the underlying results. Never carry a v1 score into the v2 chart.

The v2 chart shades the leader's measured 95% accuracy interval. The historical
charts retain their approximate 8-point noise band. Response count and wall-clock
captions come from the selected version; 2 samples mean 800 responses on v2,
and 98 on v1. The current report discloses three open questions that the gateway's
64-candidate cap made unwinnable for both models; keep this caveat beside the scores.

The ledger's dot plot, the *Thinking OFF → ON* chart and the *Live vs isolated*
chart are derived from `results[]` at load time — no extra fields. A pair is two
rows identical except for `thinking` (or `mode`) **and** sharing a report folder
(one campaign); a side with two candidate rows is skipped rather than guessed.

## Model visibility

The searchable **Show / hide models** checklists on a page share one selection. Unchecking a
model hides all of that page's ledger runs for it, strip-plot dots, System One/phishing
comparison rows, and derived thinking/live comparison pairs. Curated rows use explicit
`modelKey` values so labels such as “Jev · typesafe arm” follow the same selection as their
ledger model.

Search only narrows checklist choices; **Show all** and **Hide all** affect the
page's entire model inventory, regardless of search or the other filters. Reset and the
empty-table Clear filters button restore every model and clear searches. Choices are
page-local, not persisted, and page-local in scope: a model hidden on the LLM page is still
shown on the System One page. Recommendation cards and fixed harness/thinking
examples are intentionally unaffected. Derived comparisons follow model
visibility, not the ledger's other filters; pairs are formed before filtering so
hidden models cannot turn ambiguous candidates into valid comparisons.

Do not label an accuracy interval as an F1 interval: a missing `ci` is omitted
from the phishing row. Link the completed, error-free result, not an interrupted
or throttled run, and disclose any rate-limit waiting in latency measurements.

Link paths are repo-relative and rendered against
`https://github.com/luongnv89/m-bench/blob/main/…` (paths ending in `/` use
`tree/main/` instead). A path only resolves once that result is committed to `main`.
