-- =============================================================================
-- 02_schemas.sql
-- Medallion-style layering: RAW -> STAGING -> CORE -> MARTS
-- =============================================================================

USE DATABASE NG_FLOOD_RISK;

CREATE SCHEMA IF NOT EXISTS RAW
    COMMENT = 'Landing zone. Minimal transformation. Semi-structured VARIANT payloads from source APIs.';

CREATE SCHEMA IF NOT EXISTS STAGING
    COMMENT = 'Typed, deduplicated, GEOGRAPHY-cast records. One row per source record. No business logic.';

CREATE SCHEMA IF NOT EXISTS CORE
    COMMENT = 'Dimensional model. DIM_GRID_CELL is the conformed grain; FACT_* tables join to it.';

CREATE SCHEMA IF NOT EXISTS MARTS
    COMMENT = 'Consumption layer. Flood risk scores and state-level rollups for the dashboard.';
