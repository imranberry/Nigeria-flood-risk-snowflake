"""
Pulls elevation samples for grid cell centroids from Open-Meteo's elevation
API and lands them as VARIANT payloads in RAW.ELEVATION_RAW.

Resumable: checks RAW.INGESTION_PROGRESS before starting, skips any
grid_cell_id already loaded, and marks each batch complete as it succeeds.
Safe to interrupt (Ctrl+C) and rerun — it picks up where it left off.
"""
import time
import requests
from snowflake_utils import (
    get_session, write_json_batch,
    get_completed_grid_cell_ids, mark_grid_cells_complete,
)

OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
BATCH_SIZE = 100
SOURCE_API = "open_meteo_elevation"


def fetch_centroids(session):
    rows = session.sql("""
        SELECT grid_cell_id,
               ST_Y(centroid_geog) AS lat,
               ST_X(centroid_geog) AS lon
        FROM CORE.DIM_GRID_CELL
    """).collect()
    return [(r["GRID_CELL_ID"], r["LAT"], r["LON"]) for r in rows]


def batched(iterable, n):
    for i in range(0, len(iterable), n):
        yield iterable[i:i + n]


def main():
    session = get_session()
    centroids = fetch_centroids(session)

    done = get_completed_grid_cell_ids(session, SOURCE_API)
    remaining = [c for c in centroids if c[0] not in done]

    print(f"{len(centroids)} total grid cells, {len(done)} already done, "
          f"{len(remaining)} remaining.")

    for batch in batched(remaining, BATCH_SIZE):
        ids, lats, lons = zip(*batch)
        params = {
            "latitude": ",".join(str(x) for x in lats),
            "longitude": ",".join(str(x) for x in lons),
        }

        for attempt in range(5):
            resp = requests.get(OPEN_METEO_ELEVATION_URL, params=params, timeout=30)
            if resp.status_code == 429:
                wait = 2 ** attempt
                print(f"Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break

        data = resp.json()
        time.sleep(6)

        if "elevation" not in data:
            print(f"Unexpected response, skipping batch: {data}")
            continue

        results = [
            {"lat": lat, "lon": lon, "elevation": elev}
            for lat, lon, elev in zip(lats, lons, data["elevation"])
        ]
        write_json_batch(
            session,
            table="ELEVATION_RAW",
            source_api=SOURCE_API,
            request_params=params,
            payload={"results": results},
        )
        mark_grid_cells_complete(session, SOURCE_API, list(ids))
        print(f"  done {len(ids)} cells")

    print("Elevation ingestion complete.")


if __name__ == "__main__":
    main()