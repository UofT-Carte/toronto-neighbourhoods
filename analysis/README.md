# Neighbourhood agreement analysis

Preliminary analysis of crowdsourced neighbourhood submissions across a
name-agreement × shape-agreement grid.

## Run (two commands)

```bash
node analysis/fetch_snapshot.mjs      # dumps analysis/data/snapshot-YYYY-MM-DD.json
uv run analysis/analyze.py            # writes analysis/out/report-YYYY-MM-DD.md + CSVs
```

The fetch needs application-default credentials for the Firebase project
(`gcloud auth application-default login`), same as the dashboard.

## Tuning

All thresholds are in the config block at the top of `analyze.py`
(`NAME_SIM_THRESHOLD`, `GRID_RES`, `MIN_MEMBERS`, `IOU_THRESHOLD`, area bounds).

## Tests

```bash
cd analysis && uv run pytest -q
```

## Output

- `out/report-*.md` — the human-readable report (Q1 consensus, Q2 contested
  boundaries + solid-core/fuzzy-edges, Q3 contested turf).
- `out/clusters-*.csv` — per-cluster shape metrics.
- `out/contested-*.csv` — cross-name overlap pairs.
