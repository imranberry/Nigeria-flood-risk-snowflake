"""
Builds a ~1km analysis grid over Lagos and other target high-risk states,
tags each cell with state/LGA via a spatial join against Nigeria admin
boundaries, and loads CORE.DIM_GRID_CELL.

Grid generation is done in GeoPandas rather than SQL because Snowflake has
no native "generate a polygon grid" primitive — this is the one step best
done client-side, then loaded once.

Requires: geopandas, shapely, requests (for admin boundary GeoJSON)
"""
import geopandas as gpd
import numpy as np
from shapely.geometry import box
import requests

from snowflake_utils import get_session

# Target states — start with Lagos, expand once the pipeline is proven
TARGET_STATES = ["Lagos"]

# Nigeria state boundaries (adjust source to whichever admin-boundary GeoJSON
# you have available, e.g. HDX Nigeria admin boundaries or GADM)
ADMIN_BOUNDARIES_URL = "C:\\Users\\Afolaji\\Downloads\\nigeria_states_enriched.geojson"

CELL_SIZE_DEG = 0.01  # ~1.1km at this latitude


def build_grid(bounds, cell_size=CELL_SIZE_DEG):
    minx, miny, maxx, maxy = bounds
    xs = np.arange(minx, maxx, cell_size)
    ys = np.arange(miny, maxy, cell_size)
    cells = [box(x, y, x + cell_size, y + cell_size) for x in xs for y in ys]
    return gpd.GeoDataFrame(geometry=cells, crs="EPSG:4326")


def main():
    admin = gpd.read_file(ADMIN_BOUNDARIES_URL)
    admin = admin[admin["name"].isin(TARGET_STATES)]

    all_cells = []
    for _, state_row in admin.iterrows():
        grid = build_grid(state_row.geometry.bounds)
        grid = grid[grid.intersects(state_row.geometry)]
        grid["name"] = state_row["name"]
        grid["lga"] = None  # optionally spatial-join against LGA boundaries too
        all_cells.append(grid)

    full_grid = gpd.GeoDataFrame(
        pd_concat_workaround(all_cells), crs="EPSG:4326"
    )
    full_grid["grid_cell_id"] = [
        f"{row.name}_{i}" for i, row in enumerate(full_grid.itertuples())
    ]
    full_grid["centroid"] = full_grid.geometry.centroid

    session = get_session()
    session.sql("USE SCHEMA CORE").collect()

    rows = [
        (
            r.grid_cell_id,
            r.geometry.wkt,
            r.centroid.wkt,
            r.name,
            r.lga,
        )
        for r in full_grid.itertuples()
    ]

    df = session.create_dataframe(
        rows, schema=["grid_cell_id", "geog_wkt", "centroid_wkt", "state", "lga"]
    )
    df.create_or_replace_temp_view("grid_stage")
    session.sql("""
        INSERT INTO DIM_GRID_CELL (grid_cell_id, geog, centroid_geog, state, lga)
        SELECT grid_cell_id, TO_GEOGRAPHY(geog_wkt), TO_GEOGRAPHY(centroid_wkt), state, lga
        FROM grid_stage
    """).collect()

    print(f"Loaded {len(rows)} grid cells across {len(TARGET_STATES)} states.")


def pd_concat_workaround(frames):
    import pandas as pd
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    main()
