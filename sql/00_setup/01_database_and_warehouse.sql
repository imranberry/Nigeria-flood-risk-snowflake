-- =============================================================================
-- 01_database_and_warehouse.sql
-- Creates the database and a cost-conscious XS warehouse for the whole project.
-- =============================================================================

USE ROLE SYSADMIN;

CREATE WAREHOUSE IF NOT EXISTS NG_FLOOD_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60          -- suspend after 60s idle: critical for trial credit conservation
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'XS warehouse for Nigeria Flood Risk project — auto-suspends fast to conserve trial credits';

CREATE DATABASE IF NOT EXISTS NG_FLOOD_RISK
    COMMENT = 'Geospatial flood risk intelligence warehouse for Lagos + high-risk Nigerian states';

USE WAREHOUSE NG_FLOOD_WH;
USE DATABASE NG_FLOOD_RISK;
