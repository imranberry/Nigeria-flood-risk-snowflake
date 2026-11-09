"""
Snowpark Python scoring job: reads CORE.FACT_* tables, computes normalized
per-factor risk scores and a weighted composite score, and writes the result
to MARTS.FLOOD_RISK_SCORE.

This is the Snowpark-native counterpart to sql/04_marts/flood_risk_score.sql
(same weights, same logic) — kept as a proper Python job to demonstrate
DataFrame-API usage and so the weighting logic can carry unit tests and be
scheduled as a Snowflake Task running Python, not just SQL.

Run: python snowpark/flood_risk_scoring.py
Schedule: wrap in a Snowflake Task calling a Python stored procedure built
from this module (see docs/design_decisions.md for the deployment note).
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "ingestion"))
from snowflake_utils import get_session  # noqa: E402

from snowflake.snowpark import functions as F
from snowflake.snowpark import Window

WEIGHTS = {
    "elevation_score": 0.25,
    "water_proximity_score": 0.25,
    "rainfall_score": 0.20,
    "land_use_score": 0.15,
    "historical_score": 0.15,
}


def normalize(col, minmax_window):
    """Min-max normalize a column to [0, 1] over the given window."""
    col_min = F.min(col).over(minmax_window)
    col_max = F.max(col).over(minmax_window)
    return F.when(col_max == col_min, F.lit(0.0)) \
             .otherwise((col - col_min) / (col_max - col_min))


def build_scored_df(session):
    grid = session.table("CORE.DIM_GRID_CELL")
    elevation = session.table("CORE.FACT_ELEVATION")
    water = session.table("CORE.FACT_WATER_PROXIMITY")
    rainfall = (
        session.table("CORE.FACT_RAINFALL_CLIMATOLOGY")
        .group_by("grid_cell_id")
        .agg(F.avg("avg_rainfall_mm").alias("avg_rainfall_mm"))
    )
    land_use = session.table("CORE.FACT_LAND_USE")
    flood_history = session.table("CORE.FACT_FLOOD_HISTORY")

    df = (
        grid
        .join(elevation, "grid_cell_id", "left")
        .join(water, "grid_cell_id", "left")
        .join(rainfall, "grid_cell_id", "left")
        .join(land_use, "grid_cell_id", "left")
        .join(flood_history, "grid_cell_id", "left")
    )

    w = Window.partitionBy(F.lit(1))  # normalize across the whole dataset

    df = df.with_columns(
        ["elevation_score", "water_proximity_score", "rainfall_score",
         "land_use_score", "historical_score"],
        [
            # invert elevation: lower elevation => higher risk
            1 - normalize(F.col("elevation_m"), w),
            # invert distance to water: closer => higher risk
            1 - normalize(F.col("nearest_water_distance_m"), w),
            normalize(F.col("avg_rainfall_mm"), w),
            F.coalesce(F.col("impervious_pct"), F.lit(0)) / 100.0,
            F.least(F.coalesce(F.col("historical_event_count"), F.lit(0)) / F.lit(5.0), F.lit(1.0)),
        ],
    )

    composite = sum(
        F.coalesce(F.col(col), F.lit(0)) * weight
        for col, weight in WEIGHTS.items()
    )
    df = df.with_column("composite_risk_score", composite)

    df = df.with_column(
        "risk_category",
        F.when(F.col("composite_risk_score") >= 0.75, F.lit("severe"))
         .when(F.col("composite_risk_score") >= 0.50, F.lit("high"))
         .when(F.col("composite_risk_score") >= 0.25, F.lit("moderate"))
         .otherwise(F.lit("low")),
    )
    df = df.with_column("computed_at", F.current_timestamp())

    return df.select(
        "grid_cell_id", "state", "lga",
        "elevation_score", "water_proximity_score", "rainfall_score",
        "land_use_score", "historical_score",
        "composite_risk_score", "risk_category", "computed_at",
    )


def main():
    # Scoring reads CORE and writes MARTS, so it runs as the transformer role
    os.environ["SNOWFLAKE_ROLE"] = "NG_FLOOD_TRANSFORMER"
    session = get_session()
    session.sql("USE SCHEMA MARTS").collect()

    scored = build_scored_df(session)
    scored.write.mode("overwrite").save_as_table("MARTS.FLOOD_RISK_SCORE")

    summary = (
        session.table("MARTS.FLOOD_RISK_SCORE")
        .group_by("state")
        .agg(
            F.avg("composite_risk_score").alias("avg_risk_score"),
            (
                F.sum(
                    F.when(F.col("risk_category").isin(["high", "severe"]), 1).otherwise(0)
                )
                / F.count("*")
            ).alias("pct_high_risk_cells"),
            F.count("*").alias("total_cells"),
        )
    )
    summary.write.mode("overwrite").save_as_table("MARTS.MART_STATE_SUMMARY")

    total_cells = session.table("MARTS.FLOOD_RISK_SCORE").count()
    total_states = session.table("MARTS.MART_STATE_SUMMARY").count()
    print(f"Scored {total_cells} grid cells across {total_states} state(s). "
          f"Written to MARTS.FLOOD_RISK_SCORE.")


if __name__ == "__main__":
    main()