"""
Streamlit-in-Snowflake app: flood risk heatmap + state summary cards.

Deploy natively inside Snowflake (Snowsight -> Streamlit -> Create App,
point at this file) so there's zero separate hosting to manage — this alone
is worth calling out in a portfolio writeup, since most candidates host
Streamlit externally and never touch Snowflake's native app hosting.

Local run (against the same account, for development):
    streamlit run streamlit_app/app.py
"""
import streamlit as st
import pandas as pd
import pydeck as pdk
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="Nigeria Flood Risk", layout="wide")
st.title("Nigeria Flood Risk Intelligence")
st.caption("Composite flood risk score by ~1km grid cell — Lagos and high-risk states")

session = get_active_session()

# ---------------------------------------------------------------------------
# State-level summary cards
# ---------------------------------------------------------------------------
summary_df = session.table("MARTS.MART_STATE_SUMMARY").to_pandas()

cols = st.columns(len(summary_df))
for col, (_, row) in zip(cols, summary_df.iterrows()):
    col.metric(
        label=row["STATE"],
        value=f"{row['AVG_RISK_SCORE']:.2f}",
        delta=f"{row['PCT_HIGH_RISK_CELLS']*100:.0f}% high/severe cells",
        delta_color="inverse",
    )

st.divider()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
state_filter = st.selectbox(
    "State", options=["All"] + sorted(summary_df["STATE"].tolist())
)
risk_filter = st.multiselect(
    "Risk category", options=["low", "moderate", "high", "severe"],
    default=["moderate", "high", "severe"],
)

query = """
    SELECT grid_cell_id, state, lga,
           ST_Y(centroid_geog) AS lat, ST_X(centroid_geog) AS lon,
           composite_risk_score, risk_category
    FROM CORE.DIM_GRID_CELL g
    JOIN MARTS.FLOOD_RISK_SCORE s USING (grid_cell_id)
    WHERE 1=1
"""
if state_filter != "All":
    query += f" AND state = '{state_filter}'"
if risk_filter:
    cats = ", ".join(f"'{c}'" for c in risk_filter)
    query += f" AND risk_category IN ({cats})"

risk_df = session.sql(query).to_pandas()

# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------
RISK_COLORS = {
    "low": [34, 139, 34, 140],
    "moderate": [255, 215, 0, 160],
    "high": [255, 140, 0, 180],
    "severe": [220, 20, 60, 200],
}
risk_df["color"] = risk_df["RISK_CATEGORY"].map(RISK_COLORS)

layer = pdk.Layer(
    "ScatterplotLayer",
    data=risk_df,
    get_position=["LON", "LAT"],
    get_fill_color="color",
    get_radius=400,
    pickable=True,
)
view_state = pdk.ViewState(
    latitude=risk_df["LAT"].mean() if len(risk_df) else 6.5,
    longitude=risk_df["LON"].mean() if len(risk_df) else 3.4,
    zoom=9,
)
st.pydeck_chart(pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    tooltip={"text": "{GRID_CELL_ID}\nRisk: {RISK_CATEGORY} ({COMPOSITE_RISK_SCORE})"},
))

st.divider()
st.subheader("Highest-risk cells")
st.dataframe(
    risk_df.sort_values("COMPOSITE_RISK_SCORE", ascending=False).head(20),
    use_container_width=True,
)
