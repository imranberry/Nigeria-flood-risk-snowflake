# Design decisions

Short write-up of the choices behind this project — the kind of thing worth
pasting into a portfolio README or talking through in an interview.

## Why Snowflake-native geospatial instead of PostGIS

Most geospatial portfolio projects reach for PostGIS. Using Snowflake's
native `GEOGRAPHY` type and `ST_*` functions instead demonstrates a less
commonly shown skill (Snowflake geospatial is newer and less tutorialized),
and keeps the whole stack — storage, compute, transform, serving — inside
one platform, which is closer to how a real analytics team would evaluate
"can we do this without adding another system."

## Why a medallion (RAW → STAGING → CORE → MARTS) layout

- **RAW as VARIANT**: four unrelated source APIs (Open-Meteo, Overpass,
  WorldCover, flood history) each have their own schema and will drift.
  Landing the full response as `VARIANT` means ingestion never breaks on a
  field rename — only the STAGING flatten needs updating.
- **STAGING for typing + geometry**: this is the only layer that knows about
  source-specific JSON shapes. Everything downstream only ever sees typed
  columns and `GEOGRAPHY`.
- **CORE as a dimensional/star model**: `DIM_GRID_CELL` is the conformed
  grain; every `FACT_*` table is independently rebuildable from `STAGING`
  without touching the others. This is what makes it possible to re-run,
  say, only the rainfall ingestion after Open-Meteo API updates without
  reprocessing elevation.
- **MARTS as the only layer the dashboard touches**: `FLOOD_RISK_SCORE` and
  `MART_STATE_SUMMARY` are pre-aggregated so Streamlit never runs an
  expensive multi-join at page-load time.

## Why Snowpark for scoring instead of pure SQL

Both exist in this repo (`sql/04_marts/flood_risk_score.sql` and
`snowpark/flood_risk_scoring.py`) with matching weights. The SQL version is
a fast fallback; the Snowpark version is the one meant to run in production
because:
- weighting logic is easier to unit test as Python functions than as a wall
  of `CASE`/window-function SQL
- it can be packaged as a Python stored procedure and scheduled on a
  Snowflake Task, which is closer to how a real MLOps-adjacent pipeline
  would be run
- it's the clearer demonstration of Snowpark DataFrame API proficiency,
  which plain SQL doesn't show

## Why a fixed grid instead of H3 hexagons

H3 (Uber's hexagonal grid) is the more "correct" choice for production
geospatial analytics — equal-area cells, no edge distortion. A plain
lat/lon square grid was used here instead to keep the trial's compute and
complexity budget small and the grid-generation code (`generate_grid.py`)
readable in a portfolio review. Swapping to H3 is a natural "next step" to
mention if asked — Snowflake has native H3 functions (`H3_POINT_TO_CELL`,
etc.) that would replace `generate_grid.py` entirely.

## Cost governance

A resource monitor (`sql/00_setup/04_resource_monitor.sql`) caps monthly
credit burn and an XS warehouse auto-suspends after 60 seconds idle. This
was a deliberate design constraint, not an afterthought — worth mentioning
that the project was built to fit inside a fixed $300 trial budget and
stayed there.

## What's intentionally out of scope

- No ML model (this is a rule-based weighted score) — a natural v2 would
  train a model against `STG_FLOOD_HISTORY` as labels
- No orchestration beyond Snowflake Tasks — no Airflow/dbt, to keep the
  stack legible for a solo trial project
- No authentication/multi-tenant dashboard — single Streamlit-in-Snowflake
  app, matching the project's actual audience (portfolio reviewers)
