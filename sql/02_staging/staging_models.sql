-- =============================================================================
-- STAGING layer: flatten VARIANT payloads into typed rows with native
-- GEOGRAPHY columns. This is where Snowflake's geospatial functions
-- (ST_MAKEPOINT, TO_GEOGRAPHY, ST_DISTANCE) first show up.
--
-- Pattern: each table here is built as a view over RAW using LATERAL FLATTEN,
-- OR as a materialized table refreshed by a Snowflake Task. Shown as tables
-- for clarity; swap CREATE TABLE -> CREATE OR REPLACE TABLE ... AS SELECT
-- inside a Task for scheduled refresh.
-- =============================================================================

USE DATABASE NG_FLOOD_RISK;
USE SCHEMA STAGING;

-- ---------------------------------------------------------------------------
-- STG_ELEVATION: one row per sampled point, with elevation in meters
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE STG_ELEVATION AS
SELECT
    p.value:lat::FLOAT                                   AS latitude,
    p.value:lon::FLOAT                                   AS longitude,
    ST_MAKEPOINT(p.value:lon::FLOAT, p.value:lat::FLOAT)  AS geog,
    p.value:elevation::FLOAT                              AS elevation_m,
    r.source_api,
    r.loaded_at
FROM RAW.ELEVATION_RAW r,
     LATERAL FLATTEN(input => r.payload:results) p;

-- ---------------------------------------------------------------------------
-- STG_WATER_BODIES: one row per OSM way/node (river, lagoon, coastline)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE STG_WATER_BODIES AS
SELECT
    e.value:id::STRING                                    AS osm_id,
    e.value:tags:name::STRING                              AS water_name,
    e.value:tags:natural::STRING                            AS water_type,
    TO_GEOGRAPHY(e.value:geometry_geojson)                 AS geog,
    r.source_api,
    r.loaded_at
FROM RAW.WATER_BODIES_RAW r,
     LATERAL FLATTEN(input => r.payload:elements) e
WHERE e.value:geometry_geojson IS NOT NULL;

-- ---------------------------------------------------------------------------
-- STG_RAINFALL: daily rainfall per queried grid point, ready to aggregate
-- into monthly climatology in CORE
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE STG_RAINFALL AS
SELECT
    r.payload:latitude::FLOAT                              AS latitude,
    r.payload:longitude::FLOAT                              AS longitude,
    ST_MAKEPOINT(r.payload:longitude::FLOAT,
                 r.payload:latitude::FLOAT)                AS geog,
    d.value                                                 AS obs_date,
    p.value::FLOAT                                          AS rainfall_mm,
    r.source_api,
    r.loaded_at
FROM RAW.RAINFALL_RAW r,
     LATERAL FLATTEN(input => r.payload:daily:time) d,
     LATERAL FLATTEN(input => r.payload:daily:precipitation_sum) p
WHERE d.index = p.index;    -- align date <-> value by array position

-- ---------------------------------------------------------------------------
-- STG_LAND_USE: one row per classified polygon/cell
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE STG_LAND_USE AS
SELECT
    c.value:cell_id::STRING                                 AS source_cell_id,
    TO_GEOGRAPHY(c.value:geometry_geojson)                  AS geog,
    c.value:land_use_class::STRING                          AS land_use_class,
    c.value:impervious_pct::FLOAT                           AS impervious_pct,
    r.source_api,
    r.loaded_at
FROM RAW.LAND_USE_RAW r,
     LATERAL FLATTEN(input => r.payload:cells) c;

-- ---------------------------------------------------------------------------
-- STG_FLOOD_HISTORY: known historical flood events / extents
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE STG_FLOOD_HISTORY AS
SELECT
    e.value:event_id::STRING                                AS event_id,
    e.value:event_date::DATE                                AS event_date,
    e.value:severity::STRING                                AS severity,
    TO_GEOGRAPHY(e.value:extent_geojson)                    AS geog,
    r.source_api,
    r.loaded_at
FROM RAW.FLOOD_HISTORY_RAW r,
     LATERAL FLATTEN(input => r.payload:events) e;
