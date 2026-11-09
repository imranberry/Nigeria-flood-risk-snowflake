"""
Shared Snowflake session helper. Uses Snowpark so ingestion scripts and the
Snowpark scoring job share one connection pattern.

Credentials are read from environment variables (see .env.example) — never
hardcode them, and never commit a .env file.
"""
import json
import os

from dotenv import load_dotenv
from snowflake.snowpark import Session
from snowflake.snowpark.functions import parse_json, current_timestamp

load_dotenv()


def get_session() -> Session:
    connection_params = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "password": os.environ["SNOWFLAKE_PASSWORD"],
        "role": os.environ.get("SNOWFLAKE_ROLE", "NG_FLOOD_LOADER"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "NG_FLOOD_WH"),
        "database": os.environ.get("SNOWFLAKE_DATABASE", "NG_FLOOD_RISK"),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA", "RAW"),
    }
    return Session.builder.configs(connection_params).create()


def write_json_batch(session: Session, table: str, source_api: str,
                      request_params: dict, payload: dict) -> None:
    """
    Writes one raw API response as a single VARIANT row. Keeping ingestion
    at "one row per API call" (rather than flattening on write) means a
    malformed or partial response never blocks the load — parsing/validation
    happens downstream in STAGING where it's easy to re-run.
    """
    df = session.create_dataframe(
        [[source_api, json.dumps(request_params), json.dumps(payload)]],
        schema=["source_api", "request_params_str", "payload_str"],
    )
    df = df.select(
        df["source_api"],
        parse_json(df["request_params_str"]).alias("request_params"),
        parse_json(df["payload_str"]).alias("payload"),
        current_timestamp().alias("loaded_at"),
    )
    df.write.mode("append").save_as_table(f"RAW.{table}")


def get_completed_grid_cell_ids(session: Session, source_api: str) -> set:
    """Returns the set of grid_cell_ids already successfully ingested for this source."""
    rows = session.sql(f"""
        SELECT grid_cell_id FROM RAW.INGESTION_PROGRESS
        WHERE source_api = '{source_api}'
    """).collect()
    return {r["GRID_CELL_ID"] for r in rows}


def mark_grid_cells_complete(session: Session, source_api: str, grid_cell_ids: list) -> None:
    """Records grid_cell_ids as done so a rerun skips them."""
    if not grid_cell_ids:
        return
    rows = [(source_api, gid) for gid in grid_cell_ids]
    df = session.create_dataframe(rows, schema=["source_api", "grid_cell_id"])
    df.write.mode("append").save_as_table(
        "RAW.INGESTION_PROGRESS", column_order="name"
    )