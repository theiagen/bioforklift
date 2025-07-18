#!/usr/bin/env python3
"""
Test script to verify mock data generation works correctly
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.services.mock_data_service import MockDataService
import json
from datetime import datetime


def json_serializer(obj):
    """JSON serializer for datetime and date objects"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, 'isoformat'):  # For date objects
        return obj.isoformat()
    raise TypeError(f"Object {obj} is not JSON serializable")


def test_mock_data():
    """Test all mock data generation functions"""
    print("🧪 Testing Mock Data Service...")
    
    service = MockDataService()
    
    # Test daily runs summary
    print("\n📊 Testing daily runs summary...")
    daily_runs = service.get_daily_runs_summary(7)
    print(f"   Generated {len(daily_runs)} daily run records")
    print(f"   Sample: {daily_runs[0] if daily_runs else 'No data'}")
    
    # Test workflow states distribution
    print("\n🔄 Testing workflow states distribution...")
    workflow_states = service.get_workflow_states_distribution(7)
    print(f"   Generated distribution: {workflow_states}")
    print(f"   Total workflows: {sum(workflow_states.values())}")
    
    # Test configuration metrics
    print("\n⚙️  Testing configuration metrics...")
    config_metrics = service.get_configuration_metrics(30)
    print(f"   Generated {len(config_metrics)} configuration records")
    if config_metrics:
        print(f"   Sample config: {config_metrics[0]['config_name']} - {config_metrics[0]['success_rate']:.1f}% success")
    
    # Test recent failures
    print("\n❌ Testing recent failures...")
    failures = service.get_recent_failures(10)
    print(f"   Generated {len(failures)} failure records")
    if failures:
        print(f"   Most recent failure: {failures[0]['entity_identifier']} ({failures[0]['config_name']})")
    
    # Test processing time trends
    print("\n⏱️  Testing processing time trends...")
    trends = service.get_processing_time_trends(14)
    print(f"   Generated {len(trends)} trend records")
    if trends:
        avg_time = sum(t['avg_processing_time_minutes'] for t in trends if t['avg_processing_time_minutes']) / len([t for t in trends if t['avg_processing_time_minutes']])
        print(f"   Average processing time: {avg_time:.1f} minutes")
    
    # Test active configurations
    print("\n🔧 Testing active configurations...")
    active_configs = service.get_active_configurations()
    print(f"   Generated {len(active_configs)} active configurations")
    for config in active_configs[:3]:
        print(f"   - {config['name']} ({config['terra_analysis_method']})")
    
    # Test system health metrics
    print("\n💚 Testing system health metrics...")
    health = service.get_system_health_metrics()
    print(f"   System health: {health}")
    success_rate = (health['successful_last_24h'] / health['samples_last_24h'] * 100) if health['samples_last_24h'] > 0 else 0
    print(f"   24h success rate: {success_rate:.1f}%")
    
    print("\n✅ All mock data tests completed successfully!")
    
    # Generate sample dashboard data
    print("\n📋 Generating sample dashboard data...")
    dashboard_data = {
        'daily_runs': daily_runs[:5],  # Last 5 days
        'workflow_distribution': {'workflow_states': workflow_states, 'total_workflows': sum(workflow_states.values())},
        'configuration_metrics': config_metrics[:3],  # Top 3 configs
        'recent_failures': failures[:5],  # Last 5 failures
        'processing_trends': trends[:5],  # Last 5 days of trends
        'active_configurations': active_configs[:3],  # First 3 active configs
        'system_health': health
    }
    
    # Save to file for inspection
    with open('sample_dashboard_data.json', 'w') as f:
        json.dump(dashboard_data, f, indent=2, default=json_serializer)
    
    print("   Sample data saved to 'sample_dashboard_data.json'")
    print("\n🎉 Mock data service is ready for testing!")


if __name__ == "__main__":
    test_mock_data()