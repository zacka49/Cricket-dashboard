from __future__ import annotations

import json
from typing import Any

import plotly.graph_objects as go

from .advanced_models import GB_MODEL_NAME
from .database import Database
from .elo import MODEL_NAME as ELO_MODEL_NAME
from .logistic_model import MODEL_NAME as LOGISTIC_BASE_MODEL_NAME
from .logistic_model import POSTTOSS_MODEL_NAME, PRETOSS_MODEL_NAME
from .market import SYNTHETIC_MARKET_MODEL


FONT_FAMILY = "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"
INK = "#12181a"
MUTED = "#5c6b62"
LINE = "#dde4dc"
PANEL = "#ffffff"
PALETTE = ["#1f8f5f", "#2b6cb0", "#c98a2c", "#7c5cbf", "#0f9b8e", "#8a5a44"]
GOOD = "#1f8f5f"
BAD = "#c1443f"

COMPARISON_MODEL_NAMES = [
    ELO_MODEL_NAME,
    LOGISTIC_BASE_MODEL_NAME,
    PRETOSS_MODEL_NAME,
    POSTTOSS_MODEL_NAME,
    GB_MODEL_NAME,
    SYNTHETIC_MARKET_MODEL,
]


def _apply_theme(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(
        template=None,
        paper_bgcolor=PANEL,
        plot_bgcolor=PANEL,
        font=dict(family=FONT_FAMILY, color=INK, size=12),
        margin=dict(l=48, r=20, t=36, b=40),
        height=height,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=11)),
        hoverlabel=dict(bgcolor=PANEL, font=dict(family=FONT_FAMILY, color=INK)),
        colorway=PALETTE,
    )
    fig.update_xaxes(gridcolor=LINE, zerolinecolor=LINE, linecolor=LINE, tickfont=dict(color=MUTED, size=11))
    fig.update_yaxes(gridcolor=LINE, zerolinecolor=LINE, linecolor=LINE, tickfont=dict(color=MUTED, size=11))
    return fig


def _empty_chart(message: str) -> dict[str, Any]:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(color=MUTED, size=13),
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    _apply_theme(fig, height=220)
    return fig.to_plotly_json()


def build_model_comparison_chart(db: Database) -> dict[str, Any]:
    rows = [row for row in (_latest_model_metrics(db, name) for name in COMPARISON_MODEL_NAMES) if row]
    if not rows:
        return _empty_chart("No trained models yet. Train Elo, Logistic, and Quant Research models first.")

    labels = [f"{row['model_name']}<br><span style='font-size:10px'>({row['scope']})</span>" for row in rows]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Brier (lower=better)", x=labels, y=[row["brier"] for row in rows], marker_color=PALETTE[0]))
    fig.add_trace(go.Bar(name="Log loss (lower=better)", x=labels, y=[row["log_loss"] for row in rows], marker_color=PALETTE[1]))
    fig.add_trace(go.Bar(name="Accuracy (higher=better)", x=labels, y=[row["accuracy"] for row in rows], marker_color=PALETTE[2], yaxis="y2"))
    fig.update_layout(
        barmode="group",
        yaxis=dict(title="Brier / log loss"),
        yaxis2=dict(title="Accuracy", overlaying="y", side="right", tickformat=".0%", range=[0, 1]),
    )
    _apply_theme(fig, height=380)
    return fig.to_plotly_json()


def build_calibration_chart(db: Database) -> dict[str, Any]:
    active = db.query_one("SELECT model_name FROM model_registry WHERE active = 1 LIMIT 1")
    if not active:
        return _empty_chart("No active model set yet. Run Force Retrain Now to select one.")
    model_name = str(active["model_name"])
    payload = _latest_payload(db, model_name)
    if not payload:
        return _empty_chart(f"No stored calibration for {model_name} yet.")

    bins = None
    for key, value in (payload.get("calibration") or {}).items():
        if isinstance(value, list) and value:
            bins = value
            break
    if not bins:
        return _empty_chart(f"No calibration buckets recorded for {model_name}.")

    predicted = [float(b["avg_prediction"]) for b in bins]
    actual = [float(b["actual_rate"]) for b in bins]
    sizes = [int(b["n"]) for b in bins]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[0, 1], y=[0, 1], mode="lines", name="Perfect calibration",
            line=dict(color=MUTED, dash="dash", width=1.5), hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=predicted, y=actual, mode="lines+markers", name=model_name,
            marker=dict(size=[max(8, min(28, n / max(sizes) * 28)) for n in sizes], color=PALETTE[0]),
            line=dict(color=PALETTE[0]),
            customdata=sizes,
            hovertemplate="Predicted: %{x:.1%}<br>Actual: %{y:.1%}<br>N: %{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        xaxis=dict(title="Predicted probability", tickformat=".0%", range=[0, 1]),
        yaxis=dict(title="Actual win rate", tickformat=".0%", range=[0, 1]),
    )
    _apply_theme(fig)
    return fig.to_plotly_json()


def build_feature_importance_chart(db: Database) -> dict[str, Any]:
    active = db.query_one("SELECT model_name FROM model_registry WHERE active = 1 LIMIT 1")
    if not active:
        return _empty_chart("No active model set yet.")
    model_name = str(active["model_name"])
    payload = _latest_payload(db, model_name)
    if not payload:
        return _empty_chart(f"No stored metrics for {model_name} yet.")

    coefficients = [row for row in (payload.get("coefficients") or []) if row.get("feature") != "intercept"]
    if coefficients:
        coefficients = sorted(coefficients, key=lambda row: abs(float(row["weight"])))
        colors = [GOOD if float(row["weight"]) >= 0 else BAD for row in coefficients]
        fig = go.Figure(
            go.Bar(
                x=[float(row["weight"]) for row in coefficients],
                y=[str(row["feature"]) for row in coefficients],
                orientation="h",
                marker_color=colors,
            )
        )
        fig.update_layout(xaxis=dict(title="Standardized coefficient weight"), yaxis=dict(title=""))
        _apply_theme(fig, height=max(300, 28 * len(coefficients)))
        return fig.to_plotly_json()

    stumps = payload.get("top_stump_features") or []
    if stumps:
        stumps = sorted(stumps, key=lambda row: int(row["count"]))
        fig = go.Figure(
            go.Bar(
                x=[int(row["count"]) for row in stumps],
                y=[str(row["feature"]) for row in stumps],
                orientation="h",
                marker_color=PALETTE[0],
            )
        )
        fig.update_layout(xaxis=dict(title="Times used as a split feature"), yaxis=dict(title=""))
        _apply_theme(fig, height=max(300, 28 * len(stumps)))
        return fig.to_plotly_json()

    return _empty_chart(f"{model_name} has no feature-level breakdown available.")


def build_elo_ratings_chart(week1: dict[str, Any]) -> dict[str, Any]:
    ratings = ((week1 or {}).get("elo") or {}).get("payload", {}).get("top_ratings") or []
    if not ratings:
        return _empty_chart("No Elo ratings yet. Train Elo first.")
    ratings = sorted(ratings, key=lambda row: float(row["rating"]))
    fig = go.Figure(
        go.Bar(
            x=[float(row["rating"]) for row in ratings],
            y=[str(row["team"]) for row in ratings],
            orientation="h",
            marker_color=PALETTE[4],
        )
    )
    fig.update_layout(xaxis=dict(title="Elo rating"), yaxis=dict(title=""))
    _apply_theme(fig, height=max(300, 26 * len(ratings)))
    return fig.to_plotly_json()


def build_equity_curve_chart(paper_bets: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [bet for bet in (paper_bets or []) if bet.get("status") in ("settled", "cashed_out") and bet.get("closed_at")]
    if not closed:
        return _empty_chart("No settled paper bets yet. Run Morning, then Settle Paper once fixtures complete.")
    closed = sorted(closed, key=lambda bet: str(bet["closed_at"]))
    cumulative: list[float] = []
    running = 0.0
    for bet in closed:
        running += float(bet["pnl"])
        cumulative.append(round(running, 2))
    colors = [GOOD if value >= 0 else BAD for value in cumulative]
    fig = go.Figure()
    fig.add_hline(y=0, line_color=LINE, line_width=1)
    fig.add_trace(
        go.Scatter(
            x=[bet["closed_at"] for bet in closed],
            y=cumulative,
            mode="lines+markers",
            name="Cumulative P&L",
            line=dict(color=PALETTE[0]),
            marker=dict(color=colors, size=7),
            hovertemplate="%{x}<br>Cumulative P&L: %{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(xaxis=dict(title=""), yaxis=dict(title="Cumulative P&L (GBP)"))
    _apply_theme(fig)
    return fig.to_plotly_json()


def build_backtest_pnl_chart(backtesting: dict[str, Any]) -> dict[str, Any]:
    payload = (backtesting or {}).get("payload") or {}
    recent = payload.get("recent_bets") or []
    if not recent:
        return _empty_chart("No historical backtest bets yet. Run Rebuild Market Data after historical market baselines exist.")
    ordered = sorted(recent, key=lambda bet: (str(bet["match_date"]), str(bet["match_id"])))
    cumulative: list[float] = []
    running = 0.0
    for bet in ordered:
        running += float(bet["pnl"])
        cumulative.append(round(running, 2))
    colors = [GOOD if value >= 0 else BAD for value in cumulative]
    fig = go.Figure()
    fig.add_hline(y=0, line_color=LINE, line_width=1)
    fig.add_trace(
        go.Scatter(
            x=[bet["match_date"] for bet in ordered],
            y=cumulative,
            mode="lines+markers",
            name="Backtest cumulative P&L",
            line=dict(color=PALETTE[1]),
            marker=dict(color=colors, size=7),
            hovertemplate="%{x}<br>Cumulative P&L: %{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(xaxis=dict(title=""), yaxis=dict(title="Cumulative P&L (last 20 backtest bets)"))
    _apply_theme(fig)
    return fig.to_plotly_json()


def build_edge_bucket_chart(backtesting: dict[str, Any]) -> dict[str, Any]:
    payload = (backtesting or {}).get("payload") or {}
    buckets = payload.get("by_edge_bucket") or []
    if not buckets:
        return _empty_chart("No backtest edge-bucket breakdown yet.")
    order = {"3-5%": 0, "5-10%": 1, "10-15%": 2, "15%+": 3}
    buckets = sorted(buckets, key=lambda row: order.get(str(row["edge_bucket"]), 99))
    fig = go.Figure(
        go.Bar(
            x=[str(row["edge_bucket"]) for row in buckets],
            y=[float(row["roi"]) for row in buckets],
            marker_color=[GOOD if float(row["roi"]) >= 0 else BAD for row in buckets],
            customdata=[int(row["bets"]) for row in buckets],
            hovertemplate="Edge %{x}<br>ROI: %{y:.1%}<br>Bets: %{customdata}<extra></extra>",
        )
    )
    fig.update_layout(xaxis=dict(title="Model edge bucket"), yaxis=dict(title="ROI", tickformat=".0%"))
    _apply_theme(fig, height=300)
    return fig.to_plotly_json()


def build_all_charts(db: Database, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_comparison": build_model_comparison_chart(db),
        "calibration": build_calibration_chart(db),
        "feature_importance": build_feature_importance_chart(db),
        "elo_ratings": build_elo_ratings_chart(state.get("week1") or {}),
        "equity_curve": build_equity_curve_chart(state.get("paper_bets") or []),
        "backtest_pnl": build_backtest_pnl_chart(state.get("backtesting") or {}),
        "edge_bucket": build_edge_bucket_chart(state.get("backtesting") or {}),
    }


def _latest_payload(db: Database, model_name: str) -> dict[str, Any] | None:
    row = db.query_one(
        """
        SELECT payload_json
        FROM model_runs
        WHERE model_name = ?
        ORDER BY generated_at DESC, id DESC
        LIMIT 1
        """,
        (model_name,),
    )
    if not row:
        return None
    try:
        return json.loads(row["payload_json"])
    except json.JSONDecodeError:
        return None


def _latest_model_metrics(db: Database, model_name: str) -> dict[str, Any] | None:
    payload = _latest_payload(db, model_name)
    if not payload:
        return None
    splits = payload.get("splits")
    if isinstance(splits, dict) and splits.get("test"):
        test = splits["test"]
        return {
            "model_name": model_name,
            "brier": float(test.get("brier", 0)),
            "log_loss": float(test.get("log_loss", 0)),
            "accuracy": float(test.get("accuracy", 0)),
            "scope": "test split",
        }
    if "brier" in payload and "accuracy" in payload:
        return {
            "model_name": model_name,
            "brier": float(payload.get("brier", 0)),
            "log_loss": float(payload.get("log_loss", 0)),
            "accuracy": float(payload.get("accuracy", 0)),
            "scope": "all-time",
        }
    return None
