-- =============================================================================
-- 04_resource_monitor.sql
-- Caps monthly credit burn on the trial account. This alone is worth
-- mentioning in interviews — it shows you think about cost governance,
-- not just "can I make the query run".
-- =============================================================================

USE ROLE ACCOUNTADMIN;

CREATE RESOURCE MONITOR IF NOT EXISTS NG_FLOOD_MONITOR
    WITH
        CREDIT_QUOTA = 25              -- adjust to taste against your $300 balance
        FREQUENCY = MONTHLY
        START_TIMESTAMP = IMMEDIATELY
        TRIGGERS
            ON 50 PERCENT DO NOTIFY
            ON 75 PERCENT DO NOTIFY
            ON 90 PERCENT DO SUSPEND
            ON 100 PERCENT DO SUSPEND_IMMEDIATE;

ALTER WAREHOUSE NG_FLOOD_WH SET RESOURCE_MONITOR = NG_FLOOD_MONITOR;
