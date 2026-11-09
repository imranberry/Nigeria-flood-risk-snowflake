-- =============================================================================
-- RAW layer: landing tables for each source. Payload kept as VARIANT so
-- ingestion never breaks on upstream API schema drift — parsing happens
-- downstream in STAGING where you control the contract.
-- =============================================================================

USE DATABASE NG_FLOOD_RISK;
USE SCHEMA RAW;

CREATE TABLE IF NOT EXISTS ELEVATION_RAW (
    source_api      STRING,          -- e.g. 'opentopography_srtm'
    request_params   VARIANT,         -- bbox / lat-lon requested
    payload          VARIANT,         -- raw API response
    loaded_at        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS WATER_BODIES_RAW (
    source_api      STRING,          -- 'osm_overpass'
    request_params   VARIANT,
    payload          VARIANT,         -- Overpass JSON (ways/nodes for rivers, lagoons, coastline)
    loaded_at        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS RAINFALL_RAW (
    source_api      STRING,          -- 'open_meteo_climate'
    request_params   VARIANT,
    payload          VARIANT,         -- daily/monthly rainfall series per station/grid point
    loaded_at        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS LAND_USE_RAW (
    source_api      STRING,          -- e.g. 'esa_worldcover' or local land-use dataset
    request_params   VARIANT,
    payload          VARIANT,
    loaded_at        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS FLOOD_HISTORY_RAW (
    source_api      STRING,          -- e.g. NEMA reports, NASA MODIS flood extents
    request_params   VARIANT,
    payload          VARIANT,
    loaded_at        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
