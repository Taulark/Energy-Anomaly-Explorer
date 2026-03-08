"""
Occupancy and operating behavior insights based on load patterns and anomalies.
Heuristic-based, non-claiming, fully additive.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple


def _fmt12(hour: int) -> str:
    if hour == 0: return "12 AM"
    if hour < 12: return f"{hour} AM"
    if hour == 12: return "12 PM"
    return f"{hour - 12} PM"


def _hourly_profile(df: pd.DataFrame, building_col: str, weekday_only: bool = True) -> pd.Series:
    """Mean load by hour-of-day (weekdays only by default)."""
    tmp = df.dropna(subset=[building_col, 'hour_datetime']).copy()
    if len(tmp) == 0:
        return pd.Series(dtype=float)
    tmp['hour'] = tmp['hour_datetime'].dt.hour
    if weekday_only:
        tmp = tmp[tmp['hour_datetime'].dt.dayofweek < 5]
    if len(tmp) == 0:
        return pd.Series(dtype=float)
    return tmp.groupby('hour')[building_col].mean()


def generate_occupancy_insights(df: pd.DataFrame, anomaly_df: pd.DataFrame, building_col: str) -> Dict:
    """
    Generate data-driven operating behavior insights.

    Returns dict with keys: insights (List[str]), recommendations (List[str]),
    overall_confidence (str).
    """
    insights: List[str] = []
    recommendations: List[str] = []

    try:
        clean = df.dropna(subset=[building_col, 'hour_datetime']).copy()
        if len(clean) < 200:
            return {"insights": ["Insufficient data to infer operating behavior."],
                    "recommendations": [], "overall_confidence": "Low"}

        clean['hour'] = clean['hour_datetime'].dt.hour
        clean['weekday'] = clean['hour_datetime'].dt.dayofweek < 5
        clean['month'] = clean['hour_datetime'].dt.month

        weekday_profile = _hourly_profile(df, building_col, weekday_only=True)
        if len(weekday_profile) == 0:
            return {"insights": ["Insufficient weekday data."],
                    "recommendations": [], "overall_confidence": "Low"}

        # ── 1. Peak demand timing ──
        peak_hour = int(weekday_profile.idxmax())
        peak_load = weekday_profile.max()
        insights.append(
            f"Peak weekday demand typically occurs at {_fmt12(peak_hour)} "
            f"(avg {peak_load:,.1f} load units)."
        )

        # ── 2. Nighttime baseload ──
        night_hours = [0, 1, 2, 3, 4]
        night_vals = weekday_profile.reindex(night_hours).dropna()
        if len(night_vals) > 0 and peak_load > 0:
            night_avg = night_vals.mean()
            baseload_pct = night_avg / peak_load * 100
            if baseload_pct > 70:
                insights.append(
                    f"Nighttime baseload is {baseload_pct:.0f}% of peak — "
                    f"building rarely shuts down, large always-on load."
                )
                recommendations.append(
                    "Audit always-on equipment (chillers, servers, lighting) "
                    "for nighttime setback opportunities."
                )
            elif baseload_pct > 40:
                insights.append(
                    f"Nighttime baseload is {baseload_pct:.0f}% of peak — "
                    f"moderate overnight consumption."
                )
                recommendations.append(
                    "Review overnight HVAC schedules and plug loads for potential savings."
                )
            else:
                insights.append(
                    f"Nighttime baseload drops to {baseload_pct:.0f}% of peak — "
                    f"good evidence of shutdown procedures."
                )

        # ── 3. Weekend vs weekday ──
        weekday_mean = clean.loc[clean['weekday'], building_col].mean()
        weekend_mean = clean.loc[~clean['weekday'], building_col].mean()

        if weekday_mean > 0 and not pd.isna(weekend_mean):
            ratio = weekend_mean / weekday_mean

            if ratio > 0.90:
                insights.append(
                    f"Weekend load is {ratio:.0%} of weekday average — "
                    f"building operates near full capacity 7 days/week."
                )
            elif ratio > 0.50:
                insights.append(
                    f"Weekend load drops to {ratio:.0%} of weekday average, "
                    f"indicating partial weekend operations."
                )
                recommendations.append(
                    "Optimize weekend HVAC and lighting schedules for partial occupancy."
                )
            else:
                insights.append(
                    f"Weekend load drops to {ratio:.0%} of weekday average — "
                    f"good weekend shutdown practices in place."
                )

        # ── 4. Anomaly timing relative to load cycle ──
        anom = anomaly_df
        if 'anomaly' in anom.columns:
            anom = anom[anom['anomaly']].copy()

        if len(anom) > 0 and 'hour_datetime' in anom.columns:
            anom_hours = anom['hour_datetime'].dt.hour
            anom_hour_counts = anom_hours.value_counts()
            top_anom_hour = int(anom_hour_counts.idxmax())

            if abs(top_anom_hour - peak_hour) <= 1:
                insights.append(
                    f"Anomalies concentrate near peak demand ({_fmt12(top_anom_hour)}), "
                    f"suggesting capacity constraints during high-load periods."
                )
                recommendations.append(
                    f"Evaluate peak-hour capacity — anomalies cluster at "
                    f"{_fmt12(top_anom_hour)} when load is highest."
                )
            elif top_anom_hour < 7 or top_anom_hour >= 20:
                insights.append(
                    f"Anomalies concentrate during off-hours ({_fmt12(top_anom_hour)}), "
                    f"pointing to scheduling or equipment cycling issues."
                )
                recommendations.append(
                    "Investigate off-hours equipment schedules and BMS override logs."
                )
            else:
                period = "morning ramp-up" if top_anom_hour < peak_hour else "afternoon ramp-down"
                insights.append(
                    f"Anomalies peak at {_fmt12(top_anom_hour)} during the {period} period."
                )
                recommendations.append(
                    f"Review {period} equipment sequencing around {_fmt12(top_anom_hour)} "
                    f"for staging or scheduling issues."
                )

            # Weekend vs weekday anomaly split
            anom_weekday_pct = (anom['hour_datetime'].dt.dayofweek < 5).mean() * 100
            if anom_weekday_pct < 50:
                insights.append(
                    f"{100 - anom_weekday_pct:.0f}% of anomalies occur on weekends — "
                    f"weekend operations are a primary concern."
                )
                recommendations.append(
                    "Focus investigation on weekend equipment schedules and unplanned overrides."
                )

        # ── 5. Seasonal load variation ──
        season_map = {12: 'Winter', 1: 'Winter', 2: 'Winter',
                      3: 'Spring', 4: 'Spring', 5: 'Spring',
                      6: 'Summer', 7: 'Summer', 8: 'Summer',
                      9: 'Fall', 10: 'Fall', 11: 'Fall'}
        clean['season'] = clean['month'].map(season_map)
        seasonal_means = clean.groupby('season')[building_col].mean()

        if len(seasonal_means) >= 3:
            max_season = seasonal_means.idxmax()
            min_season = seasonal_means.idxmin()
            overall_mean = clean[building_col].mean()

            if overall_mean > 0:
                variation_pct = (seasonal_means.max() - seasonal_means.min()) / overall_mean * 100
                if variation_pct > 30:
                    insights.append(
                        f"Strong seasonal variation: {max_season} load is "
                        f"{variation_pct:.0f}% higher than {min_season}."
                    )
                    season_action = "cooling" if max_season == "Summer" else "heating" if max_season == "Winter" else "HVAC"
                    recommendations.append(
                        f"Schedule pre-{max_season.lower()} {season_action} system maintenance "
                        f"to handle the {variation_pct:.0f}% load increase."
                    )
                elif variation_pct > 10:
                    insights.append(
                        f"Moderate seasonal variation: {max_season} averages "
                        f"{seasonal_means.max():,.0f} vs {min_season} at "
                        f"{seasonal_means.min():,.0f}."
                    )
                else:
                    insights.append(
                        "Load is relatively stable across seasons — "
                        "limited weather-driven variation."
                    )

        return {
            "insights": insights[:6],
            "recommendations": recommendations[:4],
            "overall_confidence": "High" if len(clean) >= 5000 else "Medium" if len(clean) >= 1000 else "Low"
        }

    except Exception:
        return {
            "insights": ["Insufficient data to infer operating behavior."],
            "recommendations": [],
            "overall_confidence": "Low"
        }
