import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import Optional


STRAVA_ORANGE = "#FC4C02"
PALETTE = px.colors.qualitative.Set2


def kpi_metric(label: str, value: str, delta: str = None):
    """Streamlit metric wrapper — call st.metric directly in pages."""
    return {"label": label, "value": value, "delta": delta}


def weekly_distance_bar(activities: list[dict]) -> go.Figure:
    df = pd.DataFrame(activities)
    if df.empty:
        return go.Figure()
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["week"] = df["start_date"].dt.to_period("W").dt.start_time
    weekly = df.groupby("week")["distance_m"].sum().reset_index()
    weekly["km"] = weekly["distance_m"] / 1000

    fig = go.Figure(go.Bar(
        x=weekly["week"], y=weekly["km"],
        marker_color=STRAVA_ORANGE,
        hovertemplate="%{x|%d %b}<br>%{y:.1f} km<extra></extra>",
    ))
    fig.update_layout(
        title="Distancia semanal (km)", xaxis_title=None, yaxis_title="km",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=40, b=20),
    )
    return fig


def monthly_distance_bar(activities: list[dict]) -> go.Figure:
    df = pd.DataFrame(activities)
    if df.empty:
        return go.Figure()
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["month"] = df["start_date"].dt.to_period("M").dt.start_time
    monthly = df.groupby("month")["distance_m"].sum().reset_index()
    monthly["km"] = monthly["distance_m"] / 1000

    fig = go.Figure(go.Bar(
        x=monthly["month"], y=monthly["km"],
        marker_color=STRAVA_ORANGE,
        hovertemplate="%{x|%b %Y}<br>%{y:.1f} km<extra></extra>",
    ))
    fig.update_layout(
        title="Distancia mensual (km)", xaxis_title=None, yaxis_title="km",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=40, b=20),
    )
    return fig


def zone_donut(zone_seconds: dict, title: str) -> go.Figure:
    labels = list(zone_seconds.keys())
    values = list(zone_seconds.values())
    if sum(values) == 0:
        return go.Figure()

    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.45,
        textinfo="label+percent",
        hovertemplate="%{label}<br>%{value:.0f}s<extra></extra>",
        marker_colors=PALETTE,
    ))
    fig.update_layout(
        title=title,
        showlegend=False,
        margin=dict(t=40, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def stream_line(time_s: list, values: list, title: str, y_label: str,
                rolling: int = None, color: str = STRAVA_ORANGE) -> go.Figure:
    minutes = [t / 60 for t in time_s]
    fig = go.Figure()

    if rolling and len(values) >= rolling:
        s = pd.Series(values).rolling(rolling, min_periods=1).mean()
        fig.add_trace(go.Scatter(
            x=minutes, y=s,
            mode="lines", name=f"Media {rolling}s",
            line=dict(color=color, width=2),
            hovertemplate="%{x:.1f}min — %{y:.0f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=minutes, y=values,
            mode="lines", name="Raw",
            line=dict(color=color, width=1, dash="dot"),
            opacity=0.3,
            hoverinfo="skip",
        ))
    else:
        fig.add_trace(go.Scatter(
            x=minutes, y=values,
            mode="lines", name=title,
            line=dict(color=color, width=2),
            hovertemplate="%{x:.1f}min — %{y:.0f}<extra></extra>",
        ))

    fig.update_layout(
        title=title, xaxis_title="Tiempo (min)", yaxis_title=y_label,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=40, b=20), showlegend=rolling is not None,
    )
    return fig


def elevation_area(time_s: list, altitude: list) -> go.Figure:
    minutes = [t / 60 for t in time_s]
    fig = go.Figure(go.Scatter(
        x=minutes, y=altitude,
        fill="tozeroy",
        line=dict(color="#8B7355", width=1.5),
        hovertemplate="%{x:.1f}min — %{y:.0f}m<extra></extra>",
    ))
    fig.update_layout(
        title="Perfil de elevación", xaxis_title="Tiempo (min)", yaxis_title="Altitud (m)",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=40, b=20),
    )
    return fig


def ftp_trend_line(activities: list[dict]) -> go.Figure:
    data = [(a["start_date"][:10], a.get("ftp_estimate")) for a in activities if a.get("ftp_estimate")]
    if not data:
        return go.Figure()
    data.sort()
    dates, ftps = zip(*data)
    fig = go.Figure(go.Scatter(
        x=dates, y=ftps,
        mode="lines+markers",
        line=dict(color=STRAVA_ORANGE, width=2),
        marker=dict(size=6),
        hovertemplate="%{x}<br>FTP est: %{y:.0f}W<extra></extra>",
    ))
    fig.update_layout(
        title="FTP estimado (tendencia)", xaxis_title=None, yaxis_title="Watts",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=40, b=20),
    )
    return fig


def ctl_atl_chart(dates: list, ctl: list, atl: list) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=ctl, mode="lines", name="CTL (Fitness)",
        line=dict(color="#2196F3", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=atl, mode="lines", name="ATL (Fatiga)",
        line=dict(color="#F44336", width=2),
    ))
    tsb = [c - a for c, a in zip(ctl, atl)]
    fig.add_trace(go.Scatter(
        x=dates, y=tsb, mode="lines", name="TSB (Forma)",
        line=dict(color="#4CAF50", width=1.5, dash="dot"),
    ))
    fig.update_layout(
        title="CTL / ATL / TSB", xaxis_title=None, yaxis_title="Puntos de entrenamiento",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=40, b=20),
    )
    return fig


def tss_weekly_bar(activities: list[dict]) -> go.Figure:
    rows = [(a["start_date"][:10], a.get("tss", 0) or 0) for a in activities]
    if not rows:
        return go.Figure()
    df = pd.DataFrame(rows, columns=["date", "tss"])
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"].dt.to_period("W").dt.start_time
    weekly = df.groupby("week")["tss"].sum().reset_index()

    fig = go.Figure(go.Bar(
        x=weekly["week"], y=weekly["tss"],
        marker_color="#7B61FF",
        hovertemplate="%{x|%d %b}<br>TSS: %{y:.0f}<extra></extra>",
    ))
    fig.update_layout(
        title="TSS semanal", xaxis_title=None, yaxis_title="TSS",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=40, b=20),
    )
    return fig
