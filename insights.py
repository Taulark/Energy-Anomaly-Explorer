"""
Insights and explanation engine for Energy Anomaly Explorer.
Provides deterministic explanations, pattern detection, and action recommendations.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime


def format_hour_12h(hour: int) -> str:
    """Convert 24-hour integer to 12-hour format string."""
    if hour == 0:
        return "12 AM"
    elif hour < 12:
        return f"{hour} AM"
    elif hour == 12:
        return "12 PM"
    else:
        return f"{hour - 12} PM"


def resolve_col(candidate: Union[str, List[str]], columns: pd.Index) -> Optional[str]:
    """
    Resolve a column name from a candidate (string or list of strings).
    
    Args:
        candidate: Column name (str) or list of candidate column names
        columns: pandas Index of available columns
    
    Returns:
        First matching column name if found, None otherwise
    """
    if isinstance(candidate, str):
        return candidate if candidate in columns else None
    elif isinstance(candidate, list):
        for col_name in candidate:
            if col_name in columns:
                return col_name
        return None
    return None


def compute_weather_baseline(df: pd.DataFrame, feature_map: Dict[str, any], month: int, hour: int) -> Dict[str, Tuple[float, float]]:
    """
    Compute baseline statistics (mean, std) for weather features at a specific month+hour.
    
    Args:
        df: Full merged dataset with weather columns
        feature_map: Mapping of canonical names to actual column names (str) or list of column name candidates
        month: Month (1-12)
        hour: Hour (0-23)
    
    Returns:
        Dict mapping feature names to (mean, std) tuples
    """
    baseline = {}
    
    # Filter to same month and hour across all years
    subset = df[(df['hour_datetime'].dt.month == month) & (df['hour_datetime'].dt.hour == hour)]
    
    if len(subset) == 0:
        return baseline
    
    for canonical, actual_col in feature_map.items():
        # Handle both str and list[str] for actual_col
        resolved_col = None
        if isinstance(actual_col, str):
            resolved_col = actual_col if actual_col in subset.columns else None
        elif isinstance(actual_col, list):
            # Find first matching column from the list
            for candidate in actual_col:
                if candidate in subset.columns:
                    resolved_col = candidate
                    break
        
        if resolved_col and resolved_col in subset.columns:
            values = subset[resolved_col].dropna()
            if len(values) > 0:
                baseline[canonical] = (values.mean(), values.std() if values.std() > 0 else 1.0)
    
    return baseline


def compute_weather_z_scores(df: pd.DataFrame, feature_map: Dict[str, any], anomaly_time: pd.Timestamp) -> Dict[str, float]:
    """
    Compute z-scores for weather features at anomaly time relative to baseline.
    
    Args:
        df: Full merged dataset
        feature_map: Feature column mapping (canonical -> str or list[str])
        anomaly_time: Timestamp of the anomaly
    
    Returns:
        Dict mapping feature names to z-scores
    """
    z_scores = {}
    
    if anomaly_time is pd.NaT:
        return z_scores
    
    month = anomaly_time.month
    hour = anomaly_time.hour
    
    baseline = compute_weather_baseline(df, feature_map, month, hour)
    
    # Get weather values at anomaly time
    anomaly_row = df[df['hour_datetime'] == anomaly_time]
    if len(anomaly_row) == 0:
        return z_scores
    
    for canonical, actual_col in feature_map.items():
        if canonical not in baseline:
            continue
        
        # Resolve column name (handle both str and list)
        resolved_col = None
        if isinstance(actual_col, str):
            resolved_col = actual_col if actual_col in anomaly_row.columns else None
        elif isinstance(actual_col, list):
            for candidate in actual_col:
                if candidate in anomaly_row.columns:
                    resolved_col = candidate
                    break
        
        if resolved_col and resolved_col in anomaly_row.columns:
            mean, std = baseline[canonical]
            value = anomaly_row[resolved_col].iloc[0]
            if pd.notna(value) and std > 0:
                z_scores[canonical] = (value - mean) / std
    
    return z_scores


def generate_anomaly_explanations(
    result_df: pd.DataFrame,
    df: pd.DataFrame,
    feature_map: Optional[Dict[str, str]],
    building_col: str,
    occupied_hours: Tuple[int, int] = (7, 19)
) -> pd.DataFrame:
    """
    Generate deterministic explanations for each anomaly row.
    
    Args:
        result_df: Anomaly detection results for a building (includes predicted, residual, z_score, abs_z, hour_datetime, anomaly)
        df: Full merged dataset with weather columns
        feature_map: Mapping of canonical feature names to actual column names
        building_col: Building column name
        occupied_hours: Tuple of (start_hour, end_hour) for occupied hours
    
    Returns:
        DataFrame with columns: explanation_summary, explanation_tags, recommended_actions, weather_context
    """
    # Filter to anomalies only
    anomalies = result_df[result_df['anomaly']].copy()
    
    if len(anomalies) == 0:
        return pd.DataFrame()
    
    explanations = []
    
    # Pre-compute weather baselines for efficiency
    weather_available = feature_map is not None and len(feature_map) > 0
    
    for idx, row in anomalies.iterrows():
        tags = []
        explanation_parts = []
        weather_context = ""
        
        hour_datetime = row['hour_datetime']
        residual = row['residual']
        abs_z = row['abs_z']
        predicted = row['predicted']
        # Use 'actual' column if present (from anomaly_df), otherwise try building_col or lookup from df
        if 'actual' in row.index:
            actual = row['actual']
        elif building_col in row.index:
            actual = row[building_col]
        else:
            # Fallback: try to lookup from df using hour_datetime
            try:
                if df is not None and 'hour_datetime' in df.columns and building_col in df.columns:
                    match = df[df['hour_datetime'] == hour_datetime]
                    if len(match) > 0:
                        actual = match[building_col].iloc[0]
                    else:
                        actual = predicted  # Fallback to predicted if no match
                else:
                    actual = predicted  # Final fallback
            except Exception:
                actual = predicted  # Final fallback
        
        if pd.isna(hour_datetime):
            explanations.append({
                'hour_datetime': hour_datetime,
                'explanation_summary': 'Invalid timestamp',
                'explanation_tags': 'Data quality issue',
                'recommended_actions': 'Check datetime column',
                'weather_context': ''
            })
            continue
        
        # Rule 1: Weather vs Internal classification
        if weather_available:
            weather_z_scores = compute_weather_z_scores(df, feature_map, hour_datetime)
            
            weather_unusual = False
            weather_details = []
            
            for feat_name, z_score in weather_z_scores.items():
                if abs(z_score) > 1.5:
                    weather_unusual = True
                    direction = "high" if z_score > 0 else "low"
                    weather_details.append(f"{feat_name} {direction}")
            
            if weather_unusual:
                weather_context = f"Weather unusual: {', '.join(weather_details)}"
                if abs(residual) > 0.5 * abs(predicted):
                    tags.append('Weather-driven')
                    explanation_parts.append("Unusual weather conditions")
                else:
                    tags.append('Operational / Internal')
                    explanation_parts.append("Internal operational issue despite weather")
            else:
                tags.append('Operational / Internal')
                explanation_parts.append("Normal weather, internal cause likely")
        else:
            weather_context = "Weather features unavailable"
            tags.append('Operational / Internal')
            explanation_parts.append("Weather data unavailable for analysis")
        
        # Rule 2: After-hours spike
        hour = hour_datetime.hour
        weekday = hour_datetime.weekday()  # 0=Monday, 6=Sunday
        
        if weekday < 5:  # Weekday
            if not (occupied_hours[0] <= hour < occupied_hours[1]):
                if residual > 0:
                    tags.append('After-hours spike')
                    explanation_parts.append("Energy spike outside occupied hours")
        else:  # Weekend
            tags.append('Weekend anomaly')
            explanation_parts.append("Anomaly occurred on weekend")
        
        # Rule 3: Sustained anomalies (check if next 2 hours are also anomalies)
        if idx < len(anomalies) - 1:
            next_idx = anomalies.index[anomalies.index.get_loc(idx) + 1] if anomalies.index.get_loc(idx) < len(anomalies) - 1 else None
            if next_idx is not None:
                next_row = result_df.loc[next_idx]
                if next_row['anomaly']:
                    time_diff = (next_row['hour_datetime'] - hour_datetime).total_seconds() / 3600
                    if time_diff <= 2:  # Within 2 hours
                        tags.append('Sustained event')
                        explanation_parts.append("Part of sustained anomaly pattern")
        
        # Rule 4: Solar/Cloud mismatch (if Cloud_Type exists)
        if 'Cloud_Type' in df.columns and weather_available:
            anomaly_row = df[df['hour_datetime'] == hour_datetime]
            if len(anomaly_row) > 0:
                cloud_type = anomaly_row['Cloud_Type'].iloc[0]
                if feature_map and 'Clearsky GHI' in feature_map:
                    clearsky_col_candidate = feature_map['Clearsky GHI']
                    clearsky_col = resolve_col(clearsky_col_candidate, anomaly_row.columns)
                    if clearsky_col:
                        clearsky = anomaly_row[clearsky_col].iloc[0]
                        if pd.notna(clearsky) and pd.notna(cloud_type):
                            # Heavy cloud (typically > 6) but high clearsky GHI suggests mismatch
                            if cloud_type > 6 and clearsky > 500:
                                tags.append('Solar mismatch')
                                explanation_parts.append("Cloud type inconsistent with solar irradiance")
        
        # Rule 5: Extreme residual
        if abs_z > 3.5:
            tags.append('High severity')
            explanation_parts.append("Extremely high z-score indicates critical issue")
        elif abs_z > 2.5:
            tags.append('Moderate severity')
        
        # Rule 6: Seasonal patterns
        month = hour_datetime.month
        if month in [6, 7, 8]:  # Summer
            tags.append('Summer concentration')
        elif month in [12, 1, 2]:  # Winter
            tags.append('Winter heating signal')
        
        # Rule 7: Possible sensor/meter issue (very high residual with normal predicted)
        if abs(residual) > 2 * abs(predicted) and abs_z > 3.0:
            tags.append('Possible sensor/meter issue')
            explanation_parts.append("Unusually high residual suggests data quality concern")
        
        # Build summary
        if explanation_parts:
            explanation_summary = ". ".join(explanation_parts[:2])  # Max 2 parts
        else:
            explanation_summary = "Anomaly detected"
        
        # Get recommended actions
        recommended_actions = recommend_actions(tags)
        
        explanations.append({
            'hour_datetime': hour_datetime,
            'explanation_summary': explanation_summary,
            'explanation_tags': ', '.join(tags) if tags else 'General anomaly',
            'recommended_actions': '; '.join(recommended_actions) if recommended_actions else 'Review building operations',
            'weather_context': weather_context
        })
    
    return pd.DataFrame(explanations)


def recommend_actions(tags: List[str]) -> List[str]:
    """
    Map tags to actionable recommendations.
    
    Args:
        tags: List of explanation tags
    
    Returns:
        List of recommended actions
    """
    action_map = {
        'After-hours spike': 'Audit HVAC and BMS override schedules for after-hours operation',
        'Sustained event': 'Investigate equipment cycling faults (sustained anomaly detected)',
        'Weather-driven': 'Review cooling/heating capacity and demand response readiness',
        'Possible sensor/meter issue': 'Validate meter readings and sensor calibration',
        'Weekend anomaly': 'Review weekend shutdown schedules and occupancy assumptions',
        'Operational / Internal': 'Check equipment status and internal operational logs',
        'High severity': 'Immediate investigation required (critical anomaly severity)',
        'Solar mismatch': 'Verify solar irradiance sensors against cloud type data',
        'Summer concentration': 'Review cooling system capacity and summer setpoints',
        'Winter heating signal': 'Evaluate heating system efficiency and setpoint controls',
    }
    
    actions = []
    for tag in tags:
        if tag in action_map:
            action = action_map[tag]
            if action not in actions:  # Avoid duplicates
                actions.append(action)
    
    # Default action if none found
    if not actions:
        actions.append('Review building operations and schedules')
    
    return actions[:3]  # Max 3 actions


def detect_recurring_patterns(result_df: pd.DataFrame) -> Dict:
    """
    Detect recurring patterns in anomalies.
    
    Args:
        result_df: Anomaly detection results (includes hour_datetime, anomaly)
    
    Returns:
        Dict with pattern statistics
    """
    anomalies = result_df[result_df['anomaly']].copy()
    
    if len(anomalies) == 0:
        return {
            'hour_of_day_counts': {},
            'weekday_counts': {},
            'month_counts': {},
            'top_hours': [],
            'top_weekdays': [],
            'season_split': {'summer': 0, 'winter': 0, 'spring': 0, 'fall': 0}
        }
    
    # Extract temporal features
    anomalies['hour'] = anomalies['hour_datetime'].dt.hour
    anomalies['weekday'] = anomalies['hour_datetime'].dt.weekday  # 0=Monday
    anomalies['month'] = anomalies['hour_datetime'].dt.month
    
    # Count by hour of day
    hour_counts = anomalies['hour'].value_counts().sort_index()
    hour_of_day_counts = hour_counts.to_dict()
    
    # Count by weekday
    weekday_counts = anomalies['weekday'].value_counts().sort_index()
    weekday_counts_dict = weekday_counts.to_dict()
    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    weekday_counts_named = {weekday_names[k]: v for k, v in weekday_counts_dict.items()}
    
    # Count by month
    month_counts = anomalies['month'].value_counts().sort_index()
    month_counts_dict = month_counts.to_dict()
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    month_counts_named = {month_names[k-1]: v for k, v in month_counts_dict.items()}
    
    # Top hours (top 3)
    top_hours = hour_counts.nlargest(3).index.tolist()
    
    # Top weekdays (top 2)
    top_weekdays_idx = weekday_counts.nlargest(2).index.tolist()
    top_weekdays = [weekday_names[idx] for idx in top_weekdays_idx]
    
    # Season split
    summer_months = [6, 7, 8]
    winter_months = [12, 1, 2]
    spring_months = [3, 4, 5]
    fall_months = [9, 10, 11]
    
    summer_count = len(anomalies[anomalies['month'].isin(summer_months)])
    winter_count = len(anomalies[anomalies['month'].isin(winter_months)])
    spring_count = len(anomalies[anomalies['month'].isin(spring_months)])
    fall_count = len(anomalies[anomalies['month'].isin(fall_months)])
    total = len(anomalies)
    
    season_split = {
        'summer': (summer_count / total * 100) if total > 0 else 0,
        'winter': (winter_count / total * 100) if total > 0 else 0,
        'spring': (spring_count / total * 100) if total > 0 else 0,
        'fall': (fall_count / total * 100) if total > 0 else 0
    }
    
    return {
        'hour_of_day_counts': hour_of_day_counts,
        'weekday_counts': weekday_counts_named,
        'month_counts': month_counts_named,
        'top_hours': top_hours,
        'top_weekdays': top_weekdays,
        'season_split': season_split
    }


def generate_executive_summary(
    result_df: pd.DataFrame,
    building_col: str,
    selected_year: str,
    patterns: Dict,
    feature_map: Optional[Dict[str, str]]
) -> List[str]:
    """
    Generate heuristic executive summary bullet points.
    
    Args:
        result_df: Anomaly detection results
        building_col: Building column name
        selected_year: Selected year filter
        patterns: Pattern detection results
        feature_map: Feature mapping (for weather availability)
    
    Returns:
        List of summary bullet points
    """
    summary = []
    
    total_hours = len(result_df)
    anomaly_hours = result_df['anomaly'].sum()
    anomaly_rate = (anomaly_hours / total_hours * 100) if total_hours > 0 else 0
    
    # Bullet 1: Anomaly rate
    if anomaly_rate < 1:
        summary.append(f"✅ Low anomaly rate ({anomaly_rate:.2f}%) indicates stable operations")
    elif anomaly_rate < 5:
        summary.append(f"⚠️ Moderate anomaly rate ({anomaly_rate:.2f}%) suggests occasional operational issues")
    else:
        summary.append(f"🔴 High anomaly rate ({anomaly_rate:.2f}%) indicates significant operational concerns")
    
    # Bullet 2: Weather vs Internal (if weather available)
    if feature_map and len(feature_map) > 0:
        # Try to classify based on patterns
        if patterns.get('season_split', {}).get('summer', 0) > 40:
            summary.append("🌡️ Anomalies concentrated in summer months, likely weather-driven cooling issues")
        elif patterns.get('season_split', {}).get('winter', 0) > 40:
            summary.append("❄️ Anomalies concentrated in winter months, likely heating system related")
        else:
            summary.append("⚙️ Anomalies distributed across seasons, suggesting internal operational factors")
    else:
        summary.append("⚠️ Weather data unavailable; cannot determine weather vs internal classification")
    
    # Bullet 3: Time patterns
    if patterns.get('top_hours'):
        top_hour = patterns['top_hours'][0]
        if top_hour < 7 or top_hour >= 19:
            summary.append(f"🕐 Most anomalies occur during off-hours ({format_hour_12h(top_hour)}), check after-hours schedules")
        else:
            summary.append(f"🕐 Peak anomaly hour is {format_hour_12h(top_hour)}, review operations during this time")
    
    if patterns.get('top_weekdays'):
        if 'Saturday' in patterns['top_weekdays'] or 'Sunday' in patterns['top_weekdays']:
            summary.append("📅 Weekend anomalies detected; verify weekend shutdown procedures")
    
    # Bullet 4: Sustained events (if detectable from patterns)
    if patterns.get('season_split', {}).get('summer', 0) > 50:
        summary.append("📈 High summer concentration suggests recurring seasonal pattern")
    
    # Bullet 5: Severity
    avg_abs_z = result_df[result_df['anomaly']]['abs_z'].mean() if anomaly_hours > 0 else 0
    if avg_abs_z > 3.0:
        summary.append(f"🚨 High average severity (|Z|={avg_abs_z:.2f}) indicates critical issues requiring immediate attention")
    elif avg_abs_z > 2.5:
        summary.append(f"⚠️ Moderate severity (|Z|={avg_abs_z:.2f}) suggests systematic operational deviations")
    
    # Bullet 6: Suggested actions (top level)
    if anomaly_rate > 5:
        summary.append("💡 Recommended: Review building automation schedules and equipment cycling patterns")
    elif patterns.get('top_weekdays') and ('Saturday' in patterns['top_weekdays'] or 'Sunday' in patterns['top_weekdays']):
        summary.append("💡 Recommended: Audit weekend occupancy and HVAC override procedures")
    
    # Bullet 7: Year context
    if selected_year != "All":
        summary.append(f"📊 Analysis filtered to {selected_year}; patterns may differ across full dataset")
    
    return summary[:7]  # Max 7 bullets


def estimate_cost_impact(result_df: pd.DataFrame, building_col: str, rate_per_kwh: float = 0.12) -> Dict:
    """
    Estimate cost impact from anomalies.
    
    Args:
        result_df: Anomaly detection results (includes residual, anomaly)
        building_col: Building column name
        rate_per_kwh: Electricity rate in $/kWh
    
    Returns:
        Dict with cost estimates
    """
    anomalies = result_df[result_df['anomaly']].copy()
    
    if len(anomalies) == 0:
        return {
            'excess_kwh': 0,
            'avoided_kwh': 0,
            'estimated_cost': 0,
            'disclaimer': 'No anomalies detected'
        }
    
    # Excess = positive residuals (actual > predicted)
    excess = anomalies[anomalies['residual'] > 0]['residual'].sum()
    
    # Avoided = negative residuals (actual < predicted, but we care about magnitude)
    avoided = abs(anomalies[anomalies['residual'] < 0]['residual'].sum())
    
    estimated_cost = excess * rate_per_kwh
    
    return {
        'excess_kwh': excess,
        'avoided_kwh': avoided,
        'estimated_cost': estimated_cost,
        'disclaimer': 'Assumes load units ≈ kWh; treat as directional estimate only'
    }
