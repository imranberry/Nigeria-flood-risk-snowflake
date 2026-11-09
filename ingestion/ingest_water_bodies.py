"""
Pulls rivers, lagoons, and coastline geometry from the OSM Overpass API for
each target state's bounding box, lands as VARIANT in RAW.WATER_BODIES_RAW.

Same pattern as ingest_elevation.py — see that file for the fuller walkthrough.
"""
import requests
from snowflake_utils import get_session, write_json_batch

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Bounding boxes (south, west, north, east) per target state — replace with
# real values pulled from your admin boundaries in generate_grid.py
STATE_BBOXES = {
    "Lagos": (6.35, 2.70, 6.70, 4.30),
}

OVERPASS_QUERY_TEMPLATE = """
[out:json][timeout:60];
(
  way["waterway"]({bbox});
  way["natural"="water"]({bbox});
  way["natural"="coastline"]({bbox});
);
out geom;
"""


def main():
    session = get_session()
    for state, bbox in STATE_BBOXES.items():
        bbox_str = ",".join(str(x) for x in bbox)
        query = OVERPASS_QUERY_TEMPLATE.format(bbox=bbox_str)
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=90)
        resp.raise_for_status()
        data = resp.json()

        # attach GeoJSON-style geometry per element so STAGING's
        # TO_GEOGRAPHY(e.value:geometry_geojson) can parse it directly
        for el in data.get("elements", []):
            if "geometry" in el:
                el["geometry_geojson"] = {
                    "type": "LineString",
                    "coordinates": [[pt["lon"], pt["lat"]] for pt in el["geometry"]],
                }

        write_json_batch(
            session,
            table="WATER_BODIES_RAW",
            source_api="osm_overpass",
            request_params={"state": state, "bbox": bbox_str},
            payload=data,
        )
        print(f"Loaded water bodies for {state}: {len(data.get('elements', []))} features")


if __name__ == "__main__":
    main()
