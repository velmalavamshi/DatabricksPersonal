"""NEXUS Monitor — Request & Cost Dashboard for Hologic AI Agents Platform.

Queries system.billing.usage + system.billing.list_prices for real-time cost tracking,
and system.serving.served_model_inference_logs for request metrics.
"""

import os
import threading
import time
from datetime import datetime, timedelta

import gradio as gr
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from databricks import sql as dbsql
from databricks.sdk import WorkspaceClient

# --- Configuration ---
DARK_BLUE = "#1B2A4A"
RED = "#E74C3C"
GREEN = "#27AE60"
AMBER = "#F39C12"

# NEXUS-related identifiers
NEXUS_APP_NAME = "hologic-ai-agents"
NEXUS_SERVICE_PRINCIPAL_ID = "0c17cf9c-8bca-4464-a686-efe2887af896"
WORKSPACE_ID = "6617965257274108"

# SKUs relevant to NEXUS operations
NEXUS_SKUS = [
    "PREMIUM_SERVERLESS_REAL_TIME_INFERENCE_US_EAST_2",
    "PREMIUM_ANTHROPIC_MODEL_SERVING",
    "PREMIUM_SERVERLESS_SQL_COMPUTE_US_EAST_2",
    "PREMIUM_ALL_PURPOSE_SERVERLESS_COMPUTE_US_EAST_2",
    "PREMIUM_JOBS_SERVERLESS_COMPUTE_US_EAST_2",
]

# --- Database Connection ---
def get_connection():
    """Create a SQL warehouse connection using the app's service principal."""
    w = WorkspaceClient()
    warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID")
    if not warehouse_id:
        raise ValueError("DATABRICKS_WAREHOUSE_ID env var not set")
    return dbsql.connect(
        server_hostname=w.config.host.replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{warehouse_id}",
        credentials_provider=lambda: w.config._header_factory(),
    )


def run_query(query: str) -> pd.DataFrame:
    """Execute a query and return results as a DataFrame."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                return pd.DataFrame(rows, columns=columns)
    except Exception as e:
        return pd.DataFrame({"error": [str(e)]})


# --- Query Definitions ---
def get_daily_cost_query(days: int = 30) -> str:
    return f"""
    SELECT
        u.usage_date,
        u.sku_name,
        u.billing_origin_product,
        SUM(u.usage_quantity) AS dbus,
        ROUND(SUM(u.usage_quantity * lp.pricing.default), 2) AS cost_usd
    FROM system.billing.usage u
    JOIN system.billing.list_prices lp
        ON u.sku_name = lp.sku_name AND lp.price_end_time IS NULL
    WHERE u.usage_date >= DATEADD(DAY, -{days}, CURRENT_DATE())
      AND u.workspace_id = '{WORKSPACE_ID}'
      AND u.sku_name IN ({', '.join(f"'{s}'" for s in NEXUS_SKUS)})
    GROUP BY u.usage_date, u.sku_name, u.billing_origin_product
    ORDER BY u.usage_date DESC, cost_usd DESC
    """


def get_cost_summary_query(days: int = 30) -> str:
    return f"""
    SELECT
        u.sku_name,
        u.billing_origin_product,
        COUNT(DISTINCT u.usage_date) AS active_days,
        ROUND(SUM(u.usage_quantity), 2) AS total_dbus,
        ROUND(SUM(u.usage_quantity * lp.pricing.default), 2) AS total_cost_usd,
        ROUND(AVG(u.usage_quantity * lp.pricing.default), 4) AS avg_daily_cost_usd,
        ROUND(MAX(lp.pricing.default), 4) AS rate_per_dbu
    FROM system.billing.usage u
    JOIN system.billing.list_prices lp
        ON u.sku_name = lp.sku_name AND lp.price_end_time IS NULL
    WHERE u.usage_date >= DATEADD(DAY, -{days}, CURRENT_DATE())
      AND u.workspace_id = '{WORKSPACE_ID}'
      AND u.sku_name IN ({', '.join(f"'{s}'" for s in NEXUS_SKUS)})
    GROUP BY u.sku_name, u.billing_origin_product
    ORDER BY total_cost_usd DESC
    """


def get_endpoint_usage_query(days: int = 30) -> str:
    return f"""
    SELECT
        u.usage_date,
        u.usage_metadata.endpoint_name AS endpoint_name,
        u.sku_name,
        SUM(u.usage_quantity) AS dbus,
        ROUND(SUM(u.usage_quantity * lp.pricing.default), 2) AS cost_usd
    FROM system.billing.usage u
    JOIN system.billing.list_prices lp
        ON u.sku_name = lp.sku_name AND lp.price_end_time IS NULL
    WHERE u.usage_date >= DATEADD(DAY, -{days}, CURRENT_DATE())
      AND u.workspace_id = '{WORKSPACE_ID}'
      AND u.usage_metadata.endpoint_name IS NOT NULL
      AND u.sku_name IN ({', '.join(f"'{s}'" for s in NEXUS_SKUS)})
    GROUP BY u.usage_date, u.usage_metadata.endpoint_name, u.sku_name
    ORDER BY u.usage_date DESC, cost_usd DESC
    """


def get_inference_request_query(days: int = 7) -> str:
    """Query model serving inference logs for request counts."""
    return f"""
    SELECT
        DATE(timestamp_ms / 1000) AS request_date,
        request_metadata.endpoint_name AS endpoint_name,
        COUNT(*) AS request_count,
        ROUND(AVG(execution_duration_ms), 0) AS avg_latency_ms,
        ROUND(PERCENTILE(execution_duration_ms, 0.95), 0) AS p95_latency_ms,
        SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count,
        ROUND(SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS error_rate_pct
    FROM system.serving.served_model_inference_logs
    WHERE DATE(timestamp_ms / 1000) >= DATEADD(DAY, -{days}, CURRENT_DATE())
    GROUP BY DATE(timestamp_ms / 1000), request_metadata.endpoint_name
    ORDER BY request_date DESC, request_count DESC
    """


def get_hourly_pattern_query(days: int = 7) -> str:
    return f"""
    SELECT
        HOUR(FROM_UNIXTIME(timestamp_ms / 1000)) AS hour_of_day,
        COUNT(*) AS request_count,
        ROUND(AVG(execution_duration_ms), 0) AS avg_latency_ms
    FROM system.serving.served_model_inference_logs
    WHERE DATE(timestamp_ms / 1000) >= DATEADD(DAY, -{days}, CURRENT_DATE())
    GROUP BY HOUR(FROM_UNIXTIME(timestamp_ms / 1000))
    ORDER BY hour_of_day
    """


# --- Dashboard Components ---
def build_cost_overview(days: int = 30):
    """Build cost overview cards and charts."""
    summary_df = run_query(get_cost_summary_query(days))
    daily_df = run_query(get_daily_cost_query(days))

    if "error" in summary_df.columns:
        return f"Error: {summary_df['error'].iloc[0]}", None, None, None

    total_cost = summary_df["total_cost_usd"].sum() if not summary_df.empty else 0
    total_dbus = summary_df["total_dbus"].sum() if not summary_df.empty else 0
    annualized = total_cost * (365 / days)

    # KPI summary
    kpi_text = f"""
## NEXUS Cost Summary ({days}-Day Window)

| Metric | Value |
|--------|-------|
| **Total Cost** | ${total_cost:,.2f} |
| **Total DBUs** | {total_dbus:,.0f} |
| **Annualized** | ${annualized:,.0f}/year |
| **Avg Daily** | ${total_cost/max(days,1):,.2f}/day |
"""

    # Daily cost trend chart
    cost_trend_fig = None
    if not daily_df.empty:
        daily_df["usage_date"] = pd.to_datetime(daily_df["usage_date"])
        cost_trend_fig = px.area(
            daily_df,
            x="usage_date",
            y="cost_usd",
            color="sku_name",
            title=f"Daily NEXUS Cost by SKU ({days} Days)",
            labels={"usage_date": "Date", "cost_usd": "Cost (USD)", "sku_name": "SKU"},
        )
        cost_trend_fig.update_layout(
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=-0.3),
            height=400,
        )

    # Cost breakdown pie
    pie_fig = None
    if not summary_df.empty:
        pie_fig = px.pie(
            summary_df,
            values="total_cost_usd",
            names="billing_origin_product",
            title="Cost Distribution by Product",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        pie_fig.update_layout(height=350)

    return kpi_text, cost_trend_fig, pie_fig, summary_df


def build_request_metrics(days: int = 7):
    """Build request metrics from inference logs."""
    req_df = run_query(get_inference_request_query(days))
    hourly_df = run_query(get_hourly_pattern_query(days))

    if "error" in req_df.columns:
        return f"Error querying inference logs: {req_df['error'].iloc[0]}", None, None, None

    total_requests = req_df["request_count"].sum() if not req_df.empty else 0
    avg_latency = req_df["avg_latency_ms"].mean() if not req_df.empty else 0
    total_errors = req_df["error_count"].sum() if not req_df.empty else 0
    error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0

    kpi_text = f"""
## Request Metrics ({days}-Day Window)

| Metric | Value |
|--------|-------|
| **Total Requests** | {total_requests:,.0f} |
| **Avg Latency** | {avg_latency:,.0f} ms |
| **Error Count** | {total_errors:,.0f} |
| **Error Rate** | {error_rate:.2f}% |
"""

    # Requests over time
    req_trend_fig = None
    if not req_df.empty:
        req_df["request_date"] = pd.to_datetime(req_df["request_date"])
        daily_totals = req_df.groupby("request_date").agg(
            {"request_count": "sum", "avg_latency_ms": "mean", "error_count": "sum"}
        ).reset_index()

        req_trend_fig = go.Figure()
        req_trend_fig.add_trace(go.Bar(
            x=daily_totals["request_date"],
            y=daily_totals["request_count"],
            name="Requests",
            marker_color=DARK_BLUE,
        ))
        req_trend_fig.add_trace(go.Scatter(
            x=daily_totals["request_date"],
            y=daily_totals["avg_latency_ms"],
            name="Avg Latency (ms)",
            yaxis="y2",
            mode="lines+markers",
            marker_color=RED,
        ))
        req_trend_fig.update_layout(
            title=f"Daily Requests & Latency ({days} Days)",
            yaxis=dict(title="Request Count"),
            yaxis2=dict(title="Latency (ms)", overlaying="y", side="right"),
            template="plotly_white",
            height=400,
        )

    # Hourly pattern heatmap
    hourly_fig = None
    if not hourly_df.empty:
        hourly_fig = px.bar(
            hourly_df,
            x="hour_of_day",
            y="request_count",
            title="Request Volume by Hour of Day (UTC)",
            labels={"hour_of_day": "Hour (UTC)", "request_count": "Requests"},
            color="avg_latency_ms",
            color_continuous_scale="RdYlGn_r",
        )
        hourly_fig.update_layout(template="plotly_white", height=350)

    return kpi_text, req_trend_fig, hourly_fig, req_df


def build_endpoint_breakdown(days: int = 30):
    """Build per-endpoint cost breakdown."""
    ep_df = run_query(get_endpoint_usage_query(days))

    if "error" in ep_df.columns:
        return f"Error: {ep_df['error'].iloc[0]}", None, None

    if ep_df.empty:
        return "No endpoint-level usage found in the selected window.", None, None

    # Aggregate by endpoint
    ep_summary = ep_df.groupby("endpoint_name").agg(
        {"dbus": "sum", "cost_usd": "sum"}
    ).reset_index().sort_values("cost_usd", ascending=False)

    ep_fig = px.bar(
        ep_summary,
        x="endpoint_name",
        y="cost_usd",
        title=f"Cost by Endpoint ({days} Days)",
        labels={"endpoint_name": "Endpoint", "cost_usd": "Cost (USD)"},
        color="cost_usd",
        color_continuous_scale="Reds",
    )
    ep_fig.update_layout(template="plotly_white", height=400)

    # Daily by endpoint
    ep_df["usage_date"] = pd.to_datetime(ep_df["usage_date"])
    ep_daily_fig = px.line(
        ep_df.groupby(["usage_date", "endpoint_name"]).agg({"cost_usd": "sum"}).reset_index(),
        x="usage_date",
        y="cost_usd",
        color="endpoint_name",
        title="Daily Endpoint Cost Trend",
        labels={"usage_date": "Date", "cost_usd": "Cost (USD)"},
    )
    ep_daily_fig.update_layout(template="plotly_white", height=350)

    return ep_summary.to_markdown(index=False), ep_fig, ep_daily_fig


# --- Gradio UI ---
def refresh_cost(days):
    days = int(days)
    kpi, trend, pie, table = build_cost_overview(days)
    return kpi, trend, pie, table


def refresh_requests(days):
    days = int(days)
    kpi, trend, hourly, table = build_request_metrics(days)
    return kpi, trend, hourly, table


def refresh_endpoints(days):
    days = int(days)
    summary_md, bar_fig, daily_fig = build_endpoint_breakdown(days)
    return summary_md, bar_fig, daily_fig


with gr.Blocks(
    title="NEXUS Monitor",
    theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
    css=".gradio-container {max-width: 1400px !important}",
) as app:
    gr.Markdown(
        """# NEXUS Platform Monitor
        **Real-time cost and request monitoring for the Hologic AI Agents platform.**
        Data sourced from `system.billing.usage` + `system.billing.list_prices` (costs) and
        `system.serving.served_model_inference_logs` (requests).
        """
    )

    with gr.Tab("Cost Overview"):
        with gr.Row():
            cost_days = gr.Slider(minimum=7, maximum=90, value=30, step=1, label="Lookback (days)")
            cost_btn = gr.Button("Refresh", variant="primary")
        cost_kpi = gr.Markdown()
        with gr.Row():
            cost_trend_plot = gr.Plot(label="Daily Cost Trend")
            cost_pie_plot = gr.Plot(label="Cost Distribution")
        cost_table = gr.Dataframe(label="Cost Summary by SKU", interactive=False)
        cost_btn.click(
            refresh_cost, inputs=[cost_days], outputs=[cost_kpi, cost_trend_plot, cost_pie_plot, cost_table]
        )

    with gr.Tab("Request Metrics"):
        with gr.Row():
            req_days = gr.Slider(minimum=1, maximum=30, value=7, step=1, label="Lookback (days)")
            req_btn = gr.Button("Refresh", variant="primary")
        req_kpi = gr.Markdown()
        with gr.Row():
            req_trend_plot = gr.Plot(label="Requests & Latency")
            req_hourly_plot = gr.Plot(label="Hourly Pattern")
        req_table = gr.Dataframe(label="Request Details by Endpoint", interactive=False)
        req_btn.click(
            refresh_requests, inputs=[req_days], outputs=[req_kpi, req_trend_plot, req_hourly_plot, req_table]
        )

    with gr.Tab("Endpoint Breakdown"):
        with gr.Row():
            ep_days = gr.Slider(minimum=7, maximum=90, value=30, step=1, label="Lookback (days)")
            ep_btn = gr.Button("Refresh", variant="primary")
        ep_summary_md = gr.Markdown()
        with gr.Row():
            ep_bar_plot = gr.Plot(label="Cost by Endpoint")
            ep_daily_plot = gr.Plot(label="Daily Endpoint Trend")
        ep_btn.click(
            refresh_endpoints, inputs=[ep_days], outputs=[ep_summary_md, ep_bar_plot, ep_daily_plot]
        )

    # Auto-load on startup
    app.load(
        refresh_cost, inputs=[gr.Number(value=30, visible=False)], outputs=[cost_kpi, cost_trend_plot, cost_pie_plot, cost_table]
    )


if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=8000)
