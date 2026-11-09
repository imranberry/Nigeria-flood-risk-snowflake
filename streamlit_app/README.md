# Nigeria Flood Risk Intelligence: Snowflake Geospatial Warehouse

A geospatial data warehouse and flood risk scoring pipeline for Lagos, Nigeria, built on Snowflake. It uses native `GEOGRAPHY` types and spatial SQL, Snowpark Python for scoring, and a Streamlit dashboard for the results.

> **Project status:** built during a Snowflake free trial that ended before the project was finished. The pipeline ran end to end for Lagos using **elevation and rainfall**. Code for three further factors (water proximity, land use, flood history) is included but those sources were **not ingested**, so they do not contribute to the scores. See [Status](#status) and [Next steps](#next-steps).

## What it does

1. Builds a ~1 km analysis grid over Lagos with GeoPandas and loads it to Snowflake.
2. Pulls elevation and 10 years of daily rainfall (2015-2025) from the Open-Meteo APIs into Snowflake as raw `VARIANT` payloads.
3. Flattens and types the raw data into staging tables with native `GEOGRAPHY` columns.
4. Joins everything onto the grid with spatial SQL to build a dimensional model.
5. Scores each grid cell with a Snowpark Python job and writes the results to a marts layer.
6. Serves the scores through a Streamlit app.

## Architecture

```
Open-Meteo APIs  -->  RAW  -->  STAGING  -->  CORE  -->  MARTS  -->  Streamlit
(elevation,          VARIANT   typed rows    grid-cell   risk       dashboard
 rainfall)           landing   + GEOGRAPHY   star schema scores
```

| Layer | Schema | Contents |
|-------|--------|----------|
| Landing | `RAW` | One `VARIANT` row per API response; `INGESTION_PROGRESS` tracks what has been loaded |
| Staging | `STAGING` | `STG_ELEVATION`, `STG_RAINFALL` (plus empty `STG_WATER_BODIES`, `STG_LAND_USE`, `STG_FLOOD_HISTORY`) |
| Core | `CORE` | `DIM_GRID_CELL` and `FACT_*` tables, all keyed on `grid_cell_id` |
| Marts | `MARTS` | `FLOOD_RISK_SCORE` (per cell), `MART_STATE_SUMMARY` (per state) |

More detail is in [`architecture/architecture.md`](architecture/architecture.md) and [`docs/design_decisions.md`](docs/design_decisions.md).

## Status

| Component | State |
|-----------|-------|
| Grid generation (Lagos, ~1 km cells) | Done: 3,211 scored cells |
| Elevation ingestion | Done |
| Rainfall ingestion | Done |
| STAGING and CORE models for elevation and rainfall | Done |
| Snowpark scoring job | Done, ran successfully |
| Streamlit dashboard |
| Water bodies (OSM Overpass), land use (ESA WorldCover), flood history | Scripts and SQL written |

## Technical highlights

- **Native Snowflake geospatial:** `GEOGRAPHY` columns, `ST_MAKEPOINT`, `ST_DWITHIN`, `ST_DISTANCE`, `ST_INTERSECTS`.
- **Resumable ingestion:** an `INGESTION_PROGRESS` table records each completed grid cell per source, so an interrupted run resumes where it stopped. Built after repeated rate-limit (HTTP 429), request-size (414 and 400) and network failures from the free API tier. Requests use exponential backoff.
- **Schema-drift-tolerant landing zone:** raw payloads are stored as `VARIANT` and parsed only in staging.
- **Query cost awareness:** the rainfall climatology aggregates daily data to monthly values per sample point before the spatial join, instead of joining about 3.8 million daily rows to the grid. Elevation was fetched at the grid centroids, so it joins on exact coordinates rather than a spatial search.
- **Missing-data handling:** the composite score uses only the factors that have data, with weights rescaled to sum to 1. Adding a factor is a one-line change.
- **Governance:** separate loader, transformer and reader roles; an XS warehouse with 60-second auto-suspend; a resource monitor capping credit use.

## Scoring method

Each factor is min-max normalised to 0-1 across the grid.

| Factor | Direction | Weight (full model) | Used in current run |
|--------|-----------|---------------------|---------------------|
| Elevation | lower = higher risk | 0.25 | yes |
| Rainfall | heavier = higher risk | 0.20 | yes |
| Water proximity | closer = higher risk | 0.25 | no data |
| Land use (impervious surface) | more = higher risk | 0.15 | no data |
| Flood history | more events = higher risk | 0.15 | no data |

With only two factors loaded, their weights are rescaled (0.25 and 0.20 become about 0.56 and 0.44).

**Limitations:**

- This is a rule-based relative score. It is **not** a validated flood probability and has not been checked against observed flood events.
- Scores reflect only elevation and rainfall at present.
- Rainfall comes from a sample of grid points and is assigned to each cell from the nearest point.

## Repository structure

```
.
├── architecture/        data flow and grain
├── docs/                design decisions
├── sql/
│   ├── 00_setup/        warehouse, database, schemas, roles, resource monitor
│   ├── 01_raw/          landing tables
│   ├── 02_staging/      typed + GEOGRAPHY models
│   ├── 03_core/         grid dimension and fact tables
│   └── 04_marts/        risk score tables
├── ingestion/           grid generation and API loaders
├── snowpark/            flood_risk_scoring.py
├── streamlit_app/       app.py
├── requirements.txt
└── .env.example
```

## Running it

You need a Snowflake account (a trial works) and Python 3.10+.

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in your account details. Never commit `.env`.
3. In Snowsight, run the files in `sql/00_setup/` in order, then `sql/01_raw/raw_tables.sql`. Create the progress table:
   ```sql
   CREATE TABLE IF NOT EXISTS RAW.INGESTION_PROGRESS (
       source_api STRING, grid_cell_id STRING,
       loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
       PRIMARY KEY (source_api, grid_cell_id));
   ```
4. Set `ADMIN_BOUNDARIES_URL` in `ingestion/generate_grid.py` to your Nigeria state boundaries GeoJSON and `TARGET_STATES` to `["Lagos"]`. Then, from `ingestion/`:
   ```
   python generate_grid.py
   python ingest_elevation.py
   python ingest_rainfall.py
   ```
5. Run `sql/02_staging/staging_models.sql`, then `sql/03_core/core_models.sql`, in Snowsight.
6. Grant the transformer role access to CORE, then score:
   ```
   python snowpark/flood_risk_scoring.py
   ```
7. Deploy `streamlit_app/app.py` as a Streamlit app in Snowsight.

The Open-Meteo free tier rate-limits aggressively. The loaders handle it, but expect the first run to take a while.

## Next steps

- Ingest water bodies (OSM Overpass), then land use (ESA WorldCover) and flood history, and add them to the `available` weights in the scoring job.
- Validate scores against documented flood events for Lagos.
- Move to H3 hexagonal cells (native Snowflake `H3_*` functions) for equal-area cells.
- Expand from Lagos to other high-risk states such as Bayelsa, Rivers and Delta.
- Schedule the pipeline with Snowflake Tasks.

## License

MIT
