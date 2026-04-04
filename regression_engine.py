"""
Regression engine for dynamic feature selection and model fitting.
Supports ElasticNet-based feature selection and correlation-based fallback.
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import ElasticNetCV, ElasticNet
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')


# Feature mapping for candidate detection (similar to app.py FEATURE_MAP)
FEATURE_VARIANTS = {
    'Temperature': ['Temperature', 'temperature', 'temp', 'air_temperature', 'Air Temperature'],
    'Dew Point': ['Dew Point', 'DewPoint', 'dew_point', 'dew point', 'Dew Point Temperature'],
    'Clearsky GHI': ['Clearsky GHI', 'ClearskyGHI', 'clearsky_ghi', 'Clearsky GHI', 'GHI'],
    'Wind Speed': ['Wind Speed', 'WindSpeed', 'wind_speed', 'wind speed', 'Wind'],
    'Pressure': ['Pressure', 'pressure', 'surface_pressure', 'Surface Pressure', 'Pressure (Pa)'],
    'Cloud_Type': ['Cloud_Type', 'Cloud Type', 'CloudType', 'cloud_type', 'Cloud Type Code'],
}


def get_candidate_weather_features(
    df: pd.DataFrame, 
    y_col: str = None,
    exclude_cols: List[str] = None,
    building_cols: List[str] = None,
    missing_threshold: float = 5.0
) -> Dict:
    """
    Detects candidate weather features from the merged dataframe.
    Includes explicit known weather features AND auto-detects additional numeric weather columns.
    EXCLUDES building load columns, time columns, and target column.
    
    Args:
        df: Merged dataframe with weather columns
        y_col: Target column name (to exclude from candidates)
        exclude_cols: Additional columns to exclude (e.g., hour_datetime)
        building_cols: List of building load column names to exclude (REQUIRED to prevent including building columns)
        missing_threshold: Maximum missing percentage allowed (default 5%)
    
    Returns:
        Dict with:
            - feature_map: mapping canonical_name -> actual_column_name present in df
            - candidate_features: list of actual column names usable for regression (numeric, weather-only)
            - cloud_type_col: actual Cloud_Type column name if present, else None
    """
    if exclude_cols is None:
        exclude_cols = []
    if building_cols is None:
        building_cols = []
    
    # Build comprehensive exclusion set
    exclude_patterns = ['hour_datetime', 'Year', 'Month', 'Day', 'Hour', 'year', 'month', 'day', 'hour', 'datetime', 'date', 'time']
    exclude_cols_set = set(exclude_cols)
    
    # Add building columns to exclusions (CRITICAL: never include building loads as candidates)
    exclude_cols_set.update(building_cols)
    
    # Add y_col to exclusions if provided
    if y_col:
        exclude_cols_set.add(y_col)
    
    feature_map = {}
    candidates = []
    cloud_type_col = None
    candidate_set = set()  # Track to avoid duplicates
    
    # Step 1: Check for explicit known weather features
    for canonical, variants in FEATURE_VARIANTS.items():
        if canonical == 'Cloud_Type':
            # Handle Cloud_Type separately
            for variant in variants:
                if variant in df.columns and variant not in exclude_cols_set:
                    cloud_type_col = variant
                    break
        else:
            # Find matching column for numeric features
            for variant in variants:
                if variant in df.columns and variant not in exclude_cols_set:
                    # Check if numeric and not too many missing values
                    if pd.api.types.is_numeric_dtype(df[variant]):
                        missing_pct = df[variant].isna().sum() / len(df) * 100
                        if missing_pct < missing_threshold:
                            feature_map[canonical] = variant
                            if variant not in candidate_set:
                                candidates.append(variant)
                                candidate_set.add(variant)
                            break
    
    # Step 2: Auto-detect additional numeric weather columns
    # Exclude: target column, hour_datetime, Year/Month/Day/Hour, building load columns, non-numeric
    for col in df.columns:
        if col in exclude_cols_set:
            continue
        
        # Skip if matches exclusion patterns
        col_lower = col.lower()
        if any(pattern.lower() in col_lower for pattern in exclude_patterns):
            continue
        
        # Skip if already in candidates
        if col in candidate_set:
            continue
        
        # Skip Cloud_Type (handled separately)
        if col == cloud_type_col:
            continue
        
        # Check if numeric
        if pd.api.types.is_numeric_dtype(df[col]):
            missing_pct = df[col].isna().sum() / len(df) * 100
            if missing_pct < missing_threshold:
                # Only include if it's not a building column (double-check)
                if col not in building_cols:
                    candidates.append(col)
                    candidate_set.add(col)
    
    return {
        'feature_map': feature_map,
        'candidate_features': candidates,  # Changed key from 'candidates' to 'candidate_features'
        'cloud_type_col': cloud_type_col
    }


def select_weather_features(
    df: pd.DataFrame,
    y_col: str,
    feature_map: Dict[str, str],
    method: str = "elasticnet",
    top_k: int = 3,
    corr_threshold: float = 0.1,
    include_cloud_type: bool = False,
    hour_datetime_col: str = 'hour_datetime',
    missing_threshold: float = 5.0,
    building_cols: List[str] = None
) -> Dict:
    """
    Selects weather features for regression using ElasticNet or correlation.
    
    Args:
        df: Dataframe with features and target
        y_col: Target column name
        feature_map: Mapping of canonical names to actual column names
        method: "elasticnet" or "correlation"
        top_k: Number of top features to select (for correlation method)
        corr_threshold: Minimum |correlation| threshold
        include_cloud_type: If True, include Cloud_Type in candidates
        hour_datetime_col: Name of datetime column for chronological split
        missing_threshold: Maximum missing percentage allowed (default 5%)
        building_cols: List of building load column names to exclude
    
    Returns:
        Dict with:
            - method_used: str
            - selected_features: list of actual column names
            - candidate_features: list of all candidates considered
            - candidate_features_df: DataFrame with feature info (feature, missing_pct, corr_train, selected)
            - selection_diagnostics: dict with correlations/coefficients/notes
    """
    if building_cols is None:
        building_cols = []
    
    # Get candidate features (exclude y_col, hour_datetime, and building columns)
    candidate_info = get_candidate_weather_features(
        df, 
        y_col=y_col, 
        exclude_cols=[hour_datetime_col] if hour_datetime_col in df.columns else [],
        building_cols=building_cols,
        missing_threshold=missing_threshold
    )
    candidates = candidate_info.get('candidate_features', []).copy()
    cloud_type_col = candidate_info.get('cloud_type_col')
    
    # Add Cloud_Type if requested and available
    if include_cloud_type and cloud_type_col and cloud_type_col not in candidates:
        # Check missing rate for Cloud_Type
        missing_pct = df[cloud_type_col].isna().sum() / len(df) * 100
        if missing_pct < missing_threshold:
            candidates.append(cloud_type_col)
    
    if len(candidates) == 0:
        return {
            'method_used': 'none',
            'selected_features': [],
            'candidate_features': [],
            'candidate_features_df': pd.DataFrame(columns=['feature', 'missing_pct', 'corr_train', 'selected']),
            'selection_diagnostics': {'error': 'No candidate features found'}
        }
    
    # Prepare data - sort by hour_datetime first for deterministic split
    required_cols = [y_col] + candidates
    if hour_datetime_col in df.columns:
        required_cols.append(hour_datetime_col)
    
    data = df[required_cols].copy()
    
    # Sort by hour_datetime for deterministic processing
    if hour_datetime_col in data.columns:
        data = data.sort_values(hour_datetime_col).reset_index(drop=True)
    
    # Drop rows with missing values for regression
    data_clean = data.dropna()
    if len(data_clean) < 10:
        # Return empty candidate_features_df
        candidate_df = pd.DataFrame({
            'feature': candidates,
            'missing_pct': [df[c].isna().sum() / len(df) * 100 if c in df.columns else 100 for c in candidates],
            'corr_train': [0.0] * len(candidates),
            'selected': [''] * len(candidates)
        })
        return {
            'method_used': 'none',
            'selected_features': [],
            'candidate_features': candidates,
            'candidate_features_df': candidate_df,
            'selection_diagnostics': {'error': 'Insufficient data after dropping missing values'}
        }
    
    # Chronological train/test split for correlation (80/20)
    split_idx = int(len(data_clean) * 0.8)
    train_data = data_clean.iloc[:split_idx]
    test_data = data_clean.iloc[split_idx:]
    
    if len(train_data) < 5:
        # If too small, use all data
        train_data = data_clean
        test_data = data_clean
    
    X = data_clean[candidates].values
    y = data_clean[y_col].values
    X_train = train_data[candidates].values
    y_train = train_data[y_col].values
    
    selected_features = []
    diagnostics = {}
    correlations = {}  # Initialize correlations dict for candidate_features_df
    
    if method == "elasticnet":
        try:
            # Feature selection only: subsample very large series so ElasticNetCV stays fast.
            # Final regression in fit_regression() still uses the full dataset.
            MAX_ROWS_ENET_SELECT = 48_000
            n_total = len(data_clean)
            data_enet = data_clean
            if n_total > MAX_ROWS_ENET_SELECT:
                idx = np.unique(
                    np.linspace(0, n_total - 1, MAX_ROWS_ENET_SELECT, dtype=int)
                )
                data_enet = data_enet.iloc[idx].copy().reset_index(drop=True)
            X_sel = data_enet[candidates].values
            y_sel = data_enet[y_col].values
            selection_note = {"selection_rows_used": len(data_enet), "selection_rows_total": n_total}

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_sel)
            
            # Fewer CV folds / alphas than before: same role (pick sparsity), much faster on big n.
            alphas = np.logspace(-2, 0, 8)
            model = ElasticNetCV(
                alphas=alphas,
                l1_ratio=[0.1, 0.5, 0.7, 0.9, 0.95],
                cv=3,
                max_iter=800,
                random_state=42,
                n_jobs=-1,
            )
            model.fit(X_scaled, y_sel)
            
            # Get selected features (non-zero coefficients)
            selected_indices = np.where(np.abs(model.coef_) > 1e-6)[0]
            selected_features = [candidates[i] for i in selected_indices]
            
            diagnostics = {
                'alpha': model.alpha_,
                'l1_ratio': model.l1_ratio_,
                'coefficients': {candidates[i]: model.coef_[i] for i in selected_indices},
                'n_selected': len(selected_features),
                **selection_note,
            }
            
            # Build correlations dict for candidate_features_df (use train set)
            correlations = {}
            for feat in candidates:
                if feat in train_data.columns:
                    corr = train_data[[feat, y_col]].corr().iloc[0, 1]
                    if pd.notna(corr):
                        correlations[feat] = abs(corr)
            
            # If ElasticNet selected 0 features, fallback to correlation
            if len(selected_features) == 0:
                method = "correlation_fallback"
                diagnostics['fallback_reason'] = 'ElasticNet selected 0 features'
        
        except Exception as e:
            # Fallback to correlation on error
            method = "correlation_fallback"
            diagnostics['fallback_reason'] = f'ElasticNet error: {str(e)}'
            correlations = {}  # Will be computed in correlation branch
    
    if method == "correlation" or method == "correlation_fallback":
        # Compute correlations on TRAIN SET ONLY (to avoid leakage)
        correlations = {}
        for feat in candidates:
            if feat in train_data.columns:
                corr = train_data[[feat, y_col]].corr().iloc[0, 1]
                if pd.notna(corr):
                    correlations[feat] = abs(corr)
        
        # Sort by |correlation| and select top_k where |corr| >= threshold
        sorted_features = sorted(correlations.items(), key=lambda x: x[1], reverse=True)
        selected_features = [feat for feat, corr in sorted_features if corr >= corr_threshold][:top_k]
        
        # If none meet threshold, select top 1 anyway
        if len(selected_features) == 0 and len(sorted_features) > 0:
            selected_features = [sorted_features[0][0]]
        
        diagnostics = {
            'correlations': correlations,
            'top_k': top_k,
            'threshold': corr_threshold,
            'n_selected': len(selected_features),
            'note': 'Correlations computed on train set only'
        }
    
    # Ensure at least one feature is selected
    if len(selected_features) == 0 and len(candidates) > 0:
        # Last resort: select first candidate
        selected_features = [candidates[0]]
        if 'diagnostics' not in locals():
            diagnostics = {}
        diagnostics['fallback_reason'] = 'Selected first candidate as fallback'
    
    # Build candidate_features_df with correlation info
    # Map df column names to canonical names for display
    reverse_feature_map = {}  # df_col -> canonical_name
    for canonical, variants in FEATURE_VARIANTS.items():
        for variant in variants:
            if variant in candidates:
                reverse_feature_map[variant] = canonical
    
    candidate_data = []
    for feat in candidates:
        missing_pct = df[feat].isna().sum() / len(df) * 100 if feat in df.columns else 100
        # Get correlation from correlations dict (computed in ElasticNet or correlation branch)
        corr_train = correlations.get(feat, 0.0)
        is_selected = '✓' if feat in selected_features else ''
        canonical_name = reverse_feature_map.get(feat, feat)  # Use canonical if available, else use df col name
        candidate_data.append({
            'feature': feat,  # Actual df column name
            'canonical_name': canonical_name,  # Display name
            'missing_pct': missing_pct,
            'corr_train': corr_train,
            'selected': is_selected
        })
    candidate_features_df = pd.DataFrame(candidate_data)
    
    # Map selected_features to canonical names for UI display
    selected_features_canonical = [reverse_feature_map.get(f, f) for f in selected_features]
    
    return {
        'method_used': method,
        'selected_features': selected_features,  # Actual df column names (for modeling)
        'selected_features_canonical': selected_features_canonical,  # Canonical names (for UI)
        'candidate_features': candidates,  # Actual df column names
        'candidate_features_df': candidate_features_df,
        'selection_diagnostics': diagnostics
    }


def fit_regression(
    df: pd.DataFrame,
    y_col: str,
    selected_features: List[str],
    hour_datetime_col: str = 'hour_datetime'
) -> Dict:
    """
    Fits a regression model and returns metrics and predictions.
    
    Args:
        df: Dataframe with features and target
        y_col: Target column name
        selected_features: List of feature column names to use
        hour_datetime_col: Name of datetime column for chronological split
    
    Returns:
        Dict with:
            - model_type: str
            - selected_features: list
            - coef_table: DataFrame with feature, coefficient, standardized_coefficient
            - metrics: dict with R2, RMSE, MAE (on test set)
            - y_pred: numpy array aligned with df index (NaN for rows not predicted)
            - error: str if failed
    """
    if len(selected_features) == 0:
        return {
            'error': 'No features selected for regression'
        }
    
    # Prepare data
    required_cols = [y_col] + selected_features
    if hour_datetime_col in df.columns:
        required_cols.append(hour_datetime_col)
    
    # Check all columns exist
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        return {
            'error': f'Missing columns: {missing_cols}'
        }
    
    # Drop rows with missing values for model fitting
    data = df[required_cols].dropna()
    if len(data) < 10:
        return {
            'error': 'Insufficient data after dropping missing values'
        }
    
    # Log index info for debugging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"fit_regression: df length={len(df)}, df index range=[{df.index.min()}, {df.index.max()}], data length={len(data)}")
    
    # Sort by datetime for chronological split
    # CRITICAL: reset_index(drop=True) ensures 0-based positional indexing
    # This prevents out-of-bounds errors when df has been filtered (e.g., single year)
    if hour_datetime_col in data.columns:
        data = data.sort_values(hour_datetime_col).reset_index(drop=True)
    
    # Assert that data index is 0-based and contiguous
    assert data.index.min() == 0 and data.index.max() == len(data) - 1, \
        f"Data index must be 0-based: min={data.index.min()}, max={data.index.max()}, len={len(data)}"
    logger.info(f"After reset_index: data index range=[{data.index.min()}, {data.index.max()}], len={len(data)}")
    
    # Chronological train/test split (80/20)
    # Ensure minimum test size for reliable metrics
    MIN_TEST_SIZE = 100
    split_idx = int(len(data) * 0.8)
    
    # If dataset is small, adjust split to ensure minimum test size
    if len(data) < MIN_TEST_SIZE * 2:
        # For small datasets, use a larger test fraction or use all data
        if len(data) < 50:
            # Very small: use all data for both (metrics may be less reliable)
            train_data = data
            test_data = data
        else:
            # Small but reasonable: use 30% for test to ensure minimum size
            split_idx = max(int(len(data) * 0.7), len(data) - MIN_TEST_SIZE)
            train_data = data.iloc[:split_idx]
            test_data = data.iloc[split_idx:]
    else:
        train_data = data.iloc[:split_idx]
        test_data = data.iloc[split_idx:]
    
    # Final check: ensure test set is not too small
    if len(test_data) < 10:
        train_data = data
        test_data = data
    
    # Validate split indices are within bounds (should always be true after reset_index)
    assert split_idx >= 0 and split_idx <= len(data), \
        f"Split index {split_idx} out of bounds for data length {len(data)}"
    assert len(train_data) > 0 and len(test_data) > 0, \
        f"Invalid split: train={len(train_data)}, test={len(test_data)}"
    logger.info(f"Train/test split: train={len(train_data)}, test={len(test_data)}, split_idx={split_idx}")
    
    X_train = train_data[selected_features].values
    y_train = train_data[y_col].values
    X_test = test_data[selected_features].values
    y_test = test_data[y_col].values
    
    try:
        # Standardize features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Fit ElasticNet (use same approach as selection for consistency)
        model = ElasticNet(
            alpha=0.1,
            l1_ratio=0.5,
            max_iter=800,
            tol=1e-3,
            random_state=42,
            selection="random",
        )
        model.fit(X_train_scaled, y_train)
        
        # Predictions
        y_train_pred = model.predict(X_train_scaled)
        y_test_pred = model.predict(X_test_scaled)
        
        # Check for constant target (zero variance)
        y_test_std = np.std(y_test)
        y_test_mean = np.mean(y_test)
        
        # Metrics on test set
        if y_test_std < 1e-6:
            # Constant target: R² is undefined, set to None
            r2 = None
            rmse = 0.0
            mae = 0.0
        else:
            r2 = r2_score(y_test, y_test_pred)
            # Handle NaN/Inf R² (can happen with perfect predictions or numerical issues)
            if pd.isna(r2) or not np.isfinite(r2):
                r2 = None
            rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))
            mae = mean_absolute_error(y_test, y_test_pred)
            # Handle NaN/Inf for RMSE/MAE
            if pd.isna(rmse) or not np.isfinite(rmse):
                rmse = None
            if pd.isna(mae) or not np.isfinite(mae):
                mae = None
        
        # Raw-scale coefficients: convert from standardized space to original feature scale
        # model.coef_ are in standardized space (fitted on scaled features)
        # raw_coef_i = standardized_coef_i / scale_i
        raw_coefs = model.coef_ / scaler.scale_
        raw_intercept = float(model.intercept_ - np.dot(model.coef_, scaler.mean_ / scaler.scale_))
        
        coef_table = pd.DataFrame({
            'feature': selected_features,
            'coefficient': raw_coefs,
            'standardized_coefficient': model.coef_
        })
        
        # Generate predictions for full dataframe (aligned with original index)
        # First, get all rows (including those with missing values)
        full_data = df[selected_features].copy()
        full_data_clean = full_data.dropna()
        full_data_scaled = scaler.transform(full_data_clean)
        
        # Predict for non-missing rows
        # CRITICAL: After year filtering, df.index is reset to 0-based in backend/main.py
        # So full_data_clean.index contains positional indices (0, 1, 2, ...)
        # that can be used directly to index into y_pred_full array
        y_pred_full = np.full(len(df), np.nan)
        valid_positions = full_data_clean.index.values  # Get index values as numpy array
        
        # Validate positions are within bounds (should always be true after reset_index)
        valid_mask = (valid_positions >= 0) & (valid_positions < len(y_pred_full))
        valid_positions = valid_positions[valid_mask]
        
        if len(valid_positions) > 0:
            # Only predict for valid positions
            valid_data_scaled = full_data_scaled[valid_mask]
            y_pred_valid = model.predict(valid_data_scaled)
            # Assign predictions using positional indices
            if len(y_pred_valid) == len(valid_positions):
                y_pred_full[valid_positions] = y_pred_valid
            else:
                # Fallback: use minimum length
                min_len = min(len(y_pred_valid), len(valid_positions))
                y_pred_full[valid_positions[:min_len]] = y_pred_valid[:min_len]
        
        confidence = get_regression_confidence(r2)
        
        residual_std = float(np.std(y_test - y_test_pred)) if len(y_test) > 0 else 0.0
        
        return {
            'model_type': 'ElasticNet',
            'selected_features': selected_features,
            'coef_table': coef_table,
            'intercept': raw_intercept,
            'metrics': {
                'r2': r2,
                'rmse': rmse,
                'mae': mae
            },
            'confidence': confidence,
            'y_pred': y_pred_full,
            'y_test': y_test,
            'y_test_pred': y_test_pred,
            'train_size': len(train_data),
            'test_size': len(test_data),
            'error': None,
            '_model': model,
            '_scaler': scaler,
            '_residual_std': residual_std,
        }
    
    except Exception as e:
        return {
            'error': f'Regression fitting failed: {str(e)}'
        }


def get_regression_confidence(r2) -> Dict[str, str]:
    """
    Returns confidence level and badge text for a given R² score.
    
    Args:
        r2: R² score (can be None)
    
    Returns:
        Dict with 'level', 'badge', and 'color' keys
    """
    if r2 is None or (isinstance(r2, (int, float)) and not np.isfinite(r2)):
        return {'level': 'N/A', 'badge': 'N/A (R² unavailable)', 'color': '#6b7280'}
    if r2 >= 0.60:
        return {'level': 'Strong', 'badge': f'Strong (R²={r2:.2f})', 'color': '#22c55e'}
    elif r2 >= 0.30:
        return {'level': 'Moderate', 'badge': f'Moderate (R²={r2:.2f})', 'color': '#fbbf24'}
    elif r2 >= 0.10:
        return {'level': 'Weak', 'badge': f'Weak (R²={r2:.2f})', 'color': '#f97316'}
    else:
        return {'level': 'Very weak', 'badge': f'Very weak (R²={r2:.2f})', 'color': '#ef4444'}
