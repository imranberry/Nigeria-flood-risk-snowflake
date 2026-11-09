"""
Pulls historical daily rainfall (used to build monthly climatology in
CORE.FACT_RAINFALL_CLIMATOLOGY) from Open-Meteo's archive API for a
representative sample of grid points per state.

Resumable: checks RAW.INGESTION_PROGRESS before starting, skips any
grid_cell_id already loaded, and marks each point complete as it succeeds.
"""
import time
import requests
from snowflake_utils import (
    get_session, write_json_batch,
    get_completed_grid_cell_ids, mark_grid_cells_complete,
)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
START_DATE = "2015-01-01"
END_DATE = "2025-12-31"
SAMPLE_EVERY_NTH_CELL = 5
SOURCE_API = "open_meteo_archive"


def fetch_sample_points(session):
    rows = session.sql(f"""
        SELECT grid_cell_id,
               ST_Y(centroid_geog) AS lat,
               ST_X(centroid_geog) AS lon
        FROM CORE.DIM_GRID_CELL
        QUALIFY ROW_NUMBER() OVER (PARTITION BY state ORDER BY grid_cell_id)
                 % {SAMPLE_EVERY_NTH_CELL} = 0
    """).collect()
    return [(r["GRID_CELL_ID"], r["LAT"], r["LON"]) for r in rows]


def main():
    session = get_session()
    points = fetch_sample_points(session)

    done = get_completed_grid_cell_ids(session, SOURCE_API)
    remaining = [p for p in points if p[0] not in done]

    print(f"{len(points)} total sample points, {len(done)} already done, "
          f"{len(remaining)} remaining.")

    for grid_cell_id, lat, lon in remaining:
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": START_DATE,
            "end_date": END_DATE,
            "daily": "precipitation_sum",
            "timezone": "Africa/Lagos",
        }

        for attempt in range(5):
            resp = requests.get(ARCHIVE_URL, params=params, timeout=60)
            if resp.status_code == 429:
                wait = 2 ** attempt
                print(f"Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break

        write_json_batch(
            session,
            table="RAINFALL_RAW",
            source_api=SOURCE_API,
            request_params=params,
            payload=resp.json(),
        )
        mark_grid_cells_complete(session, SOURCE_API, [grid_cell_id])
        time.sleep(1.5)

    print("Rainfall ingestion complete.")


if __name__ == "__main__":
    main()