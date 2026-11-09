-- =============================================================================
-- MARTS layer: final consumption tables. FLOOD_RISK_SCORE is populated by
-- snowpark/flood_risk_scoring.py (Snowpark job) — this file defines the
-- target table shape and a pure-SQL fallback (CREATE OR REPLACE ... AS SELECT)
-- so the pipeline works even without running Snowpark, e.g. for a quick demo.
-- =============================================================================

USE DATABASE NG_FLOOD_RISK;
USE SCHEMA MARTS;

CREATE TABLE IF NOT EXISTS FLOOD_RISK_SCORE (
    grid_cell_id           STRING PRIMARY KEY,
    state                  STRING,
    lga                    STRING,
    elevation_score        FLOAT,      -- normalized 0-1, higher = higher risk (lower elevation)
    water_proximity_score  FLOAT,      -- normalized 0-1, higher = closer to water
    rainfall_score         FLOAT,      -- normalized 0-1, higher = heavier rainfall
    land_use_score         FLOAT,      -- normalized 0-1, higher = more impervious surface
    historical_score       FLOAT,      -- normalized 0-1, higher = more/worse past flood events
    composite_risk_score   FLOAT,      -- weighted sum of the above
    risk_category          STRING,     -- 'low' / 'moderate' / 'high' / 'severe'
    computed_at            TIMESTAMP_NTZ
);

-- Pure-SQL fallback scoring (weights match snowpark/flood_risk_scoring.py —
-- keep both in sync, or delete this file once the Snowpark job is running
-- on a schedule via a Snowflake Task)
CREATE OR REPLACE TABLE FLOOD_RISK_SCORE AS
WITH normalized AS (
    SELECT
        g.grid_cell_id,
        g.state,
        g.lga,
        -- invert elevation: lower elevation -> higher risk
        1 - (e.elevation_m - MIN(e.elevation_m) OVER ()) /
            NULLIF(MAX(e.elevation_m) OVER () - MIN(e.elevation_m) OVER (), 0)  AS elevation_score,
        -- invert distance: closer to water -> higher risk
        1 - (w.nearest_water_distance_m - MIN(w.nearest_water_distance_m) OVER ()) /
            NULLIF(MAX(w.nearest_water_distance_m) OVER () - MIN(w.nearest_water_distance_m) OVER (), 0) AS water_proximity_score,
        (r.avg_rainfall_mm - MIN(r.avg_rainfall_mm) OVER ()) /
            NULLIF(MAX(r.avg_rainfall_mm) OVER () - MIN(r.avg_rainfall_mm) OVER (), 0) AS rainfall_score,
        COALESCE(l.impervious_pct, 0) / 100.0 AS land_use_score,
        LEAST(COALESCE(fh.historical_event_count, 0) / 5.0, 1.0) AS historical_score
    FROM CORE.DIM_GRID_CELL g
    LEFT JOIN CORE.FACT_ELEVATION e ON g.grid_cell_id = e.grid_cell_id
    LEFT JOIN CORE.FACT_WATER_PROXIMITY w ON g.grid_cell_id = w.grid_cell_id
    LEFT JOIN (
        SELECT grid_cell_id, AVG(avg_rainfall_mm) AS avg_rainfall_mm
        FROM CORE.FACT_RAINFALL_CLIMATOLOGY GROUP BY grid_cell_id
    ) r ON g.grid_cell_id = r.grid_cell_id
    LEFT JOIN CORE.FACT_LAND_USE l ON g.grid_cell_id = l.grid_cell_id
    LEFT JOIN CORE.FACT_FLOOD_HISTORY fh ON g.grid_cell_id = fh.grid_cell_id
)
SELECT
    grid_cell_id,
    state,
    lga,
    elevation_score,
    water_proximity_score,
    rainfall_score,
    land_use_score,
    historical_score,
    -- weights: elevation 25%, water proximity 25%, rainfall 20%, land use 15%, history 15%
    (0.25 * COALESCE(elevation_score, 0) +
     0.25 * COALESCE(water_proximity_score, 0) +
     0.20 * COALESCE(rainfall_score, 0) +
     0.15 * COALESCE(land_use_score, 0) +
     0.15 * COALESCE(historical_score, 0))               AS composite_risk_score,
    CASE
        WHEN composite_risk_score >= 0.75 THEN 'severe'
        WHEN composite_risk_score >= 0.5  THEN 'high'
        WHEN composite_risk_score >= 0.25 THEN 'moderate'
        ELSE 'low'
    END                                                    AS risk_category,
    CURRENT_TIMESTAMP()                                    AS computed_at
FROM normalized;

-- State-level rollup for the dashboard summary cards
CREATE OR REPLACE TABLE MART_STATE_SUMMARY AS
SELECT
    state,
    AVG(composite_risk_score)                                    AS avg_risk_score,
    COUNT_IF(risk_category IN ('high', 'severe')) / COUNT(*)::FLOAT AS pct_high_risk_cells,
    COUNT(*)                                                       AS total_cells
FROM FLOOD_RISK_SCORE
GROUP BY state;
