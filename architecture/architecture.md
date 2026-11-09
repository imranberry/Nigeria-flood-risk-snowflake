# Architecture

## Data flow

```
┌────────────────────┐
│   Source APIs       │
│  - Open-Meteo        │  elevation, rainfall
│  - OSM Overpass       │  water bodies
│  - ESA WorldCover      │  land use (raster, sampled)
│  - Flood history        │  historical extents
└─────────┬────────────┘
          │  Python (requests / rasterio)
          ▼
┌─────────────────────┐
│   RAW schema          │  VARIANT landing tables, 1 row per API call
│  *_RAW                 │  no parsing, no business logic
└─────────┬────────────┘
          │  SQL: LATERAL FLATTEN + TO_GEOGRAPHY / ST_MAKEPOINT
          ▼
┌─────────────────────┐
│  STAGING schema        │  typed rows, native GEOGRAPHY columns
│  STG_*                  │  one row per source record
└─────────┬────────────┘
          │  SQL: ST_DWITHIN / ST_INTERSECTS spatial joins onto grid
          ▼
┌─────────────────────┐
│   CORE schema           │  DIM_GRID_CELL (conformed grain)
│  DIM_GRID_CELL           │  FACT_ELEVATION, FACT_WATER_PROXIMITY,
│  FACT_*                  │  FACT_RAINFALL_CLIMATOLOGY, FACT_LAND_USE,
│                           │  FACT_FLOOD_HISTORY
└─────────┬────────────┘
          │  Snowpark Python: normalize + weighted composite score
          ▼
┌─────────────────────┐
│   MARTS schema          │  FLOOD_RISK_SCORE (grid-cell grain)
│  FLOOD_RISK_SCORE        │  MART_STATE_SUMMARY (state grain)
│  MART_STATE_SUMMARY      │
└─────────┬────────────┘
          │  Streamlit-in-Snowflake (native, no external hosting)
          ▼
┌─────────────────────┐
│  Dashboard              │  risk heatmap + state summary cards
└─────────────────────┘
```

## Grain

The conformed grain across the whole warehouse is the **grid cell**
(`DIM_GRID_CELL`, ~1km² polygons covering Lagos and other target states).
Every fact table and the final risk score join back to `grid_cell_id`,
which is what makes the multi-source spatial join (elevation + water +
rainfall + land use + history, from four unrelated APIs with different
native geometries) tractable — everything gets projected onto the same
grid before scoring.

## Why grid cells instead of raw points/polygons

- Rainfall and elevation arrive as point samples, water bodies and flood
  history as lines/polygons, land use as raster — a common areal unit is
  the only way to join all five sources meaningfully.
- A fixed-size grid keeps the scoring model simple (average intersecting
  values into the cell) and keeps `FLOOD_RISK_SCORE` at a size Streamlit's
  `pydeck` layer can render directly, no separate tiling service needed.
- 1km resolution is enough for a state-level risk dashboard without
  generating a wasteful number of cells during a limited-credit trial.
