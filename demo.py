#!/usr/bin/env python
"""
Demo script showing the MCP server capabilities.
Run this to see example outputs from all tools.
"""

import json
from mcp_server.server import (
    get_accident_hotspots,
    get_accidents_near_location,
    get_temporal_risk_assessment,
    get_weather_risk_assessment,
    analyze_route_risk,
    get_road_feature_risk,
    get_state_statistics,
    search_accident_descriptions,
    get_covid_impact_analysis,
    get_realtime_risk_score
)


def print_section(title):
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


def main():
    print("\n🚗 US Accidents MCP Server - Demo\n")
    
    # 1. Accident Hotspots
    print_section("1. Top 5 Accident Hotspots in Texas")
    result = json.loads(get_accident_hotspots(state="TX", limit=5))
    for h in result["hotspots"]:
        print(f"  {h['City']}: {h['accident_count']:,} accidents (avg severity: {h['avg_severity']:.2f})")
    
    # 2. Accidents near a location (Los Angeles)
    print_section("2. Accidents Near Downtown LA (34.05, -118.25)")
    result = json.loads(get_accidents_near_location(latitude=34.05, longitude=-118.25, radius_miles=2))
    print(f"  Found {result['accidents_found']} accidents within 2 miles")
    print(f"  Average severity: {result['average_severity']}")
    print(f"  Severity distribution: {result['severity_distribution']}")
    
    # 3. Temporal Risk Assessment
    print_section("3. Risk Assessment: 8 AM Monday (Rush Hour)")
    result = json.loads(get_temporal_risk_assessment(hour_of_day=8, day_of_week=0))
    print(f"  Risk Level: {result['risk_assessment']['level']}")
    print(f"  Total accidents at this time: {result['statistics']['total_accidents']:,}")
    print(f"  Recommendation: {result['risk_assessment']['recommendation']}")
    
    # 4. Weather Risk Assessment
    print_section("4. Weather Risk Assessment: Heavy Rain")
    result = json.loads(get_weather_risk_assessment(weather_condition="Heavy Rain", visibility_miles=2))
    print(f"  Risk Level: {result['risk_assessment']['level']}")
    print(f"  Risk Multiplier: {result['risk_assessment']['risk_multiplier']}x")
    print(f"  Accidents in similar conditions: {result['statistics']['accidents_in_similar_conditions']:,}")
    print(f"  Recommendation: {result['risk_assessment']['recommendation']}")
    
    # 5. Route Risk Analysis
    print_section("5. Route Analysis: San Francisco to San Jose")
    waypoints = [
        {"lat": 37.77, "lng": -122.42},  # SF
        {"lat": 37.55, "lng": -122.30},  # Midpoint
        {"lat": 37.33, "lng": -121.89}   # San Jose
    ]
    result = json.loads(analyze_route_risk(waypoints=waypoints, time_of_day=17, weather="Clear"))
    print(f"  Overall Risk: {result['route_summary']['overall_risk']}")
    print(f"  Total historical accidents along route: {result['route_summary']['total_historical_accidents']:,}")
    print(f"  Recommendation: {result['route_summary']['recommendation']}")
    
    # 6. Road Feature Risk
    print_section("6. Road Feature Risk: Traffic Signals")
    result = json.loads(get_road_feature_risk(feature="traffic_signal"))
    print(f"  Risk Level: {result['risk_assessment']['level']}")
    print(f"  Accidents at traffic signals: {result['with_feature']['accident_count']:,}")
    print(f"  Severity increase: {result['risk_assessment']['severity_increase_percent']:.1f}%")
    
    # 7. State Statistics
    print_section("7. California State Statistics")
    result = json.loads(get_state_statistics(state="CA"))
    print(f"  Total accidents: {result['overall_statistics']['total_accidents']:,}")
    print(f"  Average severity: {result['overall_statistics']['average_severity']}")
    print(f"  Top city: {result['top_accident_cities'][0]['City']} ({result['top_accident_cities'][0]['count']:,} accidents)")
    print(f"  Peak hour: {result['peak_accident_hours'][0]['hour_of_day']}:00")
    
    # 8. Search Descriptions
    print_section("8. Search: 'ice' in Accident Descriptions (Severity 3+)")
    result = json.loads(search_accident_descriptions(keywords="ice", min_severity=3, limit=3))
    print(f"  Found {result['results_count']} matching accidents")
    if result['accidents']:
        print(f"  Example: {result['accidents'][0]['City']}, {result['accidents'][0]['State']}")
        print(f"           {result['accidents'][0]['Description'][:100]}...")
    
    # 9. COVID Impact
    print_section("9. COVID-19 Impact Analysis (California)")
    result = json.loads(get_covid_impact_analysis(state="CA"))
    print(f"  2019 (pre-COVID): {result['period_statistics']['pre_covid_2019']['accident_count']:,} accidents")
    print(f"  2020 (COVID): {result['period_statistics']['covid_2020']['accident_count']:,} accidents")
    print(f"  Change: {result['analysis']['change_2020_vs_2019_percent']:+.1f}%")
    
    # 10. Real-Time Risk Score (Primary AV Tool)
    print_section("10. REAL-TIME RISK SCORE - Primary AV Tool")
    print("  Scenario: Miami Beach, 6 PM Friday, Rainy, 4-mile visibility")
    result = json.loads(get_realtime_risk_score(
        latitude=25.79,
        longitude=-80.13,
        hour=18,
        day_of_week=4,
        weather="Rain",
        visibility=4.0
    ))
    print(f"\n  🚨 RISK SCORE: {result['risk_score']}/100 ({result['risk_level']})")
    print(f"\n  Component Scores:")
    for component, score in result['component_scores'].items():
        print(f"    - {component.capitalize()}: {score}/100")
    print(f"\n  📋 Recommendations:")
    print(f"    Speed adjustment: {result['recommendations']['speed_adjustment_mph']} mph")
    for action in result['recommendations']['actions']:
        print(f"    • {action}")
    
    print("\n" + "="*60)
    print("  Demo Complete! These tools are now available via MCP.")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
