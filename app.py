import streamlit as st
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Import new modules
try:
    from nsrdb_downloader import fetch_nsrdb_weather, CITY_COORDS, ensure_city_coordinates, resolve_city_coords_fallback
    from build_merge import build_and_save_merged
    NSRDB_AVAILABLE = True
except ImportError:
    NSRDB_AVAILABLE = False
    CITY_COORDS = {}
    ensure_city_coordinates = None
    resolve_city_coords_fallback = None

# Import insights and icons modules
try:
    from insights import (
        generate_anomaly_explanations,
        detect_recurring_patterns,
        generate_executive_summary,
        estimate_cost_impact
    )
    from icons import svg_icon
    INSIGHTS_AVAILABLE = True
except ImportError:
    INSIGHTS_AVAILABLE = False
    svg_icon = lambda name, size=18, color="currentColor": f'<svg width="{size}" height="{size}"></svg>'

# Import regression engine
try:
    from regression_engine import (
        get_candidate_weather_features,
        select_weather_features,
        fit_regression
    )
    REGRESSION_ENGINE_AVAILABLE = True
except ImportError:
    REGRESSION_ENGINE_AVAILABLE = False

# Page config
st.set_page_config(
    page_title="Energy Anomaly Explorer",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================
# DARK THEME CSS
# =========================
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Orbitron:wght@500;600&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" rel="stylesheet">
<style>
    /* Global Inter font */
    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    }
    
    /* Dark theme base */
    .stApp {
        background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
        color: #e0e0e0;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    
    /* Main content area */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background-color: #1e1e2e;
        border-right: 1px solid #2d2d44;
    }
    
    /* Headers */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    }
    
    h1 {
        color: #ffffff;
        font-weight: 700;
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
        letter-spacing: -0.02em;
    }
    
    h2, h3 {
        color: #ffffff;
        font-weight: 600;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }
    
    /* Apply Inter to all text elements */
    body, .stMarkdown, .stMetric, .stDataFrame, .sidebar .css-1d391kg, 
    .main .block-container, .stSelectbox, .stSlider, .stButton, 
    .stTextInput, .stNumberInput, .stCheckbox, .stRadio {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    }
    
    /* Cards and containers */
    .metric-card {
        background: linear-gradient(135deg, #1e1e2e 0%, #252538 100%);
        border: 1px solid #2d2d44;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.4);
    }
    
    /* Status badges */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 500;
        margin: 0.25rem;
    }
    
    .status-success {
        background: rgba(34, 197, 94, 0.2);
        color: #22c55e;
        border: 1px solid rgba(34, 197, 94, 0.3);
    }
    
    .status-warning {
        background: rgba(251, 191, 36, 0.2);
        color: #fbbf24;
        border: 1px solid rgba(251, 191, 36, 0.3);
    }
    
    .status-error {
        background: rgba(239, 68, 68, 0.2);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
        transition: all 0.3s;
        box-shadow: 0 4px 6px rgba(99, 102, 241, 0.3);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(99, 102, 241, 0.4);
    }
    
    /* Selectboxes and inputs */
    .stSelectbox > div > div {
        background-color: #1e1e2e;
        border: 1px solid #2d2d44;
        border-radius: 8px;
    }
    
    .stSlider > div > div {
        background-color: #1e1e2e;
    }
    
    /* Dividers */
    hr {
        border: none;
        border-top: 1px solid #2d2d44;
        margin: 2rem 0;
    }
    
    /* Tables */
    .dataframe {
        background-color: #1e1e2e;
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Footer */
    .footer {
        margin-top: 4rem;
        padding-top: 2rem;
        border-top: 1px solid #2d2d44;
        text-align: center;
        color: #888;
        font-size: 0.85rem;
    }
    
    /* Info boxes */
    .stInfo {
        background-color: rgba(59, 130, 246, 0.1);
        border-left: 4px solid #3b82f6;
        border-radius: 6px;
    }
    
    /* Success/Error messages */
    .stSuccess {
        background-color: rgba(34, 197, 94, 0.1);
        border-left: 4px solid #22c55e;
    }
    
    .stError {
        background-color: rgba(239, 68, 68, 0.1);
        border-left: 4px solid #ef4444;
    }
    
    /* Sidebar section headers - clean, no card styling */
    .sidebar-header {
        color: #B6C2E2;
        font-size: 0.9rem;
        font-weight: 600;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
        margin: 1.25rem 0 0.5rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #2d2d44;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* Sidebar content cards - use only for actual content blocks */
    .sidebar-content-card {
        background: rgba(30, 30, 46, 0.5);
        border-radius: 8px;
        padding: 1rem;
        margin: 0.75rem 0;
        border: 1px solid #2d2d44;
    }
    
    /* Legacy sidebar-section for backward compatibility (will be phased out) */
    .sidebar-section {
        background: rgba(30, 30, 46, 0.5);
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
        border: 1px solid #2d2d44;
    }
    
    /* Fix sidebar collapse/resize icon - Material Symbols */
    /* Apply Material Symbols font to all Material icon classes with proper variation settings */
    .material-symbols-rounded,
    .material-symbols-outlined,
    .material-icons,
    [class*="material-symbols"],
    [class*="material-icons"],
    span[class*="material"] {
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
        font-weight: normal;
        font-style: normal;
        font-size: 24px;
        line-height: 1;
        letter-spacing: normal;
        text-transform: none;
        display: inline-block;
        white-space: nowrap;
        word-wrap: normal;
        direction: ltr;
        font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24 !important;
        -webkit-font-feature-settings: 'liga';
        -webkit-font-smoothing: antialiased;
    }
    
    /* Disable sidebar collapse - hide the actual collapse button container and all related elements */
    div[data-testid="stSidebarCollapseButton"],
    button[data-testid="stBaseButton-headerNoPadding"],
    button[data-testid="baseButton-header"],
    section[data-testid="stSidebar"] button[data-testid="baseButton-header"],
    header[data-testid="stHeader"] button[data-testid="baseButton-header"],
    section[data-testid="stSidebar"] button[aria-label*="collapse"],
    section[data-testid="stSidebar"] button[aria-label*="sidebar"],
    section[data-testid="stSidebar"] button[title*="collapse"],
    [data-testid="stSidebar"] button[class*="collapse"],
    [data-testid="stSidebar"] button[class*="resize"],
    header button[data-testid="baseButton-header"] {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        width: 0 !important;
        height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        border: none !important;
        overflow: hidden !important;
        pointer-events: none !important;
        position: absolute !important;
        left: -9999px !important;
        top: -9999px !important;
        font-size: 0 !important;
        line-height: 0 !important;
        color: transparent !important;
        background: transparent !important;
    }
    
    /* Hide the Material Icon span that contains the ligature text */
    span[data-testid="stIconMaterial"],
    span[data-testid="stIconMaterial"] * {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        font-size: 0 !important;
        width: 0 !important;
        height: 0 !important;
        color: transparent !important;
    }
    
    /* Hide any text content inside collapse button */
    div[data-testid="stSidebarCollapseButton"] *,
    button[data-testid="stBaseButton-headerNoPadding"] *,
    section[data-testid="stSidebar"] button[data-testid="baseButton-header"] *,
    header[data-testid="stHeader"] button[data-testid="baseButton-header"] *,
    button[data-testid="baseButton-header"] * {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        font-size: 0 !important;
        width: 0 !important;
        height: 0 !important;
    }
    
    /* Disable sidebar collapse - completely hide the collapse button and all related elements (duplicate block removed) */
    section[data-testid="stSidebar"] button[data-testid="baseButton-header"] span,
    header[data-testid="stHeader"] button[data-testid="baseButton-header"] span,
    button[data-testid="baseButton-header"] span,
    section[data-testid="stSidebar"] button[aria-label*="collapse"] span,
    section[data-testid="stSidebar"] button[aria-label*="sidebar"] span {
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
        font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24 !important;
        font-size: 24px !important;
        display: inline-block !important;
    }
    
    /* Disable sidebar collapse - completely hide the collapse button and all related elements */
    section[data-testid="stSidebar"] button[data-testid="baseButton-header"],
    header[data-testid="stHeader"] button[data-testid="baseButton-header"],
    button[data-testid="baseButton-header"],
    section[data-testid="stSidebar"] button[aria-label*="collapse"],
    section[data-testid="stSidebar"] button[aria-label*="sidebar"],
    section[data-testid="stSidebar"] button[title*="collapse"],
    [data-testid="stSidebar"] button[class*="collapse"],
    [data-testid="stSidebar"] button[class*="resize"],
    header button[data-testid="baseButton-header"] {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        width: 0 !important;
        height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        border: none !important;
        overflow: hidden !important;
        pointer-events: none !important;
        position: absolute !important;
        left: -9999px !important;
        top: -9999px !important;
        font-size: 0 !important;
        line-height: 0 !important;
        color: transparent !important;
        background: transparent !important;
    }
    
    /* Hide any text content inside collapse button */
    section[data-testid="stSidebar"] button[data-testid="baseButton-header"] *,
    header[data-testid="stHeader"] button[data-testid="baseButton-header"] *,
    button[data-testid="baseButton-header"] * {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        font-size: 0 !important;
        width: 0 !important;
        height: 0 !important;
    }
    
    /* ===== Figma Hero Animations ===== */
    /* Icon rotation/scale animation */
    @keyframes iconRotateScale {
        0%, 100% { transform: rotate(0deg) scale(1); }
        25% { transform: rotate(-5deg) scale(1.1); }
        50% { transform: rotate(5deg) scale(1); }
        75% { transform: rotate(-5deg) scale(1.1); }
    }
    .hero-icon-animated {
        animation: iconRotateScale 2s ease-in-out infinite;
        animation-delay: 0s;
    }
    
    /* ENERGY E - x movement + text shadow */
    @keyframes energyE {
        0%, 100% { transform: translateX(0); text-shadow: 0 0 0px rgba(0,255,255,0); }
        50% { transform: translateX(-2px); text-shadow: 2px 0 10px rgba(0,255,255,0.8), -2px 0 10px rgba(255,0,255,0.8); }
    }
    .hero-energy-e {
        animation: energyE 0.3s ease-in-out infinite;
        animation-delay: 4s;
    }
    
    /* ENERGY R - y movement + rotate + color */
    @keyframes energyR {
        0%, 100% { transform: translateY(0) rotate(0deg); color: rgb(255, 255, 255); }
        25% { transform: translateY(-3px) rotate(-2deg); color: rgb(34, 211, 238); }
        50% { transform: translateY(3px) rotate(2deg); color: rgb(255, 255, 255); }
        75% { transform: translateY(-2px) rotate(0deg); color: rgb(34, 211, 238); }
    }
    .hero-energy-r {
        animation: energyR 0.4s ease-in-out infinite;
        animation-delay: 3.5s;
    }
    
    /* ANOMALY A - scale + color */
    @keyframes anomalyA {
        0%, 100% { transform: scale(1); color: rgb(255, 255, 255); }
        33% { transform: scale(1.15); color: rgb(239, 68, 68); }
        66% { transform: scale(0.95); color: rgb(255, 255, 255); }
    }
    .hero-anomaly-a {
        animation: anomalyA 0.5s ease-in-out infinite;
        animation-delay: 2.5s;
    }
    
    /* ANOMALY O - x movement + opacity + text shadow */
    @keyframes anomalyO {
        0%, 100% { transform: translateX(0); opacity: 1; text-shadow: 0 0 0px rgba(255,0,0,0); }
        50% { transform: translateX(3px); opacity: 0.7; text-shadow: 0 0 20px rgba(255,0,0,0.6); }
    }
    .hero-anomaly-o {
        animation: anomalyO 0.3s ease-in-out infinite;
        animation-delay: 3s;
    }
    
    /* ANOMALY Y - y movement + rotate + text shadow */
    @keyframes anomalyY {
        0%, 100% { transform: translateY(0) rotate(0deg); text-shadow: 0 0 0px rgba(168,85,247,0); }
        50% { transform: translateY(-4px) rotate(5deg); text-shadow: 0 0 15px rgba(168,85,247,0.8); }
    }
    .hero-anomaly-y {
        animation: anomalyY 0.4s ease-in-out infinite;
        animation-delay: 2s;
    }
    
    /* EXPLORER X - scaleX/scaleY */
    @keyframes explorerX {
        0%, 100% { transform: scaleX(1) scaleY(1); }
        33% { transform: scaleX(1.2) scaleY(0.8); }
        66% { transform: scaleX(0.9) scaleY(1.1); }
    }
    .hero-explorer-x {
        animation: explorerX 0.3s ease-in-out infinite;
        animation-delay: 4.5s;
    }
    
    /* EXPLORER E (end) - x movement + opacity + blur */
    @keyframes explorerE {
        0%, 100% { transform: translateX(0); opacity: 1; filter: blur(0px); }
        50% { transform: translateX(2px); opacity: 0.6; filter: blur(1px); }
    }
    .hero-explorer-e {
        animation: explorerE 0.2s ease-in-out infinite;
        animation-delay: 5s;
    }
    
    /* Glitch overlay effect */
    @keyframes glitchOverlay {
        0%, 100% { opacity: 0; }
        50% { opacity: 0.3; }
    }
    .hero-glitch-overlay {
        position: absolute;
        inset: 0;
        background: linear-gradient(90deg, rgba(6, 182, 212, 0.2), rgba(168, 85, 247, 0.2));
        filter: blur(24px);
        pointer-events: none;
        animation: glitchOverlay 0.1s ease-in-out infinite;
        animation-delay: 6s;
    }
    
    /* Initial fade-in for subtitle */
    @keyframes subtitleFadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }
    .hero-subtitle {
        animation: subtitleFadeIn 0.5s ease-in forwards;
        animation-delay: 0.5s;
        opacity: 0;
    }
    
</style>
""", unsafe_allow_html=True)
    
# Helper function for Figma-style hero branding with animations
def render_figma_style_hero():
    """
    Renders a Figma-inspired hero branding header with CSS animations:
    - Gradient rounded square icon with lightning bolt (Zap icon) - animated
    - 3-line title (ENERGY, ANOMALY, EXPLORER) with colored anomaly letters - animated
    - Italicized subtitle with fade-in
    Based on Figma React design, converted to pure HTML/CSS with CSS keyframes.
    """
    # Zap/Lightning bolt SVG (matching lucide-react Zap icon) - white, filled
    zap_svg = '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="white"/></svg>'
    
    # Build the 3-line title with colored anomaly letters and animation classes
    # ENERGY: E (cyan gradient, animated), R (cyan accent, animated)
    energy_line = (
        '<span class="hero-energy-e" style="background: linear-gradient(135deg, #06b6d4, #0891b2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; display: inline-block;">E</span>'
        '<span style="color: #ffffff;">N</span>'
        '<span style="color: #ffffff;">E</span>'
        '<span class="hero-energy-r" style="color: #22d3ee;">R</span>'
        '<span style="color: #ffffff;">G</span>'
        '<span style="color: #ffffff;">Y</span>'
    )
    
    # ANOMALY: A (red, animated), O (white, animated), Y (purple gradient, animated)
    anomaly_line = (
        '<span class="hero-anomaly-a" style="color: #ef4444;">A</span>'
        '<span style="color: #ffffff;">N</span>'
        '<span class="hero-anomaly-o" style="color: #ffffff;">O</span>'
        '<span style="color: #ffffff;">M</span>'
        '<span style="color: #ffffff;">A</span>'
        '<span style="color: #ffffff;">L</span>'
        '<span class="hero-anomaly-y" style="background: linear-gradient(135deg, #a855f7, #9333ea); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; display: inline-block;">Y</span>'
    )
    
    # EXPLORER: X (orange/yellow gradient, animated), E at end (white, animated)
    explorer_line = (
        '<span style="color: #ffffff;">E</span>'
        '<span class="hero-explorer-x" style="background: linear-gradient(135deg, #fbbf24, #f59e0b); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; display: inline-block;">X</span>'
        '<span style="color: #ffffff;">P</span>'
        '<span style="color: #ffffff;">L</span>'
        '<span style="color: #ffffff;">O</span>'
        '<span style="color: #ffffff;">R</span>'
        '<span class="hero-explorer-e" style="color: #ffffff;">E</span>'
        '<span style="color: #ffffff;">R</span>'
    )
    
    # Build hero HTML as a single string (matching Figma layout with animations)
    hero_html = (
        "<div style='text-align: center; padding: 2.5rem 0 2rem 0; margin-bottom: 2rem; position: relative;'>"
        # Glitch overlay effect
        "<div class='hero-glitch-overlay'></div>"
        "<div style='display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1rem; position: relative; z-index: 1;'>"
        # Gradient rounded square icon with Zap/lightning bolt (animated)
        "<div class='hero-icon-animated' style='padding: 0.75rem; background: linear-gradient(135deg, #06b6d4 0%, #3b82f6 50%, #8b5cf6 100%); border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-bottom: 0.5rem;'>"
        + zap_svg +
        "</div>"
        # Three-line title (matching Figma text-6xl, tracking-tight)
        "<div style='display: flex; flex-direction: column; align-items: center; gap: 0.25rem;'>"
        # ENERGY line
        "<div style='font-family: \"Inter\", -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif; font-size: clamp(3rem, 6vw, 4.5rem); font-weight: 700; letter-spacing: -0.025em; line-height: 1.1; display: flex; align-items: center; justify-content: center;'>"
        + energy_line +
        "</div>"
        # ANOMALY line
        "<div style='font-family: \"Inter\", -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif; font-size: clamp(3rem, 6vw, 4.5rem); font-weight: 700; letter-spacing: -0.025em; line-height: 1.1; display: flex; align-items: center; justify-content: center;'>"
        + anomaly_line +
        "</div>"
        # EXPLORER line
        "<div style='font-family: \"Inter\", -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif; font-size: clamp(3rem, 6vw, 4.5rem); font-weight: 700; letter-spacing: -0.025em; line-height: 1.1; display: flex; align-items: center; justify-content: center;'>"
        + explorer_line +
        "</div>"
        "</div>"
        # Subtitle (matching Figma: slate-400, text-sm, tracking-wide, italic) with fade-in
        "<p class='hero-subtitle' style='font-family: \"Inter\", -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif; margin-top: 1.5rem; font-size: clamp(0.875rem, 1.2vw, 1rem); font-weight: 400; font-style: italic; color: #94a3b8; letter-spacing: 0.05em; line-height: 1.5; max-width: 650px;'>"
        "Advanced anomaly detection for building energy load profiles"
        "</p>"
        "</div>"
        "</div>"
    )
    
    # Render with unsafe_allow_html=True - this is the ONLY render call
    st.markdown(hero_html, unsafe_allow_html=True)

# Header - Figma-style Hero Branding
render_figma_style_hero()

# Helper function for clean sidebar section headers
def sidebar_section_header(title: str, icon_name: str = None):
    """
    Renders a clean sidebar section header with optional icon.
    No card styling - just text + icon + divider.
    """
    icon_html = ""
    if icon_name:
        icon_html = svg_icon(icon_name, size=16, color="#ffffff")
    
    st.sidebar.markdown(f"""
    <div class='sidebar-header'>
        {icon_html}
        <span>{title}</span>
    </div>
    """, unsafe_allow_html=True)

# Helper function for main page section headers
def section_header(title: str, icon_name: str = None, subtitle: str = None):
    """
    Renders a clean main page section header with optional icon and subtitle.
    No card styling - just text + icon.
    """
    icon_html = ""
    if icon_name:
        icon_html = svg_icon(icon_name, size=18, color="#ffffff")
    
    subtitle_html = ""
    if subtitle:
        subtitle_html = f"<p style='color: #888; font-size: 0.9rem;'>{subtitle}</p>"
    
    st.markdown(f"""
    <div style='margin: 1rem 0;'>
        <h3 style='color: #ffffff;'>
            {icon_html}
            {title}
        </h3>
        {subtitle_html}
    </div>
    """, unsafe_allow_html=True)

# Helper function for KPI grid (reusable, similar to Cost Impact Estimate style)
def kpi_grid(items: list, columns: int = 3) -> str:
    """
    Generates HTML for a grid of KPI items (label + value pairs).
    
    Args:
        items: List of dicts with keys: 'label', 'value', 'value_color' (optional)
        columns: Number of columns in grid (default 3)
    
    Returns:
        HTML string for the KPI grid
    """
    if not items:
        return ""
    
    # Build grid HTML - ensure clean, valid HTML output without f-string interpolation issues
    grid_html = "<div style='display: grid; grid-template-columns: repeat(" + str(columns) + ", 1fr); gap: 1rem; margin-bottom: 0.75rem;'>"
    
    for item in items:
        label = str(item.get('label', ''))
        value = str(item.get('value', ''))
        value_color = str(item.get('value_color', '#ffffff'))  # Default white
        
        # Build each KPI item - label (muted) + value (large, colored)
        grid_html += (
            "<div>"
            "<div style='color: #9aa0a6; font-size: 0.85rem; margin-bottom: 0.25rem;'>" + label + "</div>"
            "<div style='color: " + value_color + "; font-size: 1.7rem; font-weight: 600;'>" + value + "</div>"
            "</div>"
        )
    
    grid_html += "</div>"
    return grid_html

# Helper function for compact section cards (header + body in one card)
def section_card(title: str, body_markdown: str, icon_name: str = None, accent_color: str = "#3b82f6", variant: str = "default"):
    """
    Renders a compact section card with header (icon + title) and body content in one card.
    Header is inside the card with accent color strip, body content immediately below.
    
    Args:
        title: Header text
        body_markdown: Body content (already formatted markdown/HTML, can be empty string)
        icon_name: SVG icon name (optional)
        accent_color: Accent color for border/icon (default: blue #3b82f6)
        variant: "default" (neutral) or "success" (green tinted)
    
    Returns:
        None (renders directly via st.markdown)
    """
    icon_html = ""
    if icon_name:
        # Get SVG icon and clean up inline styles for proper alignment
        icon_svg = svg_icon(icon_name, size=18, color=accent_color)
        # Remove inline-block and margin styles, set to block for proper alignment
        icon_svg_clean = icon_svg.replace('style="display: inline-block; vertical-align: middle; margin-right: 0.5rem;"', 
                                         'style="display: block; flex-shrink: 0;"')
        # Wrap in flex container for perfect vertical centering
        icon_html = '<div style="display: flex; align-items: center; justify-content: center; flex-shrink: 0;">' + icon_svg_clean + '</div>'
    
    # Card styling based on variant
    if variant == "success":
        card_bg = "rgba(34, 197, 94, 0.1)"
        card_border = f"1px solid rgba(34, 197, 94, 0.3)"
    else:
        card_bg = "rgba(30, 30, 46, 0.5)"
        card_border = "1px solid #2d2d44"
    
    # Ensure body_markdown is a string (handle None or empty)
    if body_markdown is None:
        body_markdown = ""
    
    # If body is empty, show a fallback message
    if body_markdown.strip() == "":
        body_markdown = "<p style='color: #888; font-size: 0.9rem; margin: 0;'>No content available yet.</p>"
    
    # Build the complete card HTML - insert body_markdown directly via string concatenation
    # This ensures HTML is inserted as-is without any escaping from f-string interpolation
    card_html = (
        "<div style='background: " + card_bg + "; border: " + card_border + "; border-left: 3px solid " + accent_color + "; "
        "border-radius: 8px; padding: 0.85rem 1rem; margin: 1rem 0 0.85rem 0;'>"
        "<div style='display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.5rem;'>"
        + icon_html +
        "<h4 style='color: #ffffff; font-size: 1.1rem; font-weight: 600; margin: 0; line-height: 1.2;'>" + title + "</h4>"
        "</div>"
        "<div style='color: #e0e0e0; line-height: 1.6; font-size: 0.95rem;'>"
        + body_markdown +  # Insert body_markdown directly (not via f-string to avoid any escaping)
        "</div>"
        "</div>"
        "<style>"
        ".section-card ul { margin: 0.25rem 0 0 1.1rem !important; padding: 0 !important; }"
        ".section-card li { margin: 0.3rem 0 !important; }"
        ".section-card p { margin: 0.25rem 0 0.5rem 0 !important; }"
        "</style>"
    )
    
    # Render with unsafe_allow_html=True - this is the ONLY render call
    st.markdown(card_html, unsafe_allow_html=True)

# Helper function to replace emoji icons with SVG icons in text
def replace_emoji_with_icon(text: str) -> str:
    """
    Replaces emoji icons in text with SVG icons from icons.py.
    Returns HTML string with SVG icons inline, baseline-aligned with text.
    """
    # Map emojis to icon names
    emoji_map = {
        '✅': 'shield-check',
        '⚠️': 'target',
        '🔴': 'target',
        '🌡️': 'activity',
        '❄️': 'activity',
        '⚙️': 'wrench',
        '🕐': 'clock',
        '📅': 'calendar',
        '📈': 'bar-chart',
        '🚨': 'target',
        '💡': 'lightbulb',
        '📊': 'bar-chart',
    }
    
    # Replace emojis with SVG icons (baseline-aligned, 16px, stroke-width=2)
    result = text
    for emoji, icon_name in emoji_map.items():
        if emoji in result:
            # Use inline SVG with proper alignment
            icon_html = svg_icon(icon_name, size=16, color="#ffffff")
            # Replace emoji with SVG icon, maintaining text alignment
            result = result.replace(emoji, icon_html)
    
    return result

# Get project root directory
PROJECT_ROOT = Path(__file__).parent

# =========================
# AUTHORITATIVE CITY LIST
# =========================
# Based on OpenEI Simulated Load Profile Dataset:
# https://data.openei.org/submissions/515
# Cities are fetched dynamically from OpenEI submission 515
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_openei_cities():
    """
    Fetch city list from OpenEI submission 515.
    Returns dict mapping clean city key to display name and URL.
    """
    try:
        from openei_loader import fetch_openei_city_resources
        return fetch_openei_city_resources()
    except Exception as e:
        st.error(f"Error fetching OpenEI cities: {e}")
        return {}

def get_valid_cities():
    """
    Returns the authoritative list of valid cities from OpenEI dataset.
    This is the ONLY source of truth for cities in the app.
    """
    city_resources = get_openei_cities()
    # Return sorted list of clean city keys
    return sorted(city_resources.keys()) if city_resources else []

def validate_city_files(city):
    """
    Validate that required files exist for a city.
    Returns (load_file_exists, merged_file_exists, load_file_path, merged_file_path)
    """
    city_lower = city.lower()
    # Check LoadProfiles folder first (for OpenEI downloads)
    load_file = PROJECT_ROOT / "LoadProfiles" / f"{city}_SimulatedLoadProfile.csv"
    if not load_file.exists():
        # Fallback to project root (legacy location)
        load_file = PROJECT_ROOT / f"{city}_SimulatedLoadProfile.csv"
    merged_file = PROJECT_ROOT / f"{city_lower}_load_weather_merged.csv"
    
    return (
        load_file.exists(),
        merged_file.exists(),
        load_file,
        merged_file
    )

@st.cache_data
def load_merged_data(city):
    """Load merged data if available - do NOT parse datetime here"""
    city_lower = city.lower()
    merged_file = PROJECT_ROOT / f"{city_lower}_load_weather_merged.csv"
    if merged_file.exists():
        df = pd.read_csv(merged_file)
        return df, True
    return None, False

# Feature column mapping for robust handling
# Extended to include all weather features that may be selected by regression engine
FEATURE_MAP = {
    "Temperature": ["Temperature", "temperature", "temp", "air_temperature", "Air Temperature"],
    "Dew Point": ["Dew Point", "DewPoint", "dew_point", "dew point", "Dew Point Temperature"],
    "Clearsky GHI": ["Clearsky GHI", "ClearskyGHI", "clearsky_ghi", "Clearsky GHI", "GHI"],
    "Wind Speed": ["Wind Speed", "WindSpeed", "wind_speed", "wind speed", "Wind"],
    "Pressure": ["Pressure", "pressure", "surface_pressure", "Surface Pressure", "Pressure (Pa)"],
    "Cloud_Type": ["Cloud_Type", "Cloud Type", "CloudType", "cloud_type", "Cloud Type Code"],
}

def resolve_feature_columns(df, required_features=None):
    """
    Resolve actual feature column names from dataframe.
    Returns dict mapping canonical names to actual column names.
    
    Args:
        df: DataFrame to search
        required_features: List of canonical feature names that must be present.
                         If None, returns all found features (flexible mode).
                         If provided, returns None only if any required feature is missing.
    
    Returns:
        Dict mapping canonical_name -> actual_column_name, or None if required features missing.
    """
    resolved = {}
    for canonical, variants in FEATURE_MAP.items():
        found = None
        for variant in variants:
            if variant in df.columns:
                found = variant
                break
        if found is not None:
            resolved[canonical] = found
        elif required_features and canonical in required_features:
            # Required feature is missing
            return None
    
    # If required_features specified and all found, or no requirements, return resolved
    if required_features:
        if all(canonical in resolved for canonical in required_features):
            return resolved
        else:
            return None
    
    return resolved

def standardize_datetime(df):
    """
    Standardize/parse hour_datetime into datetime64[ns].

    Logic:
    - Only acts if 'hour_datetime' exists
    - Try flexible parse first (Houston ISO)
    - If >10% NaT, retry with SAS format '%d%b%Y:%H:%M:%S' (Chicago)
    - No fabricated dates / no date_range fallback
    """
    if 'hour_datetime' not in df.columns:
        return df

    s = pd.to_datetime(df['hour_datetime'], errors='coerce')

    if s.isna().mean() > 0.10:
        s = pd.to_datetime(df['hour_datetime'], errors='coerce', format='%d%b%Y:%H:%M:%S')

    df['hour_datetime'] = s
    return df

@st.cache_data
def load_data(city):
    """
    Main data loading function.
    Only processes cities from OpenEI submission 515.
    Chicago: strict-merged-only (no rebuilding, no weather folder reads).
    Other cities: merged file or auto-download.
    """
    city_lower = city.lower()
    
    # Chicago: STRICT merged-only policy
    if city_lower == "chicago":
        merged_df, is_merged = load_merged_data(city)
        if not is_merged:
            return None, False  # Will show error in UI
        
        df = merged_df.copy()
        df = standardize_datetime(df)
        
        # Validate hour_datetime after standardization
        if 'hour_datetime' not in df.columns:
            return None, "hour_datetime column missing after standardization"
        
        # Check for NaT values
        nat_count = df['hour_datetime'].isna().sum()
        if nat_count > 0:
            nat_pct = (nat_count / len(df)) * 100
            sample_strings = df[df['hour_datetime'].isna()]['hour_datetime'].head(3) if len(df[df['hour_datetime'].isna()]) > 0 else []
            error_msg = (
                f"hour_datetime contains {nat_count} NaT values ({nat_pct:.1f}% of data) after parsing.\n"
                f"Tried flexible and SAS format (%d%b%Y:%H:%M:%S)."
            )
            return None, error_msg
        
        return df, True
    
    # Other cities (Houston, etc.): try merged file first
    merged_df, is_merged = load_merged_data(city)
    if is_merged:
        df = merged_df.copy()
        df = standardize_datetime(df)
        
        # Validate hour_datetime after standardization
        if 'hour_datetime' not in df.columns:
            return None, "hour_datetime column missing after standardization"
        
        # Check for NaT values
        nat_count = df['hour_datetime'].isna().sum()
        if nat_count > 0:
            nat_pct = (nat_count / len(df)) * 100
            error_msg = (
                f"hour_datetime contains {nat_count} NaT values ({nat_pct:.1f}% of data) after parsing.\n"
                f"Tried flexible and SAS format (%d%b%Y:%H:%M:%S)."
            )
            return None, error_msg
        
        return df, True
    
    # No merged file for non-Chicago cities - will trigger download in UI
    return None, False

def get_building_columns(df):
    """Identify building columns (numeric columns excluding time and weather)"""
    exclude_patterns = ['temperature', 'dew', 'pressure', 'wind', 'clearsky', 'cloud', 'ghi']

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    building_cols = []
    for c in numeric_cols:
        c_lower = c.lower()
        if not any(p in c_lower for p in exclude_patterns):
            building_cols.append(c)

    return building_cols

@st.cache_resource
def fit_model(X, y):
    model = LinearRegression()
    model.fit(X, y)
    return model

def detect_anomalies(df, building_col, z_threshold=2, use_fixed_features=False, auto_select_features=True, selection_method="elasticnet", top_k=3, include_cloud_type=False, selected_year="All"):
    """
    Detect anomalies for a single building with dynamic or fixed feature selection.
    
    Args:
        df: Dataframe with features and target
        building_col: Building column name
        z_threshold: Z-score threshold for anomalies
        use_fixed_features: If True, use fixed 3-feature model
        auto_select_features: If True, use dynamic feature selection
        selection_method: "elasticnet" or "correlation"
        top_k: Number of features for correlation method
    """
    
    # Initialize regression results storage if needed
    if 'regression_results' not in st.session_state:
        st.session_state['regression_results'] = {}
    
    # Create comprehensive cache key for stability
    # Includes: city, building, year filter, feature mode, selected features, model type, dataset signature
    dataset_signature = (
        len(df),
        df['hour_datetime'].min() if 'hour_datetime' in df.columns else None,
        df['hour_datetime'].max() if 'hour_datetime' in df.columns else None
    )
    feature_mode_key = "fixed" if use_fixed_features else f"{selection_method}_k{top_k}_cloud{include_cloud_type}"
    cache_key = (building_col, selected_year, feature_mode_key, dataset_signature)
    
    # Helper function to resolve feature names to actual df column names
    def resolve_feature_names_to_df_cols(feature_names, df):
        """Resolve feature names (canonical or df col names) to actual df column names."""
        resolved = []
        feature_map = resolve_feature_columns(df)  # Get mapping of canonical -> df col
        reverse_map = {v: k for k, v in feature_map.items()} if feature_map else {}  # df col -> canonical
        
        for feat in feature_names:
            # Check if it's already a df column name
            if feat in df.columns:
                resolved.append(feat)
            # Check if it's a canonical name that maps to a df column
            elif feat in feature_map and feature_map[feat] in df.columns:
                resolved.append(feature_map[feat])
            # Check if it's a df column that maps to a canonical (for backwards compatibility)
            elif feat in reverse_map and feat in df.columns:
                resolved.append(feat)
            # Otherwise, skip with warning (will be logged below)
        
        return resolved
    
    # Check if we have cached regression results
    regression_result = None
    if cache_key in st.session_state.get('regression_results', {}):
        regression_result = st.session_state['regression_results'][cache_key]
        selected_features = regression_result.get('selected_features', [])
        if len(selected_features) > 0:
            # Resolve feature names to actual df column names (handles canonical names)
            feature_cols = resolve_feature_names_to_df_cols(selected_features, df)
            if len(feature_cols) == 0:
                # All features missing, invalidate cache
                regression_result = None
            elif len(feature_cols) < len(selected_features):
                # Some features missing, update cache with resolved names
                regression_result['selected_features'] = feature_cols
                st.session_state['regression_results'][cache_key] = regression_result
        else:
            regression_result = None  # Invalid cache, recompute
    else:
        # Need to select features
        if use_fixed_features:
            # Fixed 3-feature mode
            feature_map = resolve_feature_columns(df)
            if feature_map is None:
                return None
            
            # Try to get the 3 fixed features
            feature_cols = []
            for feat_name in ['Temperature', 'Dew Point', 'Clearsky GHI']:
                if feat_name in feature_map:
                    feature_cols.append(feature_map[feat_name])
            
            if len(feature_cols) == 0:
                # Fallback to auto-select if fixed features not available
                if REGRESSION_ENGINE_AVAILABLE and auto_select_features:
                    # Get building columns to exclude from candidates
                    building_cols_list = get_building_columns(df)
                    method = "elasticnet" if selection_method == "ElasticNet (auto)" or selection_method == "elasticnet" else "correlation"
                    selection_result = select_weather_features(
                        df, building_col, feature_map, 
                        method=method, top_k=top_k, 
                        include_cloud_type=include_cloud_type,
                        building_cols=building_cols_list
                    )
                    feature_cols = selection_result.get('selected_features', [])
                    regression_result = {
                        'selection_result': selection_result,
                        'selected_features': feature_cols,
                        'method_used': 'auto_select_fallback',
                        'include_cloud_type': include_cloud_type
                    }
                else:
                    return None
            else:
                regression_result = {
                    'selected_features': feature_cols,
                    'method_used': 'fixed_3_feature',
                    'feature_mode': 'fixed_3_feature'
                }
        
        elif auto_select_features and REGRESSION_ENGINE_AVAILABLE:
            # Auto-select mode
            feature_map = resolve_feature_columns(df)
            if feature_map is None:
                return None
            
            # Get building columns to exclude from candidates
            building_cols_list = get_building_columns(df)
            
            # Map UI selection method to engine method
            method = "elasticnet" if selection_method == "ElasticNet (auto)" or selection_method == "elasticnet" else "correlation"
            selection_result = select_weather_features(
                df, building_col, feature_map, 
                method=method, top_k=top_k,
                include_cloud_type=include_cloud_type,
                building_cols=building_cols_list
            )
            feature_cols = selection_result.get('selected_features', [])
            
            # Safety check: filter out any building columns that slipped through
            feature_cols = [f for f in feature_cols if f not in building_cols_list]
            
            if len(feature_cols) == 0:
                return None
            
            # Fit regression to get metrics
            fit_result = fit_regression(df, building_col, feature_cols)
            if fit_result.get('error'):
                return None
            
            # Add candidate_features_df to fit_result for UI display
            fit_result['candidate_features'] = selection_result.get('candidate_features_df', pd.DataFrame())
            
            regression_result = {
                'selection_result': selection_result,
                'selected_features': feature_cols,
                'fit_result': fit_result,
                'method_used': method,
                'include_cloud_type': include_cloud_type,
                'feature_mode': 'auto_select'
            }
        
        else:
            # Fallback to fixed 3-feature if auto-select not available
            feature_map = resolve_feature_columns(df)
            if feature_map is None:
                return None
            
            feature_cols = []
            for feat_name in ['Temperature', 'Dew Point', 'Clearsky GHI']:
                if feat_name in feature_map:
                    feature_cols.append(feature_map[feat_name])
            
            if len(feature_cols) == 0:
                return None
            
            regression_result = {
                'selected_features': feature_cols,
                'method_used': 'fixed_3_feature_fallback',
                'feature_mode': 'fixed_3_feature'
            }
        
        # Cache regression results
        st.session_state['regression_results'][cache_key] = regression_result
    
    # Final safety check: ensure all feature_cols exist in df
    # Resolve any canonical names to df column names
    feature_cols = resolve_feature_names_to_df_cols(feature_cols, df)
    
    # Remove any features that don't exist in df (with warning)
    missing_features = [f for f in feature_cols if f not in df.columns]
    if missing_features:
        import warnings
        warnings.warn(f"Features not found in dataframe, dropping: {missing_features}")
        feature_cols = [f for f in feature_cols if f in df.columns]
    
    # Must have at least 1 feature
    if len(feature_cols) == 0:
        return None
    
    # Prepare data - include hour_datetime to ensure it's in result
    # Verify all columns exist before indexing
    required_cols = [building_col] + feature_cols + ['hour_datetime']
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        return None  # Critical columns missing
    
    data = df[required_cols].dropna()
    if len(data) < 10:
        return None
    
    X = data[feature_cols].values
    y = data[building_col].values
    
    # Use cached predictions if available, otherwise fit model
    if regression_result and 'fit_result' in regression_result and regression_result['fit_result'].get('y_pred') is not None:
        # Use predictions from regression engine (aligned with original df)
        y_pred_full = regression_result['fit_result']['y_pred']
        # Get predictions for the non-missing rows
        y_pred = y_pred_full[data.index]
        # Filter out NaN predictions
        valid_mask = ~np.isnan(y_pred)
        if valid_mask.sum() < 10:
            # Fallback to simple linear regression
            model = fit_model(X, y)
            y_pred = model.predict(X)
        else:
            y_pred = y_pred[valid_mask]
            y = y[valid_mask]
            data = data.iloc[valid_mask]
    else:
        # Fit model and predict (fallback)
        model = fit_model(X, y)
        y_pred = model.predict(X)
    
    residuals = y - y_pred
    
    # Compute z-scores
    resid_std = np.std(residuals)
    z_scores = np.zeros_like(residuals) if resid_std == 0 else (residuals - np.mean(residuals)) / resid_std
    anomaly_flags = np.abs(z_scores) > z_threshold
    
    # Build result dataframe with ALL required columns
    result_df = pd.DataFrame({
        building_col: data[building_col].values,
        'hour_datetime': data['hour_datetime'].values,  # CRITICAL: must be valid datetime
        'predicted': y_pred,
        'residual': residuals,
        'z_score': z_scores,
        'anomaly': anomaly_flags,
        'abs_z': np.abs(z_scores),
        'abs_residual': np.abs(residuals),
    })
    
    # Add Cloud_Type if available
    cloud_col = None
    for col in ['Cloud_Type', 'Cloud Type', 'CloudType']:
        if col in df.columns:
            cloud_col = col
            break
    if cloud_col:
        if cloud_col in data.columns:
            result_df['Cloud_Type'] = data[cloud_col].values
        else:
            result_df['Cloud_Type'] = df.loc[data.index, cloud_col].values
    
    return result_df


# =========================
# UI
# =========================

# Sidebar Header
st.sidebar.markdown(f"""
<div style='padding: 1rem 0; border-bottom: 1px solid #2d2d44; margin-bottom: 1.5rem;'>
    <h2 style='color: #ffffff; margin: 0; font-size: 1.5rem;'>{svg_icon('sliders', size=20)} Controls</h2>
</div>
""", unsafe_allow_html=True)

# Get authoritative city list (OpenEI dataset only)
city_resources = get_openei_cities()
valid_cities = sorted(city_resources.keys()) if city_resources else []

if not valid_cities:
    st.sidebar.error("❌ No cities found in OpenEI submission 515")
    st.sidebar.info("Please check your internet connection and try again.")
    st.stop()

# Ensure all OpenEI cities have coordinates (add defaults if missing)
if NSRDB_AVAILABLE and ensure_city_coordinates:
    for city in valid_cities:
        ensure_city_coordinates(city)

# Create display names for dropdown (show "City State" format)
city_display_map = {city: city_resources[city]["display"] for city in valid_cities}
city_options = [city_resources[city]["display"] for city in valid_cities]

selected_display = st.sidebar.selectbox("Select City", city_options, key="selected_city_display")

# Get clean city key from display name
selected_city = None
for city_key, city_info in city_resources.items():
    if city_info["display"] == selected_display:
        selected_city = city_key
        break

if selected_city is None:
    st.sidebar.error("❌ Invalid city selection")
    st.stop()

city_lower = selected_city.lower()

# Validate required files exist
load_file_exists, has_merged_file, load_file_path, merged_file = validate_city_files(selected_city)

# Check if city has coordinates for weather download (try CITY_COORDS first, then fallback)
has_coordinates = False
coords_resolved_via_fallback = False
if NSRDB_AVAILABLE:
    if city_lower in CITY_COORDS:
        has_coordinates = True
    elif resolve_city_coords_fallback:
        # Try fallback geocoding
        coords = resolve_city_coords_fallback(selected_city)
        if coords is not None:
            has_coordinates = True
            coords_resolved_via_fallback = True

# Auto-download load profile if missing
if not load_file_exists:
    st.sidebar.markdown("---")
    status_container = st.sidebar.empty()
    
    # Get download URL from OpenEI resources
    if selected_city in city_resources:
        download_url = city_resources[selected_city]["url"]
        
        status_container.info(f"📥 Load profile not found. Downloading from OpenEI...")
        
        try:
            from openei_loader import download_load_profile
            
            # Determine destination path
            load_profiles_dir = PROJECT_ROOT / "LoadProfiles"
            dest_path = load_profiles_dir / f"{selected_city}_SimulatedLoadProfile.csv"
            
            def progress_callback(year, message):
                if message:
                    status_container.info(f"📥 {message}")
            
            success, message = download_load_profile(selected_city, download_url, dest_path, progress_callback)
            
            if success:
                status_container.success(f"✅ Load profile downloaded: {dest_path.name}")
                # Update file paths
                load_file_exists = True
                load_file_path = dest_path
                # Small delay then continue
                import time
                time.sleep(0.5)
            else:
                status_container.error(f"❌ {message}")
                st.stop()
        except Exception as e:
            status_container.error(f"❌ Error downloading load profile: {e}")
            st.stop()
    else:
        st.sidebar.error(f"❌ Download URL not found for {selected_city}")
        st.sidebar.info("This city may not be available in OpenEI submission 515.")
        st.stop()

# If merged file exists, allow loading even without coordinates
if has_merged_file:
    # Continue to load the existing merged file (coordinates not required)
    pass
# Automatically download and build if merged file doesn't exist
# Only if city has coordinates configured
elif not has_merged_file and NSRDB_AVAILABLE and has_coordinates:
    st.sidebar.markdown("---")
    status_container = st.sidebar.empty()

    from nsrdb_downloader import get_nsrdb_api_key, NSRDB_EMAIL
    api_key = get_nsrdb_api_key()
    nsrdb_email = NSRDB_EMAIL

    status_container.info(f"📥 No merged dataset found for {selected_city}. Downloading weather data...")

    progress_messages = []

    def progress_callback(year, message):
        if year is not None:
            progress_messages.append(f"Year {year}: {message}")
        else:
            progress_messages.append(message)

        status_text = "\n".join(progress_messages[-3:])
        status_container.info(f"📥 {status_text}")

    try:
        success, message, weather_df = fetch_nsrdb_weather(
            selected_city,
            api_key=api_key,
            email=nsrdb_email,
            project_root=PROJECT_ROOT,
            progress_callback=progress_callback
        )

        if success and weather_df is not None:
            status_container.success("✅ Weather data downloaded")
            status_container.info("🔄 Merging load profile with weather data...")

            # Show progress
            status_container.info("🔄 Aggregating load profile to hourly...")
            
            build_success, build_message = build_and_save_merged(
                selected_city,
                project_root=PROJECT_ROOT,
                use_nsrdb=True,
                weather_df=weather_df,
                load_file_path=load_file_path if load_file_exists else None
            )

            if build_success:
                status_container.success(f"✅ Merged dataset created: {city_lower}_load_weather_merged.csv")
                # Clear all caches to ensure fresh load
                load_data.clear()
                load_merged_data.clear()
                # Set flag for auto-run detection if enabled
                st.session_state['just_merged'] = True
                # Small delay to show success message
                import time
                time.sleep(0.5)
                st.rerun()
            else:
                status_container.error(f"❌ {build_message}")
                st.stop()
        else:
            status_container.error(f"❌ {message}")
            st.stop()

    except Exception as e:
        status_container.error(f"❌ Error: {str(e)}")
        st.stop()

elif not has_merged_file:
    st.sidebar.markdown("---")
    if city_lower == "chicago":
        st.sidebar.error("❌ Chicago requires chicago_load_weather_merged.csv")
        st.sidebar.error("This file is mandatory and cannot be auto-created.")
        st.sidebar.info("Please ensure chicago_load_weather_merged.csv exists in the project root.")
        st.stop()
    elif not NSRDB_AVAILABLE:
        st.sidebar.error("⚠️ NSRDB modules not available")
        st.sidebar.info("Cannot download weather data. Please install required modules.")
        st.stop()
    elif coords_resolved_via_fallback:
        # Show small info message when fallback succeeds
        st.sidebar.info(f"ℹ️ Coordinates auto-resolved for '{selected_city}' and cached locally.")
    elif not has_coordinates:
        st.sidebar.warning(f"⚠️ Weather download not configured (missing coordinates)")
        st.sidebar.info(f"City '{selected_city}' is in OpenEI list but coordinates are not configured in CITY_COORDS.")
        st.sidebar.info(f"To enable weather download, add coordinates for '{selected_city}' to CITY_COORDS in nsrdb_downloader.py")
        st.sidebar.error(f"❌ No merged dataset found and weather download is not available.")
        st.sidebar.info(f"Expected file: {merged_file.name}")
        st.stop()
    elif coords_resolved_via_fallback:
        # Show small info message when fallback succeeds
        st.sidebar.info(f"ℹ️ Coordinates auto-resolved for '{selected_city}' and cached locally.")
    else:
        st.sidebar.warning(f"⚠️ No merged dataset found for {selected_city}")
        st.sidebar.info(f"Expected file: {merged_file.name}")
        st.stop()

# Load data with debug information
with st.spinner(f"Loading data for {selected_city}..."):
    result = load_data(selected_city)

# Handle load result (can be (df, True), (None, False), or (None, error_string))
if isinstance(result, tuple) and len(result) == 2:
    df, status = result
    if df is None:
        # Show debug information for failed load
        st.error(f"❌ Failed to load data for {selected_city}")
        
        # Debug block
        merged_file = PROJECT_ROOT / f"{city_lower}_load_weather_merged.csv"
        st.code(f"Expected file: {merged_file}\nFile exists: {merged_file.exists()}")
        
        if isinstance(status, str):
            st.error(f"Error: {status}")
        elif city_lower == "chicago":
            st.error("Chicago requires chicago_load_weather_merged.csv. This file is mandatory and cannot be rebuilt.")
            st.info("Please ensure chicago_load_weather_merged.csv exists in the project root.")
        else:
            st.info("For non-Chicago cities, the merged file will be auto-created on first selection.")
        
        # Enhanced debug output when loading fails (always show on error)
        with st.expander("🔍 Debug Information", expanded=True):
            st.markdown("**Load Failure Details:**")
            st.code(f"Merged file exists: {merged_file.exists()}")
            
            if merged_file.exists():
                try:
                    debug_df = pd.read_csv(merged_file, nrows=100)
                    st.code(f"Columns in file (first 15): {list(debug_df.columns)[:15]}")
                    
                    if 'hour_datetime' in debug_df.columns:
                        st.code(f"hour_datetime dtype (raw): {debug_df['hour_datetime'].dtype}")
                        st.code(f"First 5 values (raw): {debug_df['hour_datetime'].head(5).tolist()}")
                        
                        # Try parsing to see what happens
                        parsed_test = pd.to_datetime(debug_df['hour_datetime'], errors='coerce')
                        nat_count_test = parsed_test.isna().sum()
                        st.code(f"NaT count after flexible parse: {nat_count_test} / {len(debug_df)}")
                        
                        if nat_count_test > len(debug_df) * 0.1:
                            # Try SAS format
                            parsed_sas = pd.to_datetime(debug_df['hour_datetime'], errors='coerce', format='%d%b%Y:%H:%M:%S')
                            nat_count_sas = parsed_sas.isna().sum()
                            st.code(f"NaT count after SAS format parse: {nat_count_sas} / {len(debug_df)}")
                    else:
                        st.code(f"hour_datetime column NOT FOUND in file")
                except Exception as e:
                    st.code(f"Could not read file for debugging: {e}")
            else:
                st.code(f"File does not exist: {merged_file}")
        
        st.stop()
    
    # Validate hour_datetime after load (standardize_datetime already did this, but double-check)
    if 'hour_datetime' not in df.columns:
        st.error("❌ hour_datetime column missing after load")
        st.code(f"Available columns: {list(df.columns)[:20]}")
        st.stop()
    
    # Validate datetime type and no NaT (standardize_datetime should have handled this, but verify)
    if not pd.api.types.is_datetime64_any_dtype(df['hour_datetime']):
        st.error(f"❌ hour_datetime is not datetime type: {df['hour_datetime'].dtype}")
        st.stop()
    
    nat_count = df['hour_datetime'].isna().sum()
    if nat_count > 0:
        st.error(f"❌ hour_datetime contains {nat_count} NaT values after parsing")
        st.code(f"hour_datetime dtype: {df['hour_datetime'].dtype}\nNaT sample rows:\n{df[df['hour_datetime'].isna()].head(3)}")
        st.stop()
else:
    st.error("❌ Unexpected load_data return format")
    st.stop()

building_cols = get_building_columns(df)
if not building_cols:
    st.error("No building columns found in data.")
    st.stop()

# Status Panel
sidebar_section_header("Status", "activity")

# Status indicators in a content card (only render if we have status items)
status_items = []
if load_file_exists:
    status_items.append(("Load Profile", "✅ Available", "success"))
else:
    status_items.append(("Load Profile", "❌ Missing", "error"))

if has_merged_file:
    status_items.append(("Merged Dataset", "✅ Ready", "success"))
else:
    status_items.append(("Merged Dataset", "⏳ Building...", "warning"))

if has_coordinates:
    status_items.append(("Coordinates", "✅ Configured", "success"))
else:
    status_items.append(("Coordinates", "⚠️ Not set", "warning"))

# Add regression features status (will be updated after detection runs)
# Note: selected_building is defined later in sidebar, so we use session_state with safe default
if 'regression_results' in st.session_state and len(st.session_state['regression_results']) > 0:
    # Get selected_building from session_state with safe default (first building if available)
    current_selected_building = st.session_state.get("selected_building", building_cols[0] if len(building_cols) > 0 else None)
    if current_selected_building:
        # Try to get latest regression result for confidence badge
        dataset_signature = (
            len(df),
            df['hour_datetime'].min() if 'hour_datetime' in df.columns else None,
            df['hour_datetime'].max() if 'hour_datetime' in df.columns else None
        )
        # Derive feature mode from session_state (sidebar widgets set this)
        current_feature_mode = st.session_state.get('feature_mode', 'Auto-select (ElasticNet)')
        is_fixed = (current_feature_mode == "Fixed 3-feature")
        current_selection_method = "ElasticNet (auto)" if current_feature_mode == "Auto-select (ElasticNet)" else "Correlation top-k"
        current_top_k = st.session_state.get('top_k_features', 3)
        current_include_cloud = st.session_state.get('include_cloud_type', False)
        feature_mode_key = "fixed" if is_fixed else f"{current_selection_method}_k{current_top_k}_cloud{current_include_cloud}"
        # Get selected_year from session_state with safe default
        current_selected_year = st.session_state.get("selected_year", "All")
        cache_key = (current_selected_building, current_selected_year, feature_mode_key, dataset_signature)
        reg_result = st.session_state['regression_results'].get(cache_key)
        if reg_result and 'fit_result' in reg_result and reg_result['fit_result'].get('metrics'):
            r2 = reg_result['fit_result']['metrics'].get('r2', 0)
            from regression_engine import get_regression_confidence
            confidence = get_regression_confidence(r2)
            status_items.append(("Regression Fit", confidence['badge'], "success" if confidence['level'] in ['Strong', 'Moderate'] else "warning"))
        else:
            status_items.append(("Regression Features", "✅ Ready", "success"))
    else:
        status_items.append(("Regression Features", "✅ Ready", "success"))
else:
    status_items.append(("Regression Features", "✅ Ready", "success"))

# Only render card if we have status items - build content as HTML string first
if status_items:
    status_html = "<div class='sidebar-content-card'>"
    for label, status, status_type in status_items:
        color = "#22c55e" if status_type == "success" else "#fbbf24" if status_type == "warning" else "#ef4444"
        # Extract checkmark/icon and status text separately for alignment
        status_parts = status.split(" ", 1) if " " in status else (status, "")
        icon = status_parts[0] if len(status_parts) > 0 else ""
        status_text = status_parts[1] if len(status_parts) > 1 else ""
        # Use grid layout: label column | fixed-width icon column | text column
        # All icons will align in the same column
        status_html += f"<div style='display: grid; grid-template-columns: auto 1.8em 1fr; gap: 0.5rem; align-items: center; margin: 0.5rem 0;'><span style='color: #aaa;'>{label}:</span><span style='color: {color}; text-align: left;'>{icon}</span><span style='color: {color}; font-weight: 500;'>{status_text}</span></div>"
    status_html += "</div>"
    st.sidebar.markdown(status_html, unsafe_allow_html=True)

sidebar_section_header("Building Selection", "building")

selected_building = st.sidebar.selectbox("Building Type", building_cols, label_visibility="collapsed", key="selected_building")

sidebar_section_header("Detection Parameters", "target")

z_threshold = st.sidebar.slider("Z-Threshold", 1.0, 5.0, 2.0, 0.1, help="Controls sensitivity: higher = fewer anomalies detected", key="z_threshold")
top_n = st.sidebar.number_input("Top-N per Year", 1, 500, 50, 1, help="Number of top anomalies to show per year", key="top_n")

df_years = df['hour_datetime'].dt.year.dropna().astype(int)
year_options = ["All"] + sorted(df_years.unique().tolist())
selected_year = st.sidebar.selectbox("Filter Year", year_options, index=0, help="Filter analysis to specific year", key="selected_year")

# Regression Model Configuration
sidebar_section_header("Regression Model", "target")

# Single radio selector for feature mode (replaces mutually-exclusive checkboxes)
feature_mode = st.sidebar.radio(
    "Feature Mode",
    ["Auto-select (ElasticNet)", "Auto-select (Correlation Top-K)", "Fixed 3-feature"],
    index=0,
    help="How to select regression features",
    key="feature_mode"
)

# Parse feature mode
auto_select_features = feature_mode.startswith("Auto-select")
use_fixed_features = (feature_mode == "Fixed 3-feature")
selection_method = "ElasticNet (auto)" if feature_mode == "Auto-select (ElasticNet)" else "Correlation top-k"

# Top-K slider (only for Correlation Top-K mode)
top_k_features = 3
if feature_mode == "Auto-select (Correlation Top-K)":
    top_k_features = st.sidebar.slider(
        "Top-K Features",
        2, 6, 3, 1,
        help="Number of top features to select by correlation",
        key="top_k_features"
    )

# Include Cloud_Type checkbox (only for auto-select modes)
include_cloud_type = False
if auto_select_features and REGRESSION_ENGINE_AVAILABLE:
    include_cloud_type = st.sidebar.checkbox(
        "Include Cloud_Type feature",
        value=False,
        help="Include Cloud_Type as a regression feature (categorical, may not improve model)",
        key="include_cloud_type"
    )

# Insights Configuration Section
sidebar_section_header("Insights", "sparkles")

enable_insights = st.sidebar.checkbox("Enable Insights & Actions", value=True, help="Show insights tab with explanations and recommendations", key="enable_insights")
enable_recurrence = st.sidebar.checkbox("Enable Recurrence Analysis", value=True, help="Analyze recurring patterns in anomalies", key="enable_recurrence")
enable_cost_estimates = st.sidebar.checkbox("Enable Cost Estimates", value=False, help="Show cost impact estimates (requires load units ≈ kWh)", key="enable_cost_estimates")

# Cost rate input (only if cost estimates enabled)
electricity_rate = 0.12
if enable_cost_estimates:
    electricity_rate = st.sidebar.number_input("Electricity Rate ($/kWh)", 0.01, 1.0, 0.12, 0.01, help="Default: $0.12/kWh", key="electricity_rate")

# AI Summary toggle (optional, fallback to heuristic)
enable_ai_summary = st.sidebar.checkbox("Enable AI Summary", value=False, help="Use OpenAI for enhanced summaries (requires API key)", key="enable_ai_summary")
openai_api_key = None
if enable_ai_summary:
    openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password", help="Leave empty to use environment variable OPENAI_API_KEY", key="openai_api_key")
    if not openai_api_key:
        import os
        openai_api_key = os.getenv('OPENAI_API_KEY')

# Developer Mode Toggle
sidebar_section_header("Advanced", "wrench")

developer_mode = st.sidebar.checkbox("Developer Mode", value=False, help="Show debug information and technical details", key="developer_mode")

# Regression Ready Validator (after sidebar widgets are created)
feature_map = resolve_feature_columns(df)
# Derive use_fixed from feature_mode (defined in sidebar above)
current_feature_mode = st.session_state.get('feature_mode', 'Auto-select (ElasticNet)')
use_fixed = (current_feature_mode == "Fixed 3-feature")

if use_fixed:
    # Fixed mode: require the 3 traditional features
    if feature_map is None:
        missing_features = []
        for canonical, variants in FEATURE_MAP.items():
            if not any(v in df.columns for v in variants):
                missing_features.append(canonical)
        st.markdown("""
        <div style='background: linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(220, 38, 38, 0.1) 100%); 
                    border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 12px; padding: 2rem; margin: 2rem 0;'>
            <h2 style='color: #ef4444; margin-bottom: 1rem;'>❌ Regression Features Missing</h2>
            <p style='color: #aaa; margin-bottom: 1rem;'>Required features: <strong style='color: #fff;'>Temperature, Dew Point, Clearsky GHI</strong></p>
            <p style='color: #ef4444;'>Missing: {}</p>
            <p style='color: #888; font-size: 0.9rem; margin-top: 1rem;'>Available columns: {}</p>
        </div>
        """.format(', '.join(missing_features), ", ".join(df.columns[:20].tolist())), unsafe_allow_html=True)
        
        # Show debug info automatically when features are missing
        with st.expander("🔍 Feature Mapping Debug", expanded=True):
            st.markdown("**Missing Features:**")
            st.error(f"Missing: {', '.join(missing_features)}")
            st.markdown("**Available Columns:**")
            st.code(", ".join(df.columns[:20].tolist()))
            st.markdown("**Expected Feature Variants:**")
            for canonical, variants in FEATURE_MAP.items():
                st.code(f"{canonical}: {', '.join(variants)}")
        
        st.stop()
else:
    # Auto-select mode: check if we have any candidate features
    if REGRESSION_ENGINE_AVAILABLE:
        building_cols_list = get_building_columns(df)
        candidate_info = get_candidate_weather_features(df, building_cols=building_cols_list)
        # Compatibility shim: support both 'candidates' (old) and 'candidate_features' (new) keys
        candidate_features_list = candidate_info.get('candidate_features', candidate_info.get('candidates', []))
        if len(candidate_features_list) == 0:
            st.error("❌ No candidate weather features found for regression. Please ensure weather data is available.")
            st.info("Available columns: " + ", ".join(df.columns[:20].tolist()))
            st.stop()
    else:
        # Fallback: require fixed features if regression engine not available
        if feature_map is None:
            st.error("❌ Regression engine not available and fixed features missing. Please install regression_engine.py or ensure weather data is available.")
            st.stop()

# Apply year filter BEFORE anomaly detection (affects all subsequent analysis)
if selected_year != "All":
    df = df[df['hour_datetime'].dt.year == int(selected_year)].copy()

sidebar_section_header("Data Summary", "database")

st.sidebar.markdown("""
<div class='sidebar-content-card'>
    <div style='color: #aaa; font-size: 0.9rem; line-height: 1.6;'>
        <div>Rows: <strong style='color: #fff;'>{:,}</strong></div>
        <div>Buildings: <strong style='color: #fff;'>{}</strong></div>
    </div>
</div>
""".format(len(df), len(building_cols)), unsafe_allow_html=True)

# Run Detection Section
sidebar_section_header("Run Detection", "rocket")

# Run Detection controls - checkbox and description without card wrapper
# (Streamlit widgets don't render properly inside HTML div wrappers)
auto_run_detection = st.sidebar.checkbox("Auto-run after merge", value=False, help="Automatically run detection after dataset merge (may be slow)", key="auto_run_detection")

st.sidebar.markdown("""
<p style='color: #888; font-size: 0.85rem; margin: 0.5rem 0;'>Fits regression models and identifies anomalies across all buildings.</p>
""", unsafe_allow_html=True)

# Auto-run detection if checkbox is enabled and we just merged
if auto_run_detection and 'just_merged' in st.session_state and st.session_state['just_merged']:
    st.session_state['just_merged'] = False
    # Trigger detection automatically
    run_detection = True
else:
    # Check if detection is already running
    is_running = st.session_state.get("is_running", False)
    
    # Disable sidebar widgets if running
    if is_running:
        st.sidebar.info("⏳ Detection in progress...")
        st.sidebar.button("🔍 Run Anomaly Detection", type="primary", use_container_width=True, key="run_anomaly_detection", disabled=True)
        run_detection = False
    else:
        run_detection = st.sidebar.button("🔍 Run Anomaly Detection", type="primary", use_container_width=True, key="run_anomaly_detection")

if run_detection:
    # Set running flag
    st.session_state["is_running"] = True
    
    try:
        all_anomalies = {}
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, building in enumerate(building_cols):
            status_text.text(f"Processing {building}... ({i+1}/{len(building_cols)})")
            result = detect_anomalies(
                df, 
                building, 
                z_threshold,
                use_fixed_features=use_fixed_features,
                auto_select_features=auto_select_features,
                selection_method=selection_method,
                top_k=top_k_features,
                include_cloud_type=include_cloud_type,
                selected_year=selected_year
            )
            if result is not None:
                all_anomalies[building] = result
            progress_bar.progress((i + 1) / len(building_cols))

        progress_bar.empty()
        status_text.empty()

        if not all_anomalies:
            st.markdown("""
        <div style='background: linear-gradient(135deg, rgba(30, 30, 46, 0.8) 0%, rgba(37, 37, 56, 0.8) 100%); 
                    border: 1px solid #2d2d44; border-radius: 12px; padding: 3rem; text-align: center; margin: 2rem 0;'>
            <h2 style='color: #ffffff; margin-bottom: 1rem;'>⚠️ No Anomalies Detected</h2>
            <p style='color: #888; font-size: 1.1rem; margin-bottom: 1.5rem;'>
                No anomalies were found with the current parameters. This could indicate:
            </p>
            <ul style='color: #aaa; text-align: left; display: inline-block; margin: 0 auto;'>
                <li>Data quality is excellent (low variance in residuals)</li>
                <li>Z-threshold may be too high (try lowering it)</li>
                <li>Regression features may need adjustment</li>
                <li>Year filter may be too restrictive</li>
            </ul>
            <p style='color: #888; margin-top: 1.5rem;'>
                <strong>Suggestions:</strong> Try lowering the Z-threshold or selecting a different year/building.
            </p>
        </div>
        """, unsafe_allow_html=True)
            
            # Show debug info automatically when detection fails
            with st.expander("🔍 Debug Information", expanded=True):
                st.markdown("**Detection Failure Details:**")
                st.code(f"Buildings processed: {len(building_cols)}")
                st.code(f"Z-threshold: {z_threshold}")
                st.code(f"Year filter: {selected_year}")
                feature_map = resolve_feature_columns(df)
                if feature_map:
                    st.markdown("**Feature Columns:**")
                    for canonical, actual in feature_map.items():
                        st.code(f"{canonical} → {actual}")
                else:
                    st.error("Feature map unavailable")
                st.info("Available columns: " + ", ".join(df.columns[:20].tolist()))
            
            st.stop()
        else:
            st.session_state['all_anomalies'] = all_anomalies
        # Note: selected_building is managed by Streamlit via the widget key="selected_building"
        # Do not assign to st.session_state['selected_building'] as it's automatically managed
    finally:
        # Clear running flag
        st.session_state["is_running"] = False

if 'all_anomalies' in st.session_state:
    all_anomalies = st.session_state['all_anomalies']
    # Read selected_building from the widget's session state (managed by Streamlit via key="selected_building")
    # Use .get() with safe default (first building) to avoid any potential KeyError
    # Do NOT write to st.session_state["selected_building"] as it's automatically managed by the widget
    selected_building = st.session_state.get("selected_building", building_cols[0] if len(building_cols) > 0 else None)

    if selected_building not in all_anomalies:
        st.warning(f"Results not available for {selected_building}. Please run detection again.")
        st.stop()

    result_df = all_anomalies[selected_building]
    
    # For Data Quality: use original df's feature_map (result_df doesn't contain weather columns)
    # feature_map was already resolved during data loading and validation
    # This ensures we can calculate weather metrics correctly

    # KPI Metrics Row
    st.markdown(f"""
    <div style='margin: 2rem 0;'>
        <h2 style='color: #ffffff; margin-bottom: 1.5rem;'>
            {svg_icon('dashboard', size=20)}
            Key Metrics
        </h2>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    total_hours = len(result_df)
    anomaly_hours = result_df['anomaly'].sum()
    anomaly_rate = (anomaly_hours / total_hours * 100) if total_hours > 0 else 0
    avg_z = result_df['abs_z'].mean()

    with col1:
        st.markdown(f"""
        <div class='metric-card'>
            <div style='color: #888; font-size: 0.9rem; margin-bottom: 0.5rem;'>Total Hours</div>
            <div style='color: #ffffff; font-size: 2rem; font-weight: 700;'>{total_hours:,}</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class='metric-card'>
            <div style='color: #888; font-size: 0.9rem; margin-bottom: 0.5rem;'>Anomaly Hours</div>
            <div style='color: #ef4444; font-size: 2rem; font-weight: 700;'>{anomaly_hours:,}</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class='metric-card'>
            <div style='color: #888; font-size: 0.9rem; margin-bottom: 0.5rem;'>Anomaly Rate</div>
            <div style='color: #fbbf24; font-size: 2rem; font-weight: 700;'>{anomaly_rate:.2f}%</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class='metric-card'>
            <div style='color: #888; font-size: 0.9rem; margin-bottom: 0.5rem;'>Avg |Z-Score|</div>
            <div style='color: #6366f1; font-size: 2rem; font-weight: 700;'>{avg_z:.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    # Tabs for different views (clean text, icons shown inside each tab)
    tab_labels = ["Overview"]
    if enable_insights:
        tab_labels.append("Insights & Actions")
    tab_labels.append("Regression")
    tab_labels.extend(["Drilldown", "Top Anomalies"])
    
    tabs = st.tabs(tab_labels)
    tab1 = tabs[0]
    tab_idx = 1
    if enable_insights:
        tab_insights = tabs[tab_idx]
        tab_idx += 1
    tab_regression = tabs[tab_idx]
    tab_idx += 1
    tab2 = tabs[tab_idx]
    tab3 = tabs[tab_idx + 1]

    with tab1:
        section_header("Top-N Severity Summary (All Buildings)", "bar-chart", "Aggregated anomaly statistics by year across all building types")
        
        top_anomalies_all = []

        for building, building_result in all_anomalies.items():
            top_n_building = building_result.nlargest(top_n, 'abs_z')
            for _, row in top_n_building.iterrows():
                top_anomalies_all.append({
                    'Building': building,
                    'DateTime': row['hour_datetime'],
                    'Actual': row[building],
                    'Predicted': row['predicted'],
                    'Residual': row['residual'],
                    'Z-Score': row['z_score'],
                    '|Z-Score|': row['abs_z'],
                    '|Residual|': row['abs_residual'],
                    'Cloud_Type': row.get('Cloud_Type', 'N/A')
                })

        top_anomalies_df = pd.DataFrame(top_anomalies_all)

        if len(top_anomalies_df) > 0:
            # Ensure DateTime is datetime type for year extraction
            top_anomalies_df['DateTime'] = pd.to_datetime(top_anomalies_df['DateTime'], errors='coerce')
            top_anomalies_df = top_anomalies_df.dropna(subset=['DateTime'])  # Remove any invalid dates
            top_anomalies_df['Year'] = top_anomalies_df['DateTime'].dt.year
            yearly_summary = top_anomalies_df.groupby('Year').agg({
                '|Z-Score|': ['mean', 'max'],
                '|Residual|': 'mean'
            }).reset_index()
            yearly_summary.columns = ['Year', 'Avg Z-Score', 'Max Z-Score', 'Avg Residual']
            st.dataframe(yearly_summary.round(3), use_container_width=True, height=400)
        
        # Data Quality Section (always show, even if no anomalies)
        section_header("Data Quality", "shield-check")
        
        quality_col1, quality_col2, quality_col3 = st.columns(3)
        with quality_col1:
            date_range_start = result_df['hour_datetime'].min()
            date_range_end = result_df['hour_datetime'].max()
            st.metric("Date Range", f"{date_range_start.strftime('%Y-%m-%d')} to {date_range_end.strftime('%Y-%m-%d')}")
        with quality_col2:
            # Use resolved feature columns from original df for missing weather calculation
            # result_df doesn't contain weather columns, so we use the original df filtered to match result_df's time range
            if feature_map:
                # Filter original df to match result_df's time range
                df_filtered = df[df['hour_datetime'].isin(result_df['hour_datetime'])]
                # Calculate missingness across all weather features
                weather_cols = [feature_map['Temperature'], feature_map['Dew Point'], feature_map['Clearsky GHI']]
                # Only use columns that exist in df
                available_weather_cols = [col for col in weather_cols if col in df_filtered.columns]
                if available_weather_cols:
                    missing_counts = [df_filtered[col].isna().sum() for col in available_weather_cols]
                    total_missing = sum(missing_counts)
                    total_cells = len(df_filtered) * len(available_weather_cols)
                    missing_pct = (total_missing / total_cells * 100) if total_cells > 0 else 0
                else:
                    missing_pct = 100.0  # All missing if no columns found
            else:
                missing_pct = 100.0  # Can't calculate if feature map unavailable
            st.metric("Missing Weather", f"{missing_pct:.1f}%")
        with quality_col3:
            # Use resolved feature columns for completeness (from original df filtered to result_df time range)
            if feature_map:
                feature_cols = [feature_map['Temperature'], feature_map['Dew Point'], feature_map['Clearsky GHI']]
                # Filter original df to match result_df's time range
                df_filtered = df[df['hour_datetime'].isin(result_df['hour_datetime'])]
                # Only include columns that exist in df
                available_feature_cols = [col for col in feature_cols if col in df_filtered.columns]
                if available_feature_cols and selected_building in df_filtered.columns:
                    complete_rows = df_filtered[available_feature_cols + [selected_building]].dropna().shape[0]
                    completeness = (complete_rows / len(df_filtered) * 100) if len(df_filtered) > 0 else 0
                else:
                    completeness = 0
            else:
                completeness = 0
            st.metric("Data Completeness", f"{completeness:.1f}%")
        
        # Show warning if features are missing
        show_debug_auto = False
        if not feature_map:
            show_debug_auto = True
            st.markdown("""
            <div style='background: rgba(251, 191, 36, 0.1); border-left: 4px solid #fbbf24; border-radius: 6px; padding: 1rem; margin: 1rem 0;'>
                <p style='color: #fbbf24; margin: 0;'><strong>⚠️ Warning:</strong> Some regression features are missing. Data quality metrics may be incomplete.</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Debug chip: show automatically if errors, or if Developer Mode is ON
        if show_debug_auto or developer_mode:
            with st.expander("🔍 Feature Mapping Debug", expanded=show_debug_auto):
                if feature_map:
                    st.markdown("**Resolved Feature Columns:**")
                    for canonical, actual in feature_map.items():
                        st.code(f"{canonical} → {actual}")
                    missing_features = [k for k in FEATURE_MAP.keys() if k not in feature_map]
                    if missing_features:
                        st.warning(f"Missing features: {', '.join(missing_features)}")
                    else:
                        st.success("All required features found")
                else:
                    st.error("Could not resolve feature columns")
                    st.info("Available columns: " + ", ".join(df.columns[:20].tolist()))

    # Insert Insights tab if enabled
    if enable_insights:
        with tab_insights:
            if not INSIGHTS_AVAILABLE:
                st.error("Insights module not available. Please ensure insights.py is in the project directory.")
            else:
                try:
                    # Executive Summary
                    # Generate patterns for summary
                    patterns = detect_recurring_patterns(result_df) if enable_recurrence else {}
                    
                    # Generate executive summary
                    summary_points = generate_executive_summary(result_df, selected_building, selected_year, patterns, feature_map)
                    
                    # Only render card if we have summary points
                    if summary_points and len(summary_points) > 0:
                        # Build body content
                        body_html = ""
                        for point in summary_points:
                            # Replace emojis with SVG icons
                            point_with_icons = replace_emoji_with_icon(point)
                            body_html += f"<p style='margin: 0.3rem 0;'>{point_with_icons}</p>"
                        
                        section_card("Executive Summary", body_html, "lightbulb", "#f59e0b", "default")
                    
                    # Inferred Operating Behavior
                    try:
                        from occupancy_insights import generate_occupancy_insights
                        
                        # Only show if anomalies exist
                        if 'anomaly' in result_df.columns and result_df['anomaly'].sum() > 0:
                            occupancy_data = generate_occupancy_insights(df, result_df, selected_building)
                            
                            # Only show if confidence is not Low
                            if occupancy_data.get("overall_confidence") != "Low":
                                insights = occupancy_data.get("insights", [])
                                recommendations = occupancy_data.get("recommendations", [])
                                
                                # Inferred Operating Behavior card
                                if insights and len(insights) > 0:
                                    body_html = ""
                                    for insight in insights:
                                        body_html += f"<p style='margin: 0.3rem 0;'>• {insight}</p>"
                                    section_card("Inferred Operating Behavior", body_html, "clock", "#3b82f6", "default")
                                
                                # Recommended Actions card
                                if recommendations and len(recommendations) > 0:
                                    body_html = ""
                                    for rec in recommendations:
                                        body_html += f"<p style='margin: 0.3rem 0;'>• {rec}</p>"
                                    section_card("Recommended Actions", body_html, "clipboard-check", "#22c55e", "success")
                        # If confidence is Low or no anomalies, section is hidden (no rendering)
                    except ImportError:
                        # Module not available, skip silently
                        pass
                    except Exception as e:
                        # Graceful degradation - don't break the tab
                        if developer_mode:
                            st.warning(f"Occupancy insights unavailable: {e}")
                    
                    # Top Anomalies with Explanations
                    # Generate explanations
                    explanations_df = generate_anomaly_explanations(result_df, df, feature_map, selected_building)
                    
                    if len(explanations_df) > 0:
                        # Header card with description
                        section_card("Top Anomalies with Explanations", 
                                   "<p style='color: #888; font-size: 0.9rem; margin: 0.25rem 0 0;'>Detailed analysis of the most significant anomalies</p>",
                                   "clipboard-check", "#3b82f6", "default")
                        # Get top N anomalies
                        top_anomalies = result_df[result_df['anomaly']].nlargest(top_n, 'abs_z')
                        
                        # Merge with explanations
                        top_explanations = explanations_df.merge(
                            top_anomalies[['hour_datetime', selected_building, 'predicted', 'residual', 'z_score', 'abs_z', 'abs_residual']],
                            on='hour_datetime',
                            how='inner'
                        )
                        
                        # Add Cloud_Type if available
                        if 'Cloud_Type' in df.columns:
                            cloud_types = df.set_index('hour_datetime')['Cloud_Type']
                            top_explanations['Cloud_Type'] = top_explanations['hour_datetime'].map(cloud_types).fillna('N/A')
                        
                        # Display table - Cloud_Type is excluded from display but remains in top_explanations for internal use
                        display_cols = ['hour_datetime', selected_building, 'predicted', 'residual', 'z_score', 'abs_z', 
                                       'explanation_summary', 'explanation_tags', 'recommended_actions']
                        
                        display_df = top_explanations[display_cols].copy()
                        display_df.columns = ['DateTime', 'Actual', 'Predicted', 'Residual', 'Z-Score', '|Z-Score|',
                                            'Explanation', 'Tags', 'Recommended Actions']
                        
                        st.dataframe(display_df.round(3), use_container_width=True, height=500)
                    else:
                        st.info("No explanations generated. Ensure anomalies are detected.")
                    
                    # Recurring Patterns Panel
                    if enable_recurrence:
                        patterns = detect_recurring_patterns(result_df)
                        
                        # Header card with description
                        section_card("Recurring Patterns",
                                   "<p style='color: #888; font-size: 0.9rem; margin: 0.25rem 0 0;'>Temporal patterns in anomaly occurrence</p>",
                                   "clock", "#8b5cf6", "default")
                        
                        pattern_col1, pattern_col2, pattern_col3 = st.columns(3)
                        
                        with pattern_col1:
                            st.markdown("**Most Anomalous Hours**")
                            if patterns.get('top_hours'):
                                for hour in patterns['top_hours'][:3]:
                                    count = patterns['hour_of_day_counts'].get(hour, 0)
                                    st.metric(f"{hour}:00", f"{count} anomalies")
                            else:
                                st.info("No patterns detected")
                        
                        with pattern_col2:
                            st.markdown("**Most Anomalous Weekdays**")
                            if patterns.get('top_weekdays'):
                                for weekday in patterns['top_weekdays'][:2]:
                                    count = patterns['weekday_counts'].get(weekday, 0)
                                    st.metric(weekday, f"{count} anomalies")
                            else:
                                st.info("No patterns detected")
                        
                        with pattern_col3:
                            st.markdown("**Seasonal Distribution**")
                            season_split = patterns.get('season_split', {})
                            if season_split:
                                st.metric("Summer", f"{season_split.get('summer', 0):.1f}%")
                                st.metric("Winter", f"{season_split.get('winter', 0):.1f}%")
                            else:
                                st.info("No seasonal data")
                    
                    # Cost Impact (if enabled)
                    if enable_cost_estimates:
                        cost_data = estimate_cost_impact(result_df, selected_building, electricity_rate)
                        
                        # Build body content with metrics and disclaimer
                        body_html = f"""<div style='margin-bottom: 0.5rem;'>
                            <div style='display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 0.75rem;'>
                                <div>
                                    <div style='color: #888; font-size: 0.85rem; margin-bottom: 0.25rem;'>Excess Energy</div>
                                    <div style='color: #ffffff; font-size: 1.5rem; font-weight: 600;'>{cost_data['excess_kwh']:.2f} kWh</div>
                                </div>
                                <div>
                                    <div style='color: #888; font-size: 0.85rem; margin-bottom: 0.25rem;'>Avoided Energy</div>
                                    <div style='color: #ffffff; font-size: 1.5rem; font-weight: 600;'>{cost_data['avoided_kwh']:.2f} kWh</div>
                                </div>
                                <div>
                                    <div style='color: #888; font-size: 0.85rem; margin-bottom: 0.25rem;'>Estimated Cost</div>
                                    <div style='color: #22c55e; font-size: 1.5rem; font-weight: 600;'>${cost_data['estimated_cost']:.2f}</div>
                                </div>
                            </div>
                            <p style='color: #888; font-size: 0.85rem; margin: 0.25rem 0 0;'>{cost_data['disclaimer']}</p>
                        </div>"""
                        section_card("Cost Impact Estimate", body_html, "sparkles", "#f59e0b", "default")
                
                except Exception as e:
                    st.error(f"Error generating insights: {e}")
                    if developer_mode:
                        import traceback
                        st.code(traceback.format_exc())
    
    # Regression Tab
    with tab_regression:
        try:
            if not REGRESSION_ENGINE_AVAILABLE:
                st.error("Regression engine not available. Please ensure regression_engine.py is in the project directory.")
            else:
                # Get regression results for selected building
                # Use session_state to get selected_building (safe for reruns)
                current_selected_building = st.session_state.get("selected_building", building_cols[0] if len(building_cols) > 0 else None)
                if current_selected_building is None:
                    st.info("No building selected. Run anomaly detection first.")
                else:
                    dataset_signature = (
                        len(df),
                        df['hour_datetime'].min() if 'hour_datetime' in df.columns else None,
                        df['hour_datetime'].max() if 'hour_datetime' in df.columns else None
                    )
                    # Derive fixed mode from feature_mode
                    is_fixed_mode = (feature_mode == "Fixed 3-feature")
                    feature_mode_key = "fixed" if is_fixed_mode else f"{selection_method}_k{top_k_features}_cloud{include_cloud_type}"
                    cache_key = (current_selected_building, selected_year, feature_mode_key, dataset_signature)
                    regression_result = st.session_state.get('regression_results', {}).get(cache_key)
                    
                    if regression_result is None:
                        st.info("Run anomaly detection first to see regression model details.")
                    else:
                        # Get data for Model Summary
                        selected_features = regression_result.get('selected_features', [])
                        
                        # Safety filter: remove any building columns that slipped through
                        building_cols_list = get_building_columns(df)
                        selected_features = [f for f in selected_features if f not in building_cols_list]
                        
                        # Get canonical feature names for display
                        selected_features_canonical = regression_result.get('selected_features_canonical', [])
                        if not selected_features_canonical or len(selected_features_canonical) != len(selected_features):
                            # Map df column names to canonical names
                            feature_map = resolve_feature_columns(df)
                            reverse_map = {v: k for k, v in (feature_map.items() if feature_map else {})}
                            selected_features_canonical = [reverse_map.get(f, f) for f in selected_features]
                        
                        method_used = regression_result.get('method_used', 'unknown')
                        feature_mode_display = regression_result.get('feature_mode', 'unknown')
                        include_cloud_type_used = regression_result.get('include_cloud_type', False)
                        
                        # Show feature mode
                        feature_mode_labels = {
                            'auto_select': 'Auto-select',
                            'fixed_3_feature': 'Fixed 3-feature (Legacy)'
                        }
                        mode_label = feature_mode_labels.get(feature_mode_display, feature_mode_display)
                        
                        method_display = {
                            'elasticnet': 'ElasticNet',
                            'correlation': 'Correlation Top-K',
                            'correlation_fallback': 'Correlation (fallback)',
                            'fixed_3_feature': 'Fixed 3-feature',
                            'fixed_3_feature_fallback': 'Fixed 3-feature (fallback)',
                            'auto_select_fallback': 'Auto-select (fallback)'
                        }.get(method_used, method_used)
                        
                        # Build KPI items
                        kpi_items = []
                        
                        # Selected Features count
                        kpi_items.append({
                            'label': 'Selected Features',
                            'value': str(len(selected_features)),
                            'value_color': '#ffffff'
                        })
                        
                        # Selection Method
                        kpi_items.append({
                            'label': 'Selection Method',
                            'value': method_display,
                            'value_color': '#ffffff'
                        })
                        
                        # Feature Mode
                        kpi_items.append({
                            'label': 'Feature Mode',
                            'value': mode_label,
                            'value_color': '#ffffff'
                        })
                        
                        # Get metrics if available
                        fit_result = regression_result.get('fit_result')
                        if fit_result and not fit_result.get('error'):
                            metrics = fit_result.get('metrics', {})
                            r2 = metrics.get('r2', 0)
                            rmse = metrics.get('rmse', 0)
                            mae = metrics.get('mae', 0)
                            
                            # Get confidence
                            from regression_engine import get_regression_confidence
                            confidence = get_regression_confidence(r2)
                            
                            # R² Score with color
                            if r2 >= 0.60:
                                r2_color = '#22c55e'  # green
                            elif r2 >= 0.30:
                                r2_color = '#f59e0b'  # amber
                            else:
                                r2_color = '#ef4444'  # red
                            
                            kpi_items.append({
                                'label': 'R² Score',
                                'value': f"{r2:.4f}",
                                'value_color': r2_color
                            })
                            
                            # RMSE
                            kpi_items.append({
                                'label': 'RMSE',
                                'value': f"{rmse:.2f}",
                                'value_color': '#ffffff'
                            })
                            
                            # MAE
                            kpi_items.append({
                                'label': 'MAE',
                                'value': f"{mae:.2f}",
                                'value_color': '#ffffff'
                            })
                            
                            # Confidence with color
                            confidence_color = confidence.get('color', '#ffffff')
                            kpi_items.append({
                                'label': 'Confidence',
                                'value': confidence.get('level', 'Unknown'),
                                'value_color': confidence_color
                            })
                        
                        # Build feature list HTML
                        features_html = ""
                        if selected_features_canonical:
                            if len(selected_features_canonical) <= 5:
                                features_display = ', '.join(selected_features_canonical)
                                features_html = f"<div style='margin-top: 0.75rem;'><div style='color: #9aa0a6; font-size: 0.85rem; margin-bottom: 0.25rem;'>Selected Features</div><div style='color: #e0e0e0; font-size: 0.95rem;'>{features_display}</div></div>"
                            else:
                                top_5 = ', '.join(selected_features_canonical[:5])
                                remaining = len(selected_features_canonical) - 5
                                all_features = ', '.join(selected_features_canonical)
                                features_html = f"""<div style='margin-top: 0.75rem;'>
                                    <div style='color: #9aa0a6; font-size: 0.85rem; margin-bottom: 0.25rem;'>Selected Features</div>
                                    <div style='color: #e0e0e0; font-size: 0.95rem;'>{top_5} <span style='color: #888;'>+{remaining} more</span></div>
                                    <details style='margin-top: 0.5rem;'>
                                        <summary style='color: #888; font-size: 0.85rem; cursor: pointer; user-select: none;'>Show all features</summary>
                                        <div style='color: #e0e0e0; font-size: 0.9rem; margin-top: 0.5rem; padding: 0.5rem; background: rgba(0,0,0,0.2); border-radius: 4px;'>{all_features}</div>
                                    </details>
                                </div>"""
                        
                        # Cloud_Type note if included
                        cloud_note = ""
                        if include_cloud_type_used:
                            cloud_features = [f for f in selected_features_canonical if 'Cloud' in f or 'cloud' in f]
                            if cloud_features:
                                cloud_note = f"<p style='color: #888; font-size: 0.85rem; margin: 0.5rem 0 0;'>ℹ️ Cloud_Type feature included</p>"
                        
                        # Legacy mode warning
                        legacy_warning = ""
                        if feature_mode_display == 'fixed_3_feature':
                            legacy_warning = "<p style='color: #f59e0b; font-size: 0.85rem; margin: 0.5rem 0 0;'>⚠️ Legacy compatibility mode</p>"
                        
                        # Weak model warning
                        weak_warning = ""
                        if fit_result and not fit_result.get('error'):
                            r2 = fit_result.get('metrics', {}).get('r2', 0)
                            if r2 < 0.2:
                                weak_warning = "<p style='color: #ef4444; font-size: 0.85rem; margin: 0.5rem 0 0;'>⚠️ Model weak (R² < 0.2); anomaly results may be noisy</p>"
                        
                        # Build complete body HTML - ensure HTML is inserted directly without extra formatting
                        kpi_html = kpi_grid(kpi_items, columns=3)
                        body_html = "<div style='margin-bottom: 0.5rem;'>" + kpi_html + features_html + cloud_note + legacy_warning + weak_warning + "</div>"
                        
                        # Render Model Summary card (only render once, inside section_card)
                        section_card("Model Summary",
                                   body_html,
                                   "target", "#3b82f6", "default")
                        
                        # Error handling for fit_result
                        if fit_result and fit_result.get('error'):
                            st.error(f"Regression fitting error: {fit_result['error']}")
                        elif not fit_result:
                            st.info("Model metrics not available. Using simple linear regression.")
                        
                        # Coefficients table
                        if fit_result and 'coef_table' in fit_result:
                            section_card("Coefficients",
                                       "<p style='color: #888; font-size: 0.9rem; margin: 0.25rem 0 0;'>Feature coefficients and standardized values</p>",
                                       "bar-chart", "#8b5cf6", "default")
                            coef_df = fit_result['coef_table'].copy()
                            coef_df['sign'] = coef_df['coefficient'].apply(lambda x: '+' if x >= 0 else '-')
                            coef_df = coef_df[['feature', 'coefficient', 'sign', 'standardized_coefficient']]
                            coef_df.columns = ['Feature', 'Coefficient', 'Sign', 'Standardized Coef']
                            st.dataframe(coef_df.round(4), use_container_width=True, height=200)
                        
                        # Candidate features table
                        section_card("Candidate Features",
                                   "<p style='color: #888; font-size: 0.9rem; margin: 0.25rem 0 0;'>All candidate weather features considered for regression</p>",
                                   "database", "#3b82f6", "default")
                        
                        # Get candidate_features_df from fit_result or selection_result
                        candidate_features_df = None
                        fit_result_inner = regression_result.get('fit_result', {})
                        if fit_result_inner and 'candidate_features' in fit_result_inner:
                            candidate_features_df = fit_result_inner['candidate_features']
                        elif 'selection_result' in regression_result:
                            candidate_features_df = regression_result['selection_result'].get('candidate_features_df')
                        
                        if candidate_features_df is not None and len(candidate_features_df) > 0:
                            # Sort: selected first, then by abs(corr_train) descending
                            candidate_features_df = candidate_features_df.copy()
                            candidate_features_df['is_selected'] = candidate_features_df['selected'] == '✓'
                            candidate_features_df['abs_corr'] = candidate_features_df['corr_train'].abs()
                            candidate_features_df = candidate_features_df.sort_values(
                                ['is_selected', 'abs_corr'], 
                                ascending=[False, False]
                            )
                            candidate_features_df = candidate_features_df.drop(['is_selected', 'abs_corr'], axis=1)
                            
                            # Prepare display: show canonical name if available, else df column name
                            if 'canonical_name' in candidate_features_df.columns:
                                # Use canonical_name for display, show df column in parentheses if different
                                candidate_features_df['Display Name'] = candidate_features_df.apply(
                                    lambda row: row['canonical_name'] if row['canonical_name'] != row['feature'] 
                                    else row['feature'], axis=1
                                )
                                candidate_features_df['DF Column'] = candidate_features_df['feature']
                            else:
                                # Fallback: use feature as display name
                                candidate_features_df['Display Name'] = candidate_features_df['feature']
                                candidate_features_df['DF Column'] = candidate_features_df['feature']
                            
                            # Rename columns for display
                            display_df = candidate_features_df[['Display Name', 'DF Column', 'missing_pct', 'corr_train', 'selected']].copy()
                            display_df = display_df.rename(columns={
                                'missing_pct': 'Missing %',
                                'corr_train': 'Correlation (Train)',
                                'selected': 'Selected'
                            })
                            display_df['Missing %'] = display_df['Missing %'].apply(lambda x: f"{x:.1f}%")
                            display_df['Correlation (Train)'] = display_df['Correlation (Train)'].apply(lambda x: f"{x:.3f}" if x != 0 else "N/A")
                            
                            st.dataframe(display_df, use_container_width=True, height=300)
                        else:
                            st.warning("Candidate features information not available.")
                            if developer_mode:
                                st.code(f"Available keys in regression_result: {list(regression_result.keys())}")
                                if 'fit_result' in regression_result:
                                    st.code(f"Available keys in fit_result: {list(regression_result['fit_result'].keys())}")
                        
                        # Optional: Predicted vs Actual scatter plot (test set only)
                        if fit_result and 'y_test' in fit_result and 'y_test_pred' in fit_result:
                            y_test = fit_result['y_test']
                            y_test_pred = fit_result['y_test_pred']
                            
                            if len(y_test) > 0 and len(y_test_pred) > 0:
                                section_card("Model Fit (Test Set)",
                                         "<p style='color: #888; font-size: 0.9rem; margin: 0.25rem 0 0;'>Predicted vs actual load on test set</p>",
                                         "bar-chart", "#8b5cf6", "default")
                                fig = go.Figure()
                                fig.add_trace(go.Scatter(
                                    x=y_test,
                                    y=y_test_pred,
                                    mode='markers',
                                    marker=dict(color='#3b82f6', size=4, opacity=0.6),
                                    name='Predictions',
                                    hovertemplate='Actual: %{x:.2f}<br>Predicted: %{y:.2f}<extra></extra>'
                                ))
                                # Perfect prediction line
                                min_val = min(y_test.min(), y_test_pred.min())
                                max_val = max(y_test.max(), y_test_pred.max())
                                fig.add_trace(go.Scatter(
                                    x=[min_val, max_val],
                                    y=[min_val, max_val],
                                    mode='lines',
                                    line=dict(color='#22c55e', width=2, dash='dash'),
                                    name='Perfect Prediction'
                                ))
                                fig.update_layout(
                                    template="plotly_dark",
                                    title="Predicted vs Actual (Test Set)",
                                    xaxis_title="Actual Load",
                                    yaxis_title="Predicted Load",
                                    height=400,
                                    margin=dict(l=40, r=40, t=60, b=40),
                                    font=dict(family="Inter, sans-serif", size=12, color="#e0e0e0"),
                                    paper_bgcolor="#25253a",
                                    plot_bgcolor="#25253a",
                                )
                                fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)')
                                fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)')
                                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error rendering Regression tab: {e}")
            if developer_mode:
                import traceback
                st.code(traceback.format_exc())
    
    with tab2:
        section_card(f"Building Drilldown: {selected_building}",
                     "<p style='color: #888; font-size: 0.9rem; margin: 0.25rem 0 0;'>Time series analysis with anomaly markers</p>",
                     "building", "#3b82f6", "default")

        # Dark theme plotly template
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Actual vs Predicted Load', 'Residuals with Anomaly Thresholds'),
            vertical_spacing=0.12,
            row_heights=[0.6, 0.4]
        )

        # Actual vs Predicted
        fig.add_trace(go.Scatter(
            x=result_df['hour_datetime'], 
            y=result_df[selected_building],
            name='Actual',
            mode='lines',
            line=dict(color='#3b82f6', width=1.5),
            hovertemplate='<b>%{fullData.name}</b><br>Time: %{x}<br>Load: %{y:.2f}<extra></extra>'
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=result_df['hour_datetime'], 
            y=result_df['predicted'],
            name='Predicted',
            mode='lines',
            line=dict(color='#22c55e', width=1.5, dash='dash'),
            hovertemplate='<b>%{fullData.name}</b><br>Time: %{x}<br>Load: %{y:.2f}<extra></extra>'
        ), row=1, col=1)

        anomalies = result_df[result_df['anomaly']]
        if len(anomalies) > 0:
            fig.add_trace(go.Scatter(
                x=anomalies['hour_datetime'], 
                y=anomalies[selected_building],
                name='Anomalies',
                mode='markers',
                marker=dict(
                    color='#ef4444',
                    size=8,
                    symbol='x',
                    line=dict(width=1, color='#ffffff')
                ),
                hovertemplate='<b>Anomaly</b><br>Time: %{x}<br>Load: %{y:.2f}<br>Z-Score: %{customdata:.2f}<extra></extra>',
                customdata=anomalies['abs_z']
            ), row=1, col=1)

        # Residuals
        fig.add_trace(go.Scatter(
            x=result_df['hour_datetime'], 
            y=result_df['residual'],
            name='Residuals',
            mode='lines',
            line=dict(color='#888', width=1),
            hovertemplate='<b>%{fullData.name}</b><br>Time: %{x}<br>Residual: %{y:.2f}<extra></extra>'
        ), row=2, col=1)

        threshold_line = z_threshold * result_df['residual'].std()
        fig.add_hline(
            y=threshold_line, 
            line_dash="dash", 
            line_color="#ef4444",
            annotation_text=f"+{z_threshold}σ",
            annotation_position="right",
            row=2, col=1
        )
        fig.add_hline(
            y=-threshold_line, 
            line_dash="dash", 
            line_color="#ef4444",
            annotation_text=f"-{z_threshold}σ",
            annotation_position="right",
            row=2, col=1
        )

        # Update layout with dark theme
        fig.update_layout(
            height=700,
            showlegend=True,
            template='plotly_dark',
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#e0e0e0', size=12),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            hovermode='x unified'
        )
        
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)', row=1, col=1)
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)', row=2, col=1)
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)', row=1, col=1)
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)', row=2, col=1)
        
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        section_card(f"Top {top_n} Anomalies for {selected_building}",
                     "<p style='color: #888; font-size: 0.9rem; margin: 0.25rem 0 0;'>Most severe anomalies ranked by absolute Z-score</p>",
                     "table", "#3b82f6", "default")

        display_cols = ['hour_datetime', selected_building, 'predicted', 'residual', 'z_score', 'abs_z', 'abs_residual']
        # Note: Cloud_Type is excluded from display but remains in result_df for regression/insights

        top_anoms = result_df.nlargest(top_n, 'abs_z')[display_cols].copy().round(3)
        top_anoms.columns = ['DateTime', 'Actual Load', 'Predicted', 'Residual', 'Z-Score', '|Z-Score|', '|Residual|']
        st.dataframe(top_anoms, use_container_width=True, height=500)
    
    # Footer (only show when results are displayed)
    st.markdown("""
    <div class='footer'>
        <p>Energy Anomaly Explorer • Powered by OpenEI + NSRDB</p>
    </div>
    """, unsafe_allow_html=True)
