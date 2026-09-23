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
| `results[]` | Filterable ledger rows |
| `campaigns[]` | Timeline verdicts |

The ledger's dot plot, the *Thinking OFF → ON* chart and the *Live vs isolated*
chart are derived from `results[]` at load time — no extra fields. A pair is two
rows identical except for `thinking` (or `mode`) **and** sharing a report folder
(one campaign); a side with two candidate rows is skipped rather than guessed.

Link paths are repo-relative and rendered against
`https://github.com/luongnv89/m-bench/blob/main/…` (paths ending in `/` use
`tree/main/` instead). A path only resolves once that result is committed to `main`.
