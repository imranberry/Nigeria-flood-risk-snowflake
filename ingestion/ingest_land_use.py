"""
Loads land-use classification per grid cell from ESA WorldCover (10m global
land cover) clipped to target states. WorldCover ships as raster (COG)
rather than a REST API, so this script rasterizes/samples locally with
rasterio + geopandas rather than making HTTP calls per cell, then lands
the result as VARIANT (same shape as the other RAW tables) for consistency
with the STAGING flatten pattern.

Requires: rasterio, geopandas
"""
import geopandas as gpd
import rasterio
from rasterio.mask import mask

from snowflake_utils import get_session, write_json_batch

# Download the relevant ESA WorldCover tile(s) for your target states first:
# https://esa-worldcover.org/en/data-access
WORLDCOVER_TIF_PATH = "data/esa_worldcover_lagos_2021.tif"

# WorldCover class codes -> simplified label + assumed imperviousness
LAND_USE_CLASS_MAP = {
    50: ("built_up", 0.85),
    10: ("tree_cover", 0.05),
    30: ("grassland", 0.10),
    40: ("cropland", 0.15),
    80: ("water", 0.0),
    90: ("wetland", 0.05),
}


def main():
    session = get_session()
    grid = load_grid_from_snowflake(session)

    with rasterio.open(WORLDCOVER_TIF_PATH) as src:
        cells = []
        for _, row in grid.iterrows():
            out_image, _ = mask(src, [row.geometry.__geo_interface__], crop=True)
            values, counts = _value_counts(out_image)
            dominant_class = values[counts.argmax()] if len(values) else None
            label, impervious_pct = LAND_USE_CLASS_MAP.get(dominant_class, ("unknown", 0.0))
            cells.append({
                "cell_id": row["grid_cell_id"],
                "geometry_geojson": row.geometry.__geo_interface__,
                "land_use_class": label,
                "impervious_pct": impervious_pct * 100,
            })

    write_json_batch(
        session,
        table="LAND_USE_RAW",
        source_api="esa_worldcover_2021",
        request_params={"tif": WORLDCOVER_TIF_PATH},
        payload={"cells": cells},
    )
    print(f"Loaded land use classification for {len(cells)} cells.")


def load_grid_from_snowflake(session):
    rows = session.sql("""
        SELECT grid_cell_id, ST_ASGEOJSON(geog) AS geojson
        FROM CORE.DIM_GRID_CELL
    """).collect()
    import json
    from shapely.geometry import shape
    return gpd.GeoDataFrame(
        [{"grid_cell_id": r["GRID_CELL_ID"], "geometry": shape(json.loads(r["GEOJSON"]))}
         for r in rows],
        crs="EPSG:4326",
    )


def _value_counts(arr):
    import numpy as np
    vals, counts = np.unique(arr[arr > 0], return_counts=True)
    return vals, counts


if __name__ == "__main__":
    main()
