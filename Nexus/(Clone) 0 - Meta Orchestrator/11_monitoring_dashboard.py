# Databricks notebook source
# DBTITLE 1,Monitoring Dashboard
# MAGIC %md
# MAGIC # NEXUS Phase 11 — Real-Time Monitoring Dashboard (W0)
# MAGIC
# MAGIC **Purpose:** Live health view of all 80+ agents. SLA compliance, latency percentiles, throughput, error rates. Renders as rich HTML for quick visual assessment.

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,STEP 1: Compute Real-Time Health Metrics
# ======================================================================
# STEP 1 — REAL-TIME HEALTH METRICS
# ======================================================================

AGENT_NAME = "11_monitoring_dashboard"
run_id = generate_run_id()

# Platform-wide metrics
platform_health = spark.sql(f"""
    SELECT
        -- Registry health
        (SELECT COUNT(*) FROM {NEXUS_REGISTRY}) as total_agents,
        (SELECT COUNT_IF(status = 'ACTIVE') FROM {NEXUS_REGISTRY}) as active_agents,
        
        -- Circuit breaker health
        (SELECT COUNT_IF(state = 'CLOSED') FROM {NEXUS_CIRCUIT}) as healthy_breakers,
        (SELECT COUNT_IF(state = 'OPEN') FROM {NEXUS_CIRCUIT}) as open_breakers,
        (SELECT COUNT_IF(state = 'HALF_OPEN') FROM {NEXUS_CIRCUIT}) as halfopen_breakers,
        
        -- Event bus (1h)
        (SELECT COUNT(*) FROM {NEXUS_EVENTS} WHERE created_at >= DATEADD(HOUR, -1, CURRENT_TIMESTAMP())) as events_1h,
        (SELECT COUNT_IF(status = 'PUBLISHED') FROM {NEXUS_EVENTS} WHERE created_at >= DATEADD(HOUR, -24, CURRENT_TIMESTAMP())) as pending_events_24h,
        
        -- Agent performance
        (SELECT ROUND(AVG(success_rate) * 100, 1) FROM {NEXUS_REGISTRY} WHERE total_runs > 0) as avg_success_pct,
        (SELECT ROUND(AVG(avg_latency_ms), 0) FROM {NEXUS_REGISTRY} WHERE avg_latency_ms > 0) as avg_latency_ms
""").collect()[0]

# Per-workspace health
ws_health = spark.sql(f"""
    SELECT
        r.workspace,
        COUNT(*) as agents,
        ROUND(AVG(COALESCE(r.success_rate, 0)) * 100, 1) as avg_success_pct,
        SUM(r.total_runs) as total_runs,
        COUNT_IF(cb.state = 'OPEN') as open_breakers
    FROM {NEXUS_REGISTRY} r
    LEFT JOIN {NEXUS_CIRCUIT} cb ON r.agent_name = cb.agent_name
    GROUP BY r.workspace
    ORDER BY r.workspace
""").collect()

# COMMAND ----------

# DBTITLE 1,STEP 2: Render HTML Monitoring Dashboard
# ======================================================================
# STEP 2 — RENDER HTML MONITORING DASHBOARD
# ======================================================================

def kpi_box(label, value, unit="", color="#27AE60", icon=""):
    return (
        f'<div style="display:inline-block; width:160px; margin:8px; padding:16px; '
        f'background:#FAFBFC; border-radius:10px; border-left:4px solid {color}; text-align:center;">'
        f'<div style="font-size:11px; color:#7F8C8D; text-transform:uppercase; margin-bottom:4px;">{icon} {label}</div>'
        f'<div style="font-size:28px; font-weight:700; color:{color};">{value}{unit}</div>'
        f'</div>'
    )

# Icons as variables (avoid backslash in f-string)
ICON_GREEN = "\U0001f7e2"
ICON_YELLOW = "\U0001f7e1"
ICON_RED = "\U0001f534"
ICON_SATELLITE = "\U0001f4e1"
ICON_ROBOT = "\U0001f916"
ICON_CHECK = "\u2705"
ICON_CHART = "\U0001f4c8"
ICON_MAIL = "\U0001f4e8"
ICON_SHIELD = "\U0001f6e1"

# Health score
total_cb = platform_health['healthy_breakers'] + platform_health['open_breakers'] + platform_health['halfopen_breakers']
health_pct = round((platform_health['healthy_breakers'] / max(total_cb, 1)) * 100, 0)
health_color = '#27AE60' if health_pct >= 95 else '#F39C12' if health_pct >= 80 else '#E74C3C'
health_icon = ICON_GREEN if health_pct >= 95 else ICON_YELLOW if health_pct >= 80 else ICON_RED

# Workspace status rows
ws_rows = ""
ws_colors = {"W0": "#1B2A4A", "W1": "#27AE60", "W2": "#3498DB", "W3": "#8E44AD", "W4": "#E67E22"}
for ws in ws_health:
    ws_color = ws_colors.get(ws['workspace'], '#555')
    status_dot = ICON_GREEN if ws['open_breakers'] == 0 else ICON_RED
    ws_rows += (f"<tr><td><span style='color:{ws_color};font-weight:700;'>{ws['workspace']}</span></td>"
                f"<td>{ws['agents']}</td><td>{ws['avg_success_pct']}%</td>"
                f"<td>{ws['total_runs'] or 0}</td><td>{status_dot} {ws['open_breakers']} open</td></tr>")

timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
breaker_color = '#E74C3C' if platform_health['open_breakers'] > 0 else '#27AE60'
health_val = f"{health_pct:.0f}"

dashboard_html = (
    f'<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif; max-width:100%;">'
    f'<div style="background:linear-gradient(135deg,#1B2A4A,#2C3E50); color:white; padding:20px 24px; border-radius:12px 12px 0 0;">'
    f'<h2 style="margin:0; font-size:18px;">{ICON_SATELLITE} NEXUS MONITORING DASHBOARD</h2>'
    f'<p style="margin:4px 0 0; opacity:0.8; font-size:13px;">Generated: {timestamp}</p>'
    f'</div>'
    f'<div style="background:white; padding:20px; border:1px solid #E1E4E8; border-top:none;">'
    f'<h3 style="margin:0 0 12px; color:#1B2A4A;">Platform KPIs</h3>'
    + kpi_box('Health', health_val, '%', health_color, health_icon)
    + kpi_box('Agents', platform_health['total_agents'], '', '#1B2A4A', ICON_ROBOT)
    + kpi_box('Active', platform_health['active_agents'], '', '#27AE60', ICON_CHECK)
    + kpi_box('Success Rate', platform_health['avg_success_pct'] or 0, '%', '#3498DB', ICON_CHART)
    + kpi_box('Events/1h', platform_health['events_1h'], '', '#8E44AD', ICON_MAIL)
    + kpi_box('Open Breakers', platform_health['open_breakers'], '', breaker_color, ICON_SHIELD)
    + f'</div>'
    f'<div style="background:#FAFBFC; padding:20px; border:1px solid #E1E4E8; border-top:none; border-radius:0 0 12px 12px;">'
    f'<h3 style="margin:0 0 12px; color:#1B2A4A;">Workspace Status</h3>'
    f'<table style="width:100%; border-collapse:collapse; font-size:13px;">'
    f'<tr style="background:#1B2A4A; color:white;"><th style="padding:8px 12px;">WS</th><th>Agents</th><th>Success</th><th>Runs</th><th>Breakers</th></tr>'
    f'{ws_rows}'
    f'</table></div></div>'
)

displayHTML(dashboard_html)
print(f"{ICON_CHECK} Monitoring dashboard rendered | Health: {health_pct:.0f}%")