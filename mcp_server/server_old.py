"""
MCP Server for US Accidents Dataset (2016-2023)
Powers an Autonomous Vehicle Agent with accident hotspot and risk analysis tools.

This server exposes tools for:
- Querying accident hotspots by location, time, and weather
- Getting risk assessments for routes
- Analyzing temporal patterns (rush hour, time of day, day of week)
- Weather-based accident risk analysis
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Any
from contextlib import contextmanager

from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("US Accidents Dataset Server")

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), "accidents.db")


@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def format_accident_record(row: sqlite3.Row) -> dict:
    """Format a database row as a dictionary."""
    return dict(row)


# ============================================================================
# TOOL 1: Get Accident Hotspots by Region
# ============================================================================
@mcp.tool()
def get_accident_hotspots(
    state: str | None = None,
    city: str | None = None,
    limit: int = 10
) -> str:
    """
    Get accident hotspot locations ranked by accident frequency.
    
    Use this tool when the autonomous vehicle needs to know which areas
    have historically high accident rates. Results can be filtered by
    state or city.
    
    Args:
        state: Two-letter state code (e.g., 'CA', 'TX', 'FL'). Optional.
        city: City name to filter by. Optional.
        limit: Maximum number of hotspots to return (default: 10).
    
    Returns:
        JSON string with hotspot locations and accident counts.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Build query based on filters
        conditions = []
        params = []
        
        if state:
            conditions.append("State = ?")
            params.append(state.upper())
        if city:
            conditions.append("City LIKE ?")
            params.append(f"%{city}%")
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        query = f"""
            SELECT 
                City,
                State,
                County,
                COUNT(*) as accident_count,
                AVG(Severity) as avg_severity,
                ROUND(AVG(Start_Lat), 4) as center_lat,
                ROUND(AVG(Start_Lng), 4) as center_lng
            FROM accidents
            {where_clause}
            GROUP BY City, State, County
            ORDER BY accident_count DESC
            LIMIT ?
        """
        params.append(limit)
        
        cursor.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        
        return json.dumps({
            "hotspots": results,
            "total_returned": len(results),
            "filters_applied": {"state": state, "city": city}
        }, indent=2)


# ============================================================================
# TOOL 2: Get Accidents Near Location
# ============================================================================
@mcp.tool()
def get_accidents_near_location(
    latitude: float,
    longitude: float,
    radius_miles: float = 5.0,
    limit: int = 50
) -> str:
    """
    Find accidents near a specific GPS coordinate within a given radius.
    
    Use this tool when the autonomous vehicle needs to assess accident
    history near its current location or along a planned route segment.
    
    Args:
        latitude: GPS latitude coordinate.
        longitude: GPS longitude coordinate.
        radius_miles: Search radius in miles (default: 5.0).
        limit: Maximum number of accidents to return (default: 50).
    
    Returns:
        JSON string with nearby accidents and summary statistics.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Approximate degree conversion (1 degree ≈ 69 miles at equator)
        lat_range = radius_miles / 69.0
        lng_range = radius_miles / (69.0 * abs(cos_deg(latitude)))
        
        query = """
            SELECT 
                ID,
                Severity,
                Start_Time,
                Start_Lat,
                Start_Lng,
                Street,
                City,
                Weather_Condition,
                Visibility_mi,
                Description
            FROM accidents
            WHERE Start_Lat BETWEEN ? AND ?
              AND Start_Lng BETWEEN ? AND ?
            ORDER BY Severity DESC, Start_Time DESC
            LIMIT ?
        """
        
        cursor.execute(query, (
            latitude - lat_range,
            latitude + lat_range,
            longitude - lng_range,
            longitude + lng_range,
            limit
        ))
        
        accidents = [dict(row) for row in cursor.fetchall()]
        
        # Calculate summary statistics
        if accidents:
            avg_severity = sum(a['Severity'] for a in accidents) / len(accidents)
            severity_counts = {}
            for a in accidents:
                sev = a['Severity']
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
        else:
            avg_severity = 0
            severity_counts = {}
        
        return json.dumps({
            "location": {"latitude": latitude, "longitude": longitude},
            "radius_miles": radius_miles,
            "accidents_found": len(accidents),
            "average_severity": round(avg_severity, 2),
            "severity_distribution": severity_counts,
            "accidents": accidents[:20]  # Return top 20 for brevity
        }, indent=2)


def cos_deg(degrees: float) -> float:
    """Cosine of angle in degrees."""
    import math
    return math.cos(math.radians(degrees))


# ============================================================================
# TOOL 3: Get Risk Assessment for Time Period
# ============================================================================
@mcp.tool()
def get_temporal_risk_assessment(
    hour_of_day: int,
    day_of_week: int | None = None,
    state: str | None = None
) -> str:
    """
    Get accident risk assessment based on time of day and day of week.
    
    Use this tool when the autonomous vehicle needs to understand
    how dangerous the current time period is historically.
    
    Args:
        hour_of_day: Hour in 24-hour format (0-23).
        day_of_week: Day of week (0=Monday, 6=Sunday). Optional.
        state: Two-letter state code to filter by. Optional.
    
    Returns:
        JSON string with temporal risk analysis and recommendations.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        conditions = ["hour_of_day = ?"]
        params = [hour_of_day]
        
        if day_of_week is not None:
            conditions.append("day_of_week = ?")
            params.append(day_of_week)
        if state:
            conditions.append("State = ?")
            params.append(state.upper())
        
        where_clause = " AND ".join(conditions)
        
        # Get accident counts for this time period
        query = f"""
            SELECT 
                COUNT(*) as accident_count,
                AVG(Severity) as avg_severity,
                SUM(CASE WHEN Severity >= 3 THEN 1 ELSE 0 END) as severe_accidents
            FROM accidents
            WHERE {where_clause}
        """
        
        cursor.execute(query, params)
        result = dict(cursor.fetchone())
        
        # Get comparison with overall average
        cursor.execute("SELECT COUNT(*) / 168.0 as avg_hourly FROM accidents")  # 168 = 24*7
        avg_hourly = cursor.fetchone()[0]
        
        # Calculate risk level
        if result['accident_count'] > avg_hourly * 1.5:
            risk_level = "HIGH"
            recommendation = "Exercise extreme caution. Reduce speed and increase following distance."
        elif result['accident_count'] > avg_hourly:
            risk_level = "MODERATE"
            recommendation = "Be alert. This is a higher-than-average risk period."
        else:
            risk_level = "LOW"
            recommendation = "Normal driving conditions expected."
        
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        return json.dumps({
            "time_period": {
                "hour": hour_of_day,
                "day_of_week": day_names[day_of_week] if day_of_week is not None else "All days",
                "state": state or "All states"
            },
            "statistics": {
                "total_accidents": result['accident_count'],
                "average_severity": round(result['avg_severity'] or 0, 2),
                "severe_accidents_count": result['severe_accidents']
            },
            "risk_assessment": {
                "level": risk_level,
                "recommendation": recommendation
            }
        }, indent=2)


# ============================================================================
# TOOL 4: Get Weather-Based Risk Assessment
# ============================================================================
@mcp.tool()
def get_weather_risk_assessment(
    weather_condition: str,
    visibility_miles: float | None = None,
    state: str | None = None
) -> str:
    """
    Get accident risk assessment based on weather conditions.
    
    Use this tool when the autonomous vehicle encounters specific
    weather conditions and needs to assess the associated risk.
    
    Args:
        weather_condition: Current weather (e.g., 'Rain', 'Snow', 'Fog', 'Clear').
        visibility_miles: Current visibility in miles. Optional.
        state: Two-letter state code to filter by. Optional.
    
    Returns:
        JSON string with weather-related risk analysis.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Search for similar weather conditions
        conditions = ["Weather_Condition LIKE ?"]
        params = [f"%{weather_condition}%"]
        
        if visibility_miles is not None:
            # Look at accidents with similar or worse visibility
            conditions.append("Visibility_mi <= ?")
            params.append(visibility_miles + 1)  # Include slightly better visibility
        if state:
            conditions.append("State = ?")
            params.append(state.upper())
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT 
                COUNT(*) as accident_count,
                AVG(Severity) as avg_severity,
                AVG(Visibility_mi) as avg_visibility,
                SUM(CASE WHEN Severity >= 3 THEN 1 ELSE 0 END) as severe_count
            FROM accidents
            WHERE {where_clause}
        """
        
        cursor.execute(query, params)
        result = dict(cursor.fetchone())
        
        # Get baseline (clear weather) for comparison
        cursor.execute("""
            SELECT AVG(Severity) as clear_severity 
            FROM accidents 
            WHERE Weather_Condition LIKE '%Clear%' OR Weather_Condition LIKE '%Fair%'
        """)
        clear_severity = cursor.fetchone()[0] or 2.0
        
        # Calculate risk multiplier
        current_severity = result['avg_severity'] or 0
        risk_multiplier = current_severity / clear_severity if clear_severity > 0 else 1.0
        
        if risk_multiplier > 1.3:
            risk_level = "HIGH"
            recommendation = "Hazardous conditions. Significantly reduce speed and increase following distance."
        elif risk_multiplier > 1.1:
            risk_level = "MODERATE"
            recommendation = "Exercise caution. Weather conditions increase accident risk."
        else:
            risk_level = "LOW"
            recommendation = "Normal risk level for current weather conditions."
        
        return json.dumps({
            "weather_conditions": {
                "condition": weather_condition,
                "visibility_miles": visibility_miles
            },
            "statistics": {
                "accidents_in_similar_conditions": result['accident_count'],
                "average_severity": round(current_severity, 2),
                "severe_accidents": result['severe_count'],
                "average_visibility": round(result['avg_visibility'] or 0, 2)
            },
            "risk_assessment": {
                "level": risk_level,
                "risk_multiplier": round(risk_multiplier, 2),
                "recommendation": recommendation
            }
        }, indent=2)


# ============================================================================
# TOOL 5: Analyze Route Risk
# ============================================================================
@mcp.tool()
def analyze_route_risk(
    waypoints: list[dict],
    time_of_day: int | None = None,
    weather: str | None = None
) -> str:
    """
    Analyze accident risk along a route defined by waypoints.
    
    Use this tool when the autonomous vehicle needs to assess the
    overall risk of a planned route and identify dangerous segments.
    
    Args:
        waypoints: List of GPS coordinates as dicts with 'lat' and 'lng' keys.
                   Example: [{"lat": 34.05, "lng": -118.25}, {"lat": 34.10, "lng": -118.30}]
        time_of_day: Current hour (0-23) for time-based risk adjustment. Optional.
        weather: Current weather condition for weather-based adjustment. Optional.
    
    Returns:
        JSON string with route risk analysis and segment-by-segment breakdown.
    """
    if not waypoints or len(waypoints) < 2:
        return json.dumps({"error": "At least 2 waypoints required for route analysis"})
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        segment_analyses = []
        total_accidents = 0
        max_severity = 0
        
        for i in range(len(waypoints) - 1):
            start = waypoints[i]
            end = waypoints[i + 1]
            
            # Calculate bounding box for segment
            min_lat = min(start['lat'], end['lat']) - 0.05
            max_lat = max(start['lat'], end['lat']) + 0.05
            min_lng = min(start['lng'], end['lng']) - 0.05
            max_lng = max(start['lng'], end['lng']) + 0.05
            
            conditions = [
                "Start_Lat BETWEEN ? AND ?",
                "Start_Lng BETWEEN ? AND ?"
            ]
            params = [min_lat, max_lat, min_lng, max_lng]
            
            if time_of_day is not None:
                conditions.append("hour_of_day = ?")
                params.append(time_of_day)
            if weather:
                conditions.append("Weather_Condition LIKE ?")
                params.append(f"%{weather}%")
            
            where_clause = " AND ".join(conditions)
            
            query = f"""
                SELECT 
                    COUNT(*) as accident_count,
                    AVG(Severity) as avg_severity,
                    MAX(Severity) as max_severity,
                    GROUP_CONCAT(DISTINCT Street) as streets
                FROM accidents
                WHERE {where_clause}
            """
            
            cursor.execute(query, params)
            result = dict(cursor.fetchone())
            
            segment_accidents = result['accident_count'] or 0
            segment_severity = result['avg_severity'] or 0
            
            total_accidents += segment_accidents
            max_severity = max(max_severity, result['max_severity'] or 0)
            
            # Determine segment risk
            if segment_accidents > 100 and segment_severity > 2.5:
                segment_risk = "HIGH"
            elif segment_accidents > 50 or segment_severity > 2.3:
                segment_risk = "MODERATE"
            else:
                segment_risk = "LOW"
            
            segment_analyses.append({
                "segment": i + 1,
                "from": start,
                "to": end,
                "accidents_count": segment_accidents,
                "avg_severity": round(segment_severity, 2),
                "risk_level": segment_risk,
                "notable_streets": (result['streets'] or "")[:200]  # Limit string length
            })
        
        # Overall route risk
        if max_severity >= 4 or total_accidents > 500:
            overall_risk = "HIGH"
            recommendation = "High-risk route. Consider alternative routes or extra precautions."
        elif max_severity >= 3 or total_accidents > 200:
            overall_risk = "MODERATE"
            recommendation = "Moderate risk route. Stay alert, especially in identified segments."
        else:
            overall_risk = "LOW"
            recommendation = "Relatively safe route based on historical data."
        
        return json.dumps({
            "route_summary": {
                "total_waypoints": len(waypoints),
                "segments_analyzed": len(segment_analyses),
                "total_historical_accidents": total_accidents,
                "max_severity_encountered": max_severity,
                "overall_risk": overall_risk,
                "recommendation": recommendation
            },
            "context": {
                "time_of_day": time_of_day,
                "weather": weather
            },
            "segment_analysis": segment_analyses
        }, indent=2)


# ============================================================================
# TOOL 6: Get Road Feature Risk Analysis
# ============================================================================
@mcp.tool()
def get_road_feature_risk(
    feature: str,
    state: str | None = None
) -> str:
    """
    Analyze accident risk associated with specific road features.
    
    Use this tool when the autonomous vehicle encounters specific
    road features and needs to understand the associated risks.
    
    Args:
        feature: Road feature to analyze. Options: 'crossing', 'junction',
                 'traffic_signal', 'stop', 'railway', 'roundabout', 'bump'.
        state: Two-letter state code to filter by. Optional.
    
    Returns:
        JSON string with road feature risk analysis.
    """
    feature_columns = {
        'crossing': 'Crossing',
        'junction': 'Junction',
        'traffic_signal': 'Traffic_Signal',
        'stop': 'Stop',
        'railway': 'Railway',
        'roundabout': 'Roundabout',
        'bump': 'Bump',
        'give_way': 'Give_Way',
        'no_exit': 'No_Exit',
        'station': 'Station'
    }
    
    feature_lower = feature.lower()
    if feature_lower not in feature_columns:
        return json.dumps({
            "error": f"Unknown feature: {feature}",
            "available_features": list(feature_columns.keys())
        })
    
    column = feature_columns[feature_lower]
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        state_condition = "AND State = ?" if state else ""
        params = [state.upper()] if state else []
        
        # Get stats for accidents WITH this feature
        query_with = f"""
            SELECT 
                COUNT(*) as count,
                AVG(Severity) as avg_severity,
                AVG(Duration_minutes) as avg_duration
            FROM accidents
            WHERE {column} = 1 {state_condition}
        """
        cursor.execute(query_with, params)
        with_feature = dict(cursor.fetchone())
        
        # Get stats for accidents WITHOUT this feature
        query_without = f"""
            SELECT 
                COUNT(*) as count,
                AVG(Severity) as avg_severity,
                AVG(Duration_minutes) as avg_duration
            FROM accidents
            WHERE {column} = 0 {state_condition}
        """
        cursor.execute(query_without, params)
        without_feature = dict(cursor.fetchone())
        
        # Calculate risk increase
        if without_feature['avg_severity'] and without_feature['avg_severity'] > 0:
            severity_increase = ((with_feature['avg_severity'] or 0) / without_feature['avg_severity'] - 1) * 100
        else:
            severity_increase = 0
        
        if severity_increase > 10:
            risk_level = "HIGH"
            recommendation = f"Extra caution needed near {feature}. Significantly higher accident severity."
        elif severity_increase > 5:
            risk_level = "MODERATE"
            recommendation = f"Be alert near {feature}. Slightly elevated accident risk."
        else:
            risk_level = "LOW"
            recommendation = f"Normal risk level near {feature}."
        
        return json.dumps({
            "feature": feature,
            "state_filter": state or "All states",
            "with_feature": {
                "accident_count": with_feature['count'],
                "avg_severity": round(with_feature['avg_severity'] or 0, 2),
                "avg_duration_minutes": round(with_feature['avg_duration'] or 0, 1)
            },
            "without_feature": {
                "accident_count": without_feature['count'],
                "avg_severity": round(without_feature['avg_severity'] or 0, 2),
                "avg_duration_minutes": round(without_feature['avg_duration'] or 0, 1)
            },
            "risk_assessment": {
                "level": risk_level,
                "severity_increase_percent": round(severity_increase, 1),
                "recommendation": recommendation
            }
        }, indent=2)


# ============================================================================
# TOOL 7: Get State Statistics Summary
# ============================================================================
@mcp.tool()
def get_state_statistics(state: str) -> str:
    """
    Get comprehensive accident statistics for a specific state.
    
    Use this tool when the autonomous vehicle enters a new state
    and needs an overview of accident patterns in that region.
    
    Args:
        state: Two-letter state code (e.g., 'CA', 'TX', 'FL').
    
    Returns:
        JSON string with comprehensive state accident statistics.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        state_upper = state.upper()
        
        # Overall stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_accidents,
                AVG(Severity) as avg_severity,
                AVG(Duration_minutes) as avg_duration,
                MIN(Start_Time) as earliest_record,
                MAX(Start_Time) as latest_record
            FROM accidents
            WHERE State = ?
        """, (state_upper,))
        overall = dict(cursor.fetchone())
        
        # Top 5 cities
        cursor.execute("""
            SELECT City, COUNT(*) as count
            FROM accidents
            WHERE State = ?
            GROUP BY City
            ORDER BY count DESC
            LIMIT 5
        """, (state_upper,))
        top_cities = [dict(row) for row in cursor.fetchall()]
        
        # Severity distribution
        cursor.execute("""
            SELECT Severity, COUNT(*) as count
            FROM accidents
            WHERE State = ?
            GROUP BY Severity
            ORDER BY Severity
        """, (state_upper,))
        severity_dist = {row['Severity']: row['count'] for row in cursor.fetchall()}
        
        # Peak hours
        cursor.execute("""
            SELECT hour_of_day, COUNT(*) as count
            FROM accidents
            WHERE State = ?
            GROUP BY hour_of_day
            ORDER BY count DESC
            LIMIT 5
        """, (state_upper,))
        peak_hours = [dict(row) for row in cursor.fetchall()]
        
        # Weather conditions
        cursor.execute("""
            SELECT Weather_Condition, COUNT(*) as count
            FROM accidents
            WHERE State = ? AND Weather_Condition IS NOT NULL
            GROUP BY Weather_Condition
            ORDER BY count DESC
            LIMIT 5
        """, (state_upper,))
        weather_conditions = [dict(row) for row in cursor.fetchall()]
        
        return json.dumps({
            "state": state_upper,
            "overall_statistics": {
                "total_accidents": overall['total_accidents'],
                "average_severity": round(overall['avg_severity'] or 0, 2),
                "average_duration_minutes": round(overall['avg_duration'] or 0, 1),
                "data_range": {
                    "from": overall['earliest_record'],
                    "to": overall['latest_record']
                }
            },
            "top_accident_cities": top_cities,
            "severity_distribution": severity_dist,
            "peak_accident_hours": peak_hours,
            "common_weather_conditions": weather_conditions
        }, indent=2)


# ============================================================================
# TOOL 8: Search Accident Descriptions
# ============================================================================
@mcp.tool()
def search_accident_descriptions(
    keywords: str,
    state: str | None = None,
    min_severity: int = 1,
    limit: int = 20
) -> str:
    """
    Search accident records by keywords in descriptions.
    
    Use this tool to find accidents involving specific circumstances,
    vehicles, or road conditions mentioned in accident descriptions.
    
    Args:
        keywords: Search terms to find in accident descriptions.
        state: Two-letter state code to filter by. Optional.
        min_severity: Minimum severity level (1-4). Default: 1.
        limit: Maximum results to return. Default: 20.
    
    Returns:
        JSON string with matching accident records.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        conditions = ["Description LIKE ?", "Severity >= ?"]
        params = [f"%{keywords}%", min_severity]
        
        if state:
            conditions.append("State = ?")
            params.append(state.upper())
        
        params.append(limit)
        
        query = f"""
            SELECT 
                ID,
                Severity,
                Start_Time,
                City,
                State,
                Street,
                Weather_Condition,
                Description
            FROM accidents
            WHERE {" AND ".join(conditions)}
            ORDER BY Severity DESC, Start_Time DESC
            LIMIT ?
        """
        
        cursor.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        
        return json.dumps({
            "search_terms": keywords,
            "filters": {
                "state": state,
                "min_severity": min_severity
            },
            "results_count": len(results),
            "accidents": results
        }, indent=2)


# ============================================================================
# TOOL 9: Get COVID Impact Analysis
# ============================================================================
@mcp.tool()
def get_covid_impact_analysis(state: str | None = None) -> str:
    """
    Analyze the impact of COVID-19 on accident patterns.
    
    Compares accident statistics before (2019), during (2020-2021),
    and after (2022-2023) the pandemic.
    
    Args:
        state: Two-letter state code to filter by. Optional.
    
    Returns:
        JSON string with COVID impact analysis.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        state_condition = "AND State = ?" if state else ""
        base_params = [state.upper()] if state else []
        
        periods = {
            "pre_covid_2019": ("2019-01-01", "2019-12-31"),
            "covid_2020": ("2020-01-01", "2020-12-31"),
            "covid_2021": ("2021-01-01", "2021-12-31"),
            "post_covid_2022": ("2022-01-01", "2022-12-31"),
            "post_covid_2023": ("2023-01-01", "2023-03-31")  # Dataset ends March 2023
        }
        
        results = {}
        for period_name, (start_date, end_date) in periods.items():
            query = f"""
                SELECT 
                    COUNT(*) as accident_count,
                    AVG(Severity) as avg_severity,
                    AVG(Duration_minutes) as avg_duration
                FROM accidents
                WHERE Start_Time BETWEEN ? AND ? {state_condition}
            """
            params = [start_date, end_date] + base_params
            cursor.execute(query, params)
            results[period_name] = dict(cursor.fetchone())
        
        # Calculate changes
        pre_covid = results['pre_covid_2019']['accident_count'] or 1
        covid_2020 = results['covid_2020']['accident_count'] or 0
        
        change_2020 = ((covid_2020 - pre_covid) / pre_covid) * 100
        
        return json.dumps({
            "state_filter": state or "All states",
            "period_statistics": {
                period: {
                    "accident_count": data['accident_count'],
                    "avg_severity": round(data['avg_severity'] or 0, 2),
                    "avg_duration_minutes": round(data['avg_duration'] or 0, 1)
                }
                for period, data in results.items()
            },
            "analysis": {
                "change_2020_vs_2019_percent": round(change_2020, 1),
                "insight": "Positive values indicate more accidents during COVID compared to pre-pandemic."
            }
        }, indent=2)


# ============================================================================
# TOOL 10: Get Real-Time Risk Score
# ============================================================================
@mcp.tool()
def get_realtime_risk_score(
    latitude: float,
    longitude: float,
    hour: int,
    day_of_week: int,
    weather: str = "Clear",
    visibility: float = 10.0
) -> str:
    """
    Calculate a comprehensive real-time risk score for autonomous vehicle.
    
    This is the primary tool for the AV agent to assess current driving
    conditions. It combines location, time, and weather factors into
    a single risk score with actionable recommendations.
    
    Args:
        latitude: Current GPS latitude.
        longitude: Current GPS longitude.
        hour: Current hour (0-23).
        day_of_week: Current day (0=Monday, 6=Sunday).
        weather: Current weather condition (default: "Clear").
        visibility: Current visibility in miles (default: 10.0).
    
    Returns:
        JSON string with comprehensive risk score and recommendations.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Location risk (accidents within ~5 miles)
        lat_range = 0.07  # ~5 miles
        lng_range = 0.09
        
        cursor.execute("""
            SELECT COUNT(*) as count, AVG(Severity) as severity
            FROM accidents
            WHERE Start_Lat BETWEEN ? AND ?
              AND Start_Lng BETWEEN ? AND ?
        """, (latitude - lat_range, latitude + lat_range,
              longitude - lng_range, longitude + lng_range))
        location_data = dict(cursor.fetchone())
        
        # 2. Temporal risk
        cursor.execute("""
            SELECT COUNT(*) as count, AVG(Severity) as severity
            FROM accidents
            WHERE hour_of_day = ? AND day_of_week = ?
        """, (hour, day_of_week))
        temporal_data = dict(cursor.fetchone())
        
        # 3. Weather risk
        cursor.execute("""
            SELECT COUNT(*) as count, AVG(Severity) as severity
            FROM accidents
            WHERE Weather_Condition LIKE ?
        """, (f"%{weather}%",))
        weather_data = dict(cursor.fetchone())
        
        # 4. Visibility risk
        cursor.execute("""
            SELECT AVG(Severity) as severity
            FROM accidents
            WHERE Visibility_mi <= ?
        """, (visibility + 1,))
        visibility_data = dict(cursor.fetchone())
        
        # Calculate component scores (0-100)
        location_score = min(100, (location_data['count'] or 0) / 50 * 100)
        temporal_score = min(100, (temporal_data['count'] or 0) / 10000 * 100)
        
        # Weather score based on severity increase
        cursor.execute("SELECT AVG(Severity) FROM accidents WHERE Weather_Condition LIKE '%Clear%'")
        clear_severity = cursor.fetchone()[0] or 2.0
        weather_severity = weather_data['severity'] or clear_severity
        weather_score = min(100, (weather_severity / clear_severity - 1) * 200 + 50)
        
        # Visibility score
        visibility_score = max(0, 100 - visibility * 10) if visibility < 10 else 0
        
        # Overall risk score (weighted average)
        overall_score = (
            location_score * 0.35 +
            temporal_score * 0.25 +
            weather_score * 0.25 +
            visibility_score * 0.15
        )
        
        # Risk level and recommendations
        if overall_score >= 70:
            risk_level = "CRITICAL"
            speed_adjustment = -15
            recommendations = [
                "Reduce speed by at least 15 mph",
                "Maximize following distance",
                "Enable all safety sensors",
                "Consider stopping if conditions worsen"
            ]
        elif overall_score >= 50:
            risk_level = "HIGH"
            speed_adjustment = -10
            recommendations = [
                "Reduce speed by 10 mph",
                "Increase following distance",
                "Stay alert for sudden hazards"
            ]
        elif overall_score >= 30:
            risk_level = "MODERATE"
            speed_adjustment = -5
            recommendations = [
                "Slight speed reduction recommended",
                "Maintain awareness"
            ]
        else:
            risk_level = "LOW"
            speed_adjustment = 0
            recommendations = [
                "Normal driving conditions",
                "Maintain standard safety protocols"
            ]
        
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        return json.dumps({
            "risk_score": round(overall_score, 1),
            "risk_level": risk_level,
            "component_scores": {
                "location": round(location_score, 1),
                "temporal": round(temporal_score, 1),
                "weather": round(weather_score, 1),
                "visibility": round(visibility_score, 1)
            },
            "current_conditions": {
                "location": {"lat": latitude, "lng": longitude},
                "time": f"{hour}:00 on {day_names[day_of_week]}",
                "weather": weather,
                "visibility_miles": visibility
            },
            "recommendations": {
                "speed_adjustment_mph": speed_adjustment,
                "actions": recommendations
            }
        }, indent=2)


# ============================================================================
# Main entry point
# ============================================================================
if __name__ == "__main__":
    mcp.run()
