# m-bench docs (GitHub Pages)

Static landing page for measured benchmark results.

- `index.html` — self-contained UI (embedded CSS/JS)
- `data.json` — curated scores from `results/**` (regenerate when campaigns land)
- `assets/` — logo marks

## Serve locally

```bash
python3 -m http.server 8080 --directory docs
# open http://localhost:8080
```

`fetch("data.json")` requires HTTP — opening `index.html` via `file://` will fail.

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
| `systemOne` / `realUseCase` | Typed-decision and phishing comparisons, including measured latency and caveats; `modelKey` must match a `results[].model` exactly |
| `results[]` | Filterable ledger rows |
| `campaigns[]` | Timeline verdicts |

The ledger's dot plot, the *Thinking OFF → ON* chart and the *Live vs isolated*
chart are derived from `results[]` at load time — no extra fields. A pair is two
rows identical except for `thinking` (or `mode`) **and** sharing a report folder
(one campaign); a side with two candidate rows is skipped rather than guessed.

## Model visibility

The searchable **Show / hide models** checklists above System One and the full
ledger share one selection. Unchecking a model hides all of its ledger runs,
strip-plot dots, System One/phishing comparison rows, and derived thinking/live
comparison pairs. Curated rows use explicit `modelKey` values so labels such as
“Jev · typesafe arm” follow the same selection as their ledger model.

Search only narrows checklist choices; **Show all** and **Hide all** affect the
entire model inventory, regardless of search or the other filters. Reset and the
empty-table Clear filters button restore every model and clear searches. Choices
are page-local, not persisted. Recommendation cards and fixed harness/thinking
examples are intentionally unaffected. Derived comparisons follow model
visibility, not the ledger's other filters; pairs are formed before filtering so
hidden models cannot turn ambiguous candidates into valid comparisons.

Do not label an accuracy interval as an F1 interval: a missing `ci` is omitted
from the phishing row. Link the completed, error-free result, not an interrupted
or throttled run, and disclose any rate-limit waiting in latency measurements.

Link paths are repo-relative and rendered against
`https://github.com/luongnv89/m-bench/blob/main/…` (paths ending in `/` use
`tree/main/` instead). A path only resolves once that result is committed to `main`.
