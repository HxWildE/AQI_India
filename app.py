"""
Streamlit Dashboard: AQI India Real-time Intelligence & Anomaly Detection.

Visualizes:
1. Real-time and historical air quality observations across Indian cities.
2. SQL-driven pollutant trends and distribution comparisons.
3. Scikit-learn Isolation Forest anomaly detection for unusual readings.
4. Data quality audit and quarantine log inspection.
"""

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

from aqi_pipeline.config import get_config, DEFAULT_INDIAN_CITIES
from aqi_pipeline.analytics import AQIAnalytics
from aqi_pipeline.anomaly import AQIAnomalyDetector
from aqi_pipeline.pipeline import AQIPipeline

# Page setup
st.set_page_config(
    page_title="AQI India - Intelligence & Anomaly Dashboard",
    page_icon="🌫️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished dark-mode aesthetic
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .metric-card {
        background: linear-gradient(135deg, #1e222d, #141720);
        border: 1px solid #2d3343;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .metric-title {
        color: #8b949e;
        font-size: 13px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-value {
        color: #f0f6fc;
        font-size: 28px;
        font-weight: 700;
        margin-top: 4px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        padding: 8px 16px;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=60)
def load_data():
    """Loads observations and runs anomaly detection."""
    analytics = AQIAnalytics()
    df = analytics.get_all_observations_df()
    quality = analytics.get_data_quality_report()
    summary = analytics.get_city_summary_metrics()

    if not df.empty:
        detector = AQIAnomalyDetector(contamination=0.15)
        df_scored = detector.detect_anomalies(df)
    else:
        df_scored = pd.DataFrame()

    return df_scored, quality, summary


# --- SIDEBAR CONTROLS ---
st.sidebar.image("https://img.icons8.com/fluency/96/air-quality.png", width=64)
st.sidebar.title("AQI India Pipeline")
st.sidebar.caption("End-to-End ETL, Analytics & ML Anomaly Detection")

st.sidebar.markdown("---")
st.sidebar.subheader("Pipeline Execution")

exec_mode = st.sidebar.selectbox("Ingestion Mode", ["Live API (Open-Meteo)", "Sanitized Fixtures"])
run_btn = st.sidebar.button("🚀 Run Pipeline Now", use_container_width=True)

if run_btn:
    mode_arg = "live" if "Live" in exec_mode else "fixture"
    with st.spinner(f"Executing ETL pipeline in {mode_arg.upper()} mode..."):
        try:
            cfg = get_config(execution_mode=mode_arg)
            pipe = AQIPipeline(cfg)
            res = pipe.run(mode=mode_arg)
            st.sidebar.success(f"Success! {res['records_accepted']} accepted, {res['records_inserted']} new, {res['records_updated']} updated.")
            st.cache_data.clear()
        except Exception as e:
            st.sidebar.error(f"Pipeline error: {e}")

st.sidebar.markdown("---")
st.sidebar.subheader("Filters")

# Load data
df_observations, quality_report, city_summary = load_data()

available_cities = sorted(df_observations["city"].unique()) if not df_observations.empty else list(DEFAULT_INDIAN_CITIES.keys())
selected_cities = st.sidebar.multiselect("Select Cities", options=available_cities, default=available_cities)


# --- MAIN HEADER ---
st.title("🌫️ India Air Quality: Real-Time Intelligence & Anomaly Dashboard")
st.caption("Monitoring urban air quality, particulate trends, and ML anomaly detection across major Indian metropolises.")

# --- TOP METRIC ROW ---
m1, m2, m3, m4 = st.columns(4)

total_obs = quality_report.get("accepted_observations", 0)
clean_rate = quality_report.get("clean_rate_percent", 100.0)
total_anomalies = int(df_observations["is_anomaly"].sum()) if not df_observations.empty else 0
highest_aqi = int(df_observations["provider_aqi"].max()) if not df_observations.empty and df_observations["provider_aqi"].notna().any() else 0

with m1:
    st.markdown(f'<div class="metric-card"><div class="metric-title">Clean Observations</div><div class="metric-value">{total_obs:,}</div></div>', unsafe_allow_html=True)
with m2:
    st.markdown(f'<div class="metric-card"><div class="metric-title">Data Quality Clean Rate</div><div class="metric-value">{clean_rate}%</div></div>', unsafe_allow_html=True)
with m3:
    st.markdown(f'<div class="metric-card"><div class="metric-title">Peak Recorded AQI</div><div class="metric-value">{highest_aqi}</div></div>', unsafe_allow_html=True)
with m4:
    st.markdown(f'<div class="metric-card"><div class="metric-title">ML Outliers Detected</div><div class="metric-value">{total_anomalies}</div></div>', unsafe_allow_html=True)

# Filter by selected cities
filtered_df = df_observations[df_observations["city"].isin(selected_cities)] if not df_observations.empty else pd.DataFrame()

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 City Observations & Map",
    "📈 SQL Trend Analysis",
    "🤖 Scikit-Learn Anomaly Detection",
    "🛡️ Data Quality & Quarantine",
])

# --- TAB 1: CITY OBSERVATIONS & MAP ---
with tab1:
    st.subheader("Geographic & Real-Time Air Quality Distribution")

    col_map, col_cards = st.columns([1.2, 1])

    with col_map:
        if not filtered_df.empty:
            map_data = filtered_df[["latitude", "longitude", "city", "provider_aqi"]].dropna().drop_duplicates(subset=["city"])
            st.map(map_data, latitude="latitude", longitude="longitude", size=25, zoom=4)
        else:
            st.info("No city coordinates available.")

    with col_cards:
        st.write("##### Latest City Metrics")
        if not city_summary.empty:
            st.dataframe(
                city_summary[city_summary["city"].isin(selected_cities)],
                column_config={
                    "city": "City",
                    "avg_pm2_5": "Avg PM2.5 (µg/m³)",
                    "avg_pm10": "Avg PM10 (µg/m³)",
                    "avg_aqi": "Avg AQI",
                    "max_aqi": "Max AQI",
                    "latest_timestamp": "Timestamp",
                },
                hide_index=True,
                use_container_width=True,
            )

    st.markdown("---")
    st.subheader("Temporal Trends (PM2.5 vs PM10)")

    if not filtered_df.empty:
        chart_data = filtered_df[["timestamp_local", "city", "pm2_5", "pm10"]].dropna()
        chart = alt.Chart(chart_data).mark_line(point=True).encode(
            x=alt.X("timestamp_local:T", title="Observation Time (IST)"),
            y=alt.Y("pm2_5:Q", title="PM2.5 Concentration (µg/m³)"),
            color=alt.Color("city:N", title="City"),
            tooltip=["city", "timestamp_local", "pm2_5", "pm10"],
        ).properties(height=320)
        st.altair_chart(chart, use_container_width=True)


# --- TAB 2: SQL TREND ANALYSIS ---
with tab2:
    st.subheader("Multi-Pollutant Aggregation & Correlation")

    c1, c2 = st.columns(2)

    with c1:
        st.write("##### City-by-City AQI Comparison (SQL Group By)")
        if not city_summary.empty:
            bar_chart = alt.Chart(city_summary).mark_bar(cornerRadius=4).encode(
                x=alt.X("avg_aqi:Q", title="Average AQI"),
                y=alt.Y("city:N", sort="-x", title="City"),
                color=alt.Color("avg_aqi:Q", scale=alt.Scale(scheme="redyellowgreen", reverse=True)),
                tooltip=["city", "avg_aqi", "max_aqi", "avg_pm2_5"],
            ).properties(height=300)
            st.altair_chart(bar_chart, use_container_width=True)

    with c2:
        st.write("##### PM2.5 / PM10 Ratio Distribution")
        analytics = AQIAnalytics()
        ratio_df = analytics.get_pm_ratio_analysis()
        if not ratio_df.empty:
            ratio_chart = alt.Chart(ratio_df).mark_circle(size=80).encode(
                x=alt.X("pm10:Q", title="PM10 (µg/m³)"),
                y=alt.Y("pm2_5:Q", title="PM2.5 (µg/m³)"),
                color=alt.Color("city:N", title="City"),
                tooltip=["city", "timestamp_local", "pm2_5", "pm10", "pm_ratio"],
            ).properties(height=300)
            st.altair_chart(ratio_chart, use_container_width=True)

    st.markdown("""
    > **Data Engineering Takeaway**: PM2.5 particles are a physical subset of PM10. Atmospheric ratios typically range between 0.4 and 0.8. A ratio $> 1.0$ violates physics and flags optical sensor baseline drift.
    """)


# --- TAB 3: SCIKIT-LEARN ANOMALY DETECTION ---
with tab3:
    st.subheader("🤖 Machine Learning Anomaly Detection (Isolation Forest)")
    st.markdown("""
    We use **Scikit-learn's `IsolationForest`** model across 6 simultaneous pollutant features (`pm2_5`, `pm10`, `carbon_monoxide`, `nitrogen_dioxide`, `sulphur_dioxide`, `ozone`).
    The model isolates anomalous atmospheric events and sensor malfunctions without requiring labeled historical training data.
    """)

    if not filtered_df.empty and "is_anomaly" in filtered_df.columns:
        sc1, sc2 = st.columns([1.5, 1])

        with sc1:
            st.write("##### Anomaly Scatter: Normal vs Unusual Readings")
            scatter = alt.Chart(filtered_df).mark_circle(size=90).encode(
                x=alt.X("pm10:Q", title="PM10 (µg/m³)"),
                y=alt.Y("pm2_5:Q", title="PM2.5 (µg/m³)"),
                color=alt.Color("is_anomaly:N", scale=alt.Scale(domain=[False, True], range=["#38bdf8", "#ef4444"]), title="Is Outlier"),
                tooltip=["city", "timestamp_local", "pm2_5", "pm10", "anomaly_score", "anomaly_reason"],
            ).properties(height=350)
            st.altair_chart(scatter, use_container_width=True)

        with sc2:
            st.write("##### Anomaly Detection Summary")
            st.metric("Total Flagged Readings", int(filtered_df["is_anomaly"].sum()))
            st.metric("Model Contamination Rate", "15%")
            st.metric("Features Inspected", "6 Pollutants")

        st.write("##### Flagged Unusual Observations")
        anomalies_only = filtered_df[filtered_df["is_anomaly"]][["city", "timestamp_local", "pm2_5", "pm10", "provider_aqi", "anomaly_score", "anomaly_reason"]]
        if not anomalies_only.empty:
            st.dataframe(anomalies_only, hide_index=True, use_container_width=True)
        else:
            st.success("No anomalies detected in selected cities. All readings align with expected multi-pollutant distributions.")


# --- TAB 4: DATA QUALITY & QUARANTINE ---
with tab4:
    st.subheader("🛡️ Data Quality Governance & Quarantine Table")
    st.markdown("""
    The pipeline implements a **Dead-Letter Quarantine Pattern**. Records with negative pollutant readings, extreme out-of-range anomalies, or corrupt timestamps are diverted to `aqi_quarantine` so pipeline runs do not crash.
    """)

    q1, q2 = st.columns([1, 1])

    with q1:
        st.write("##### Data Quality Audit Breakdown")
        reasons_list = quality_report.get("quarantine_reasons", [])
        if reasons_list:
            reasons_df = pd.DataFrame(reasons_list)
            st.dataframe(reasons_df, hide_index=True, use_container_width=True)
        else:
            st.info("No quarantined records recorded yet.")

    with q2:
        st.write("##### Recent Pipeline Execution Runs (Audit Trail)")
        with AQIAnalytics().loader.get_connection() as conn:
            runs_df = pd.read_sql_query("SELECT run_id, execution_mode, status, records_extracted, records_inserted, records_updated, elapsed_seconds, started_at FROM pipeline_runs ORDER BY started_at DESC LIMIT 10;", conn)
        st.dataframe(runs_df, hide_index=True, use_container_width=True)
