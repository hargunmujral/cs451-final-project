"""
MCP Server for US Accidents Dataset (2016-2023)
Powers an Autonomous Vehicle Agent with accident hotspot and risk analysis tools.

OPTIMIZED VERSION - Uses pre-aggregated summary tables for instant queries.
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


# ============================================================================
# TOOL 1: Get Accident Hotspots by Region (OPTIMIZED)
# ============================================================================
@mcp.tool()
def get_accident_hotspots(
    state: str | None = None,
    city: str | None = None,
    limit: int = 10
) -> str:
    """
    Get accident hotspot locations ranked by accident frequency.
    
    Args:
        state: Two-letter state code (e.g., 'CA', 'TX', 'FL'). Optional.
        city: City name to filter by. Optional.
        limit: Maximum number of hotspots to return (default: 10).
    
    Returns:
        JSON string with hotspot locations and accident counts.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        conditions = []
        params = []
        
        if state:
            conditions.append("State = ?")
            params.append(state.upper())
        if city:
            conditions.append("City LIKE ?")
            params.append(f"%{city}%")
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        # Use pre-aggregated city_stats table
        query = f"""
            SELECT City, State, County, accident_count, avg_severity, center_lat, center_lng
            FROM city_stats
            {where_clause}
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
    
    Args:
        latitude: GPS latitude coordinate.
        longitude: GPS longitude coordinate.
        radius_miles: Search radius in miles (default: 5.0).
        limit: Maximum number of accidents to return (default: 50).
    
    Returns:
        JSON string with nearby accidents and summary statistics.
    """
    import math
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        lat_range = radius_miles / 69.0
        lng_range = radius_miles / (69.0 * abs(math.cos(math.radians(latitude))))
        
        query = """
            SELECT ID, Severity, Start_Time, Start_Lat, Start_Lng, Street, City, Weather_Condition
            FROM accidents
            WHERE Start_Lat BETWEEN ? AND ?
              AND Start_Lng BETWEEN ? AND ?
            ORDER BY Severity DESC
            LIMIT ?
        """
        
        cursor.execute(query, (
            latitude - lat_range, latitude + lat_range,
            longitude - lng_range, longitude + lng_range,
            limit
        ))
        
        accidents = [dict(row) for row in cursor.fetchall()]
        
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
            "accidents": accidents[:20]
        }, indent=2)


# ============================================================================
# TOOL 3: Get Risk Assessment for Time Period (OPTIMIZED)
# ============================================================================
@mcp.tool()
def get_temporal_risk_assessment(
    hour_of_day: int,
    day_of_week: int | None = None,
    state: str | None = None
) -> str:
    """
    Get accident risk assessment based on time of day and day of week.
    
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
        
        # Use pre-aggregated hourly_dow_stats table
        query = f"""
            SELECT 
                SUM(accident_count) as accident_count,
                SUM(accident_count * avg_severity) / SUM(accident_count) as avg_severity,
                SUM(severe_count) as severe_accidents
            FROM hourly_dow_stats
            WHERE {where_clause}
        """
        
        cursor.execute(query, params)
        result = dict(cursor.fetchone())
        
        # Get global average from pre-computed table
        cursor.execute("SELECT avg_hourly FROM global_stats")
        avg_hourly = cursor.fetchone()[0]
        
        accident_count = result['accident_count'] or 0
        if accident_count > avg_hourly * 1.5:
            risk_level = "HIGH"
            recommendation = "Exercise extreme caution. Reduce speed and increase following distance."
        elif accident_count > avg_hourly:
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
                "total_accidents": accident_count,
                "average_severity": round(result['avg_severity'] or 0, 2),
                "severe_accidents_count": result['severe_accidents'] or 0
            },
            "risk_assessment": {
                "level": risk_level,
                "recommendation": recommendation
            }
        }, indent=2)


# ============================================================================
# TOOL 4: Get Weather-Based Risk Assessment (OPTIMIZED)
# ============================================================================
@mcp.tool()
def get_weather_risk_assessment(
    weather_condition: str,
    visibility_miles: float | None = None,
    state: str | None = None
) -> str:
    """
    Get accident risk assessment based on weather conditions.
    
    Args:
        weather_condition: Current weather (e.g., 'Rain', 'Snow', 'Fog', 'Clear').
        visibility_miles: Current visibility in miles. Optional.
        state: Two-letter state code to filter by. Optional.
    
    Returns:
        JSON string with weather-related risk analysis.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        conditions = ["Weather_Condition LIKE ?"]
        params = [f"%{weather_condition}%"]
        
        if state:
            conditions.append("State = ?")
            params.append(state.upper())
        
        where_clause = " AND ".join(conditions)
        
        # Use pre-aggregated weather_stats table
        query = f"""
            SELECT 
                SUM(accident_count) as accident_count,
                SUM(accident_count * avg_severity) / SUM(accident_count) as avg_severity,
                SUM(accident_count * avg_visibility) / SUM(accident_count) as avg_visibility,
                SUM(severe_count) as severe_count
            FROM weather_stats
            WHERE {where_clause}
        """
        
        cursor.execute(query, params)
        result = dict(cursor.fetchone())
        
        # Get clear weather baseline from global_stats
        cursor.execute("SELECT clear_weather_severity FROM global_stats")
        clear_severity = cursor.fetchone()[0] or 2.0
        
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
                "accidents_in_similar_conditions": result['accident_count'] or 0,
                "average_severity": round(current_severity, 2),
                "severe_accidents": result['severe_count'] or 0,
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
    
    Args:
        waypoints: List of GPS coordinates as dicts with 'lat' and 'lng' keys.
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
            
            min_lat = min(start['lat'], end['lat']) - 0.05
            max_lat = max(start['lat'], end['lat']) + 0.05
            min_lng = min(start['lng'], end['lng']) - 0.05
            max_lng = max(start['lng'], end['lng']) + 0.05
            
            # Simple location-based query (fast with indexes)
            query = """
                SELECT COUNT(*) as cnt, AVG(Severity) as sev, MAX(Severity) as max_sev
                FROM accidents
                WHERE Start_Lat BETWEEN ? AND ? AND Start_Lng BETWEEN ? AND ?
            """
            cursor.execute(query, (min_lat, max_lat, min_lng, max_lng))
            result = dict(cursor.fetchone())
            
            segment_accidents = result['cnt'] or 0
            segment_severity = result['sev'] or 0
            
            total_accidents += segment_accidents
            max_severity = max(max_severity, result['max_sev'] or 0)
            
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
                "risk_level": segment_risk
            })
        
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
            "context": {"time_of_day": time_of_day, "weather": weather},
            "segment_analysis": segment_analyses
        }, indent=2)


# ============================================================================
# TOOL 6: Get Road Feature Risk Analysis (OPTIMIZED)
# ============================================================================
@mcp.tool()
def get_road_feature_risk(
    feature: str,
    state: str | None = None
) -> str:
    """
    Analyze accident risk associated with specific road features.
    
    Args:
        feature: Road feature to analyze. Options: 'crossing', 'junction',
                 'traffic_signal', 'stop', 'railway', 'roundabout', 'bump'.
        state: Two-letter state code to filter by. Optional.
    
    Returns:
        JSON string with road feature risk analysis.
    """
    valid_features = ['crossing', 'junction', 'traffic_signal', 'stop', 'railway', 'roundabout', 'bump']
    feature_lower = feature.lower()
    
    if feature_lower not in valid_features:
        return json.dumps({"error": f"Unknown feature: {feature}", "available_features": valid_features})
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        state_condition = "AND State = ?" if state else ""
        params = [feature_lower] + ([state.upper()] if state else [])
        
        # Use pre-aggregated road_feature_stats table
        query = f"""
            SELECT has_feature, SUM(cnt) as count, 
                   SUM(cnt * sev) / SUM(cnt) as avg_severity,
                   SUM(cnt * dur) / SUM(cnt) as avg_duration
            FROM road_feature_stats
            WHERE feature = ? {state_condition}
            GROUP BY has_feature
        """
        
        cursor.execute(query, params)
        results = {row['has_feature']: dict(row) for row in cursor.fetchall()}
        
        with_feature = results.get(1, {'count': 0, 'avg_severity': 0, 'avg_duration': 0})
        without_feature = results.get(0, {'count': 0, 'avg_severity': 0, 'avg_duration': 0})
        
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
# TOOL 7: Get State Statistics Summary (OPTIMIZED)
# ============================================================================
@mcp.tool()
def get_state_statistics(state: str) -> str:
    """
    Get comprehensive accident statistics for a specific state.
    
    Args:
        state: Two-letter state code (e.g., 'CA', 'TX', 'FL').
    
    Returns:
        JSON string with comprehensive state accident statistics.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        state_upper = state.upper()
        
        # Overall stats from state_summary table
        cursor.execute("SELECT * FROM state_summary WHERE State = ?", (state_upper,))
        overall = dict(cursor.fetchone() or {})
        
        # Top 5 cities from city_stats
        cursor.execute("""
            SELECT City, accident_count as count
            FROM city_stats WHERE State = ?
            ORDER BY accident_count DESC LIMIT 5
        """, (state_upper,))
        top_cities = [dict(row) for row in cursor.fetchall()]
        
        # Peak hours from hourly_dow_stats
        cursor.execute("""
            SELECT hour_of_day, SUM(accident_count) as count
            FROM hourly_dow_stats WHERE State = ?
            GROUP BY hour_of_day ORDER BY count DESC LIMIT 5
        """, (state_upper,))
        peak_hours = [dict(row) for row in cursor.fetchall()]
        
        # Top weather conditions from weather_stats
        cursor.execute("""
            SELECT Weather_Condition, accident_count as count
            FROM weather_stats WHERE State = ?
            ORDER BY accident_count DESC LIMIT 5
        """, (state_upper,))
        weather_conditions = [dict(row) for row in cursor.fetchall()]
        
        return json.dumps({
            "state": state_upper,
            "overall_statistics": {
                "total_accidents": overall.get('total_accidents', 0),
                "average_severity": round(overall.get('avg_severity', 0) or 0, 2),
                "average_duration_minutes": round(overall.get('avg_duration', 0) or 0, 1),
                "data_range": {
                    "from": overall.get('earliest_record', ''),
                    "to": overall.get('latest_record', '')
                }
            },
            "top_accident_cities": top_cities,
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
            SELECT ID, Severity, Start_Time, City, State, Street, Weather_Condition, Description
            FROM accidents
            WHERE {" AND ".join(conditions)}
            ORDER BY Severity DESC
            LIMIT ?
        """
        
        cursor.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        
        return json.dumps({
            "search_terms": keywords,
            "filters": {"state": state, "min_severity": min_severity},
            "results_count": len(results),
            "accidents": results
        }, indent=2)


# ============================================================================
# TOOL 9: Get COVID Impact Analysis (OPTIMIZED)
# ============================================================================
@mcp.tool()
def get_covid_impact_analysis(state: str | None = None) -> str:
    """
    Analyze the impact of COVID-19 on accident patterns.
    
    Args:
        state: Two-letter state code to filter by. Optional.
    
    Returns:
        JSON string with COVID impact analysis.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if state:
            query = """
                SELECT year, accident_count, avg_severity, avg_duration
                FROM yearly_state_stats
                WHERE State = ? AND year IN ('2019', '2020', '2021', '2022', '2023')
                ORDER BY year
            """
            cursor.execute(query, (state.upper(),))
        else:
            query = """
                SELECT year, SUM(accident_count) as accident_count, 
                       SUM(accident_count * avg_severity) / SUM(accident_count) as avg_severity,
                       SUM(accident_count * avg_duration) / SUM(accident_count) as avg_duration
                FROM yearly_state_stats
                WHERE year IN ('2019', '2020', '2021', '2022', '2023')
                GROUP BY year ORDER BY year
            """
            cursor.execute(query)
        
        results = {row['year']: dict(row) for row in cursor.fetchall()}
        
        periods = {
            "pre_covid_2019": results.get('2019', {}),
            "covid_2020": results.get('2020', {}),
            "covid_2021": results.get('2021', {}),
            "post_covid_2022": results.get('2022', {}),
            "post_covid_2023": results.get('2023', {})
        }
        
        pre_covid = periods['pre_covid_2019'].get('accident_count', 1) or 1
        covid_2020 = periods['covid_2020'].get('accident_count', 0) or 0
        change_2020 = ((covid_2020 - pre_covid) / pre_covid) * 100
        
        return json.dumps({
            "state_filter": state or "All states",
            "period_statistics": {
                period: {
                    "accident_count": data.get('accident_count', 0),
                    "avg_severity": round(data.get('avg_severity', 0) or 0, 2),
                    "avg_duration_minutes": round(data.get('avg_duration', 0) or 0, 1)
                }
                for period, data in periods.items()
            },
            "analysis": {
                "change_2020_vs_2019_percent": round(change_2020, 1),
                "insight": "Positive values indicate more accidents during COVID compared to pre-pandemic."
            }
        }, indent=2)


# ============================================================================
# TOOL 10: Get Real-Time Risk Score (OPTIMIZED)
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
        
        # 1. Location risk (use city_stats for nearby areas)
        lat_range = 0.07
        lng_range = 0.09
        
        cursor.execute("""
            SELECT SUM(accident_count) as count, 
                   SUM(accident_count * avg_severity) / SUM(accident_count) as severity
            FROM city_stats
            WHERE center_lat BETWEEN ? AND ? AND center_lng BETWEEN ? AND ?
        """, (latitude - lat_range, latitude + lat_range,
              longitude - lng_range, longitude + lng_range))
        location_data = dict(cursor.fetchone())
        
        # 2. Temporal risk from hourly_dow_stats
        cursor.execute("""
            SELECT SUM(accident_count) as count
            FROM hourly_dow_stats
            WHERE hour_of_day = ? AND day_of_week = ?
        """, (hour, day_of_week))
        temporal_data = dict(cursor.fetchone())
        
        # 3. Weather risk from weather_stats
        cursor.execute("""
            SELECT SUM(accident_count) as count,
                   SUM(accident_count * avg_severity) / SUM(accident_count) as severity
            FROM weather_stats
            WHERE Weather_Condition LIKE ?
        """, (f"%{weather}%",))
        weather_data = dict(cursor.fetchone())
        
        # Get global stats for scoring
        cursor.execute("SELECT avg_hourly, clear_weather_severity FROM global_stats")
        global_stats = dict(cursor.fetchone())
        
        # Calculate component scores (0-100)
        location_score = min(100, (location_data['count'] or 0) / 1000 * 100)
        temporal_score = min(100, (temporal_data['count'] or 0) / (global_stats['avg_hourly'] * 2) * 100)
        
        weather_severity = weather_data['severity'] or global_stats['clear_weather_severity']
        clear_severity = global_stats['clear_weather_severity'] or 2.0
        weather_score = min(100, (weather_severity / clear_severity - 1) * 200 + 50)
        
        visibility_score = max(0, 100 - visibility * 10) if visibility < 10 else 0
        
        overall_score = (
            location_score * 0.35 +
            temporal_score * 0.25 +
            weather_score * 0.25 +
            visibility_score * 0.15
        )
        
        if overall_score >= 70:
            risk_level = "CRITICAL"
            speed_adjustment = -15
            recommendations = ["Reduce speed by at least 15 mph", "Maximize following distance", 
                             "Enable all safety sensors", "Consider stopping if conditions worsen"]
        elif overall_score >= 50:
            risk_level = "HIGH"
            speed_adjustment = -10
            recommendations = ["Reduce speed by 10 mph", "Increase following distance", 
                             "Stay alert for sudden hazards"]
        elif overall_score >= 30:
            risk_level = "MODERATE"
            speed_adjustment = -5
            recommendations = ["Slight speed reduction recommended", "Maintain awareness"]
        else:
            risk_level = "LOW"
            speed_adjustment = 0
            recommendations = ["Normal driving conditions", "Maintain standard safety protocols"]
        
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
