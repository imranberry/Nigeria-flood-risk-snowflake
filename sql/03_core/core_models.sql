-- =============================================================================
-- CORE layer: dimensional model. DIM_GRID_CELL is the conformed grain that
-- every FACT_* table joins to, so elevation, water proximity, rainfall,
-- land use, and flood history all line up spatially for scoring.
--
-- DIM_GRID_CELL itself is populated by ingestion/generate_grid.py (built in
-- GeoPandas, then loaded via Snowpark — grid generation is easier in Python
-- than in SQL). This file defines the table shape + the FACT_* transforms
-- that read from STAGING.
-- =============================================================================

USE DATABASE NG_FLOOD_RISK;
USE SCHEMA CORE;

-- ---------------------------------------------------------------------------
-- DIM_GRID_CELL: ~1km analysis grid over Lagos + target high-risk states.
-- Loaded by ingestion/generate_grid.py — table declared here for reference.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS DIM_GRID_CELL (
    grid_cell_id     STRING PRIMARY KEY,
    geog             GEOGRAPHY,          -- cell polygon
    centroid_geog    GEOGRAPHY,          -- cell centroid point, used for distance joins
    state            STRING,
    lga              STRING,             -- Local Government Area
    created_at       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ---------------------------------------------------------------------------
-- FACT_ELEVATION: nearest elevation sample per grid cell
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE FACT_ELEVATION AS
SELECT
    g.grid_cell_id,
    e.elevation_m,
    ST_DISTANCE(g.centroid_geog, e.geog) AS sample_distance_m
FROM DIM_GRID_CELL g
JOIN STAGING.STG_ELEVATION e
  ON ST_DWITHIN(g.centroid_geog, e.geog, 2000)      -- consider samples within 2km
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY g.grid_cell_id ORDER BY sample_distance_m ASC
) = 1;

-- ---------------------------------------------------------------------------
-- FACT_WATER_PROXIMITY: distance from each grid cell to nearest water body
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE FACT_WATER_PROXIMITY AS
SELECT
    g.grid_cell_id,
    w.water_type,
    w.water_name,
    ST_DISTANCE(g.centroid_geog, w.geog) AS nearest_water_distance_m
FROM DIM_GRID_CELL g
JOIN STAGING.STG_WATER_BODIES w
  ON ST_DWITHIN(g.centroid_geog, w.geog, 15000)     -- search radius 15km
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY g.grid_cell_id ORDER BY nearest_water_distance_m ASC
) = 1;

-- ---------------------------------------------------------------------------
-- FACT_RAINFALL_CLIMATOLOGY: monthly avg/max rainfall per grid cell
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE FACT_RAINFALL_CLIMATOLOGY AS
SELECT
    g.grid_cell_id,
    MONTH(r.obs_date)          AS month,
    AVG(r.rainfall_mm)         AS avg_rainfall_mm,
    MAX(r.rainfall_mm)         AS max_rainfall_mm
FROM DIM_GRID_CELL g
JOIN STAGING.STG_RAINFALL r
  ON ST_DWITHIN(g.centroid_geog, r.geog, 5000)      -- nearest rainfall grid point within 5km
GROUP BY g.grid_cell_id, MONTH(r.obs_date);

-- ---------------------------------------------------------------------------
-- FACT_LAND_USE: dominant land-use class + imperviousness per grid cell
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE FACT_LAND_USE AS
SELECT
    g.grid_cell_id,
    l.land_use_class,
    l.impervious_pct
FROM DIM_GRID_CELL g
JOIN STAGING.STG_LAND_USE l
  ON ST_INTERSECTS(g.geog, l.geog)
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY g.grid_cell_id ORDER BY ST_AREA(ST_INTERSECTION(g.geog, l.geog)) DESC
) = 1;                                               -- keep the land-use class covering most of the cell

-- ---------------------------------------------------------------------------
-- FACT_FLOOD_HISTORY: historical flood event count + max severity per cell
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE FACT_FLOOD_HISTORY AS
SELECT
    g.grid_cell_id,
    COUNT(*)                                   AS historical_event_count,
    MAX(f.event_date)                          AS most_recent_event_date,
    MAX(CASE f.severity
            WHEN 'severe' THEN 3
            WHEN 'moderate' THEN 2
            WHEN 'minor' THEN 1
            ELSE 0 END)                        AS max_severity_rank
FROM DIM_GRID_CELL g
JOIN STAGING.STG_FLOOD_HISTORY f
  ON ST_INTERSECTS(g.geog, f.geog)
GROUP BY g.grid_cell_id;
