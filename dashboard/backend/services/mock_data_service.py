import random
from datetime import datetime, timedelta, date
from typing import List, Dict, Any
import uuid
from faker import Faker

fake = Faker()


class MockDataService:
    """Mock data service for testing dashboard visualizations locally"""
    
    def __init__(self):
        self.workflow_states = ['Succeeded', 'Failed', 'Aborted', 'Running', 'Queued', 'Submitted']
        self.config_names = [
            'COVID-19 Sequencing Pipeline',
            'TB Drug Resistance Analysis',
            'Flu Strain Classification',
            'Bacterial Genomics QC',
            'Viral Metagenomics',
            'AMR Detection Pipeline',
            'Outbreak Investigation',
            'Reference Genome Assembly'
        ]
        
        # Generate consistent config IDs
        self.configs = [
            {
                'id': f'config-{i:03d}',
                'name': name,
                'state': fake.state(),
                'prefix': name.lower().replace(' ', '_')[:10],
                'terra_analysis_method': f'Pipeline_{fake.random_element(["Illumina_PE", "ONT", "Illumina_SE"])}',
                'active': random.choice([True, True, True, False]),  # 75% active
                'created_at': fake.date_time_between(start_date='-1y', end_date='now'),
                'updated_at': fake.date_time_between(start_date='-1m', end_date='now')
            }
            for i, name in enumerate(self.config_names)
        ]
    
    def get_daily_runs_summary(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """Generate mock daily runs summary"""
        data = []
        
        for i in range(days_back):
            run_date = date.today() - timedelta(days=i)
            
            # Generate realistic patterns - more activity on weekdays
            is_weekend = run_date.weekday() >= 5
            base_runs = random.randint(10, 30) if not is_weekend else random.randint(5, 15)
            
            # Add some randomness but keep success rate realistic
            total_runs = base_runs + random.randint(-5, 10)
            total_runs = max(1, total_runs)  # Ensure at least 1 run
            
            success_rate = random.uniform(0.75, 0.95)  # 75-95% success rate
            successful_runs = int(total_runs * success_rate)
            
            # Distribute remaining runs
            remaining = total_runs - successful_runs
            failed_runs = random.randint(0, remaining)
            aborted_runs = random.randint(0, remaining - failed_runs)
            in_progress_runs = remaining - failed_runs - aborted_runs
            
            data.append({
                'date': run_date,
                'total_runs': total_runs,
                'successful_runs': successful_runs,
                'failed_runs': failed_runs,
                'aborted_runs': aborted_runs,
                'in_progress_runs': in_progress_runs
            })
        
        return data
    
    def get_workflow_states_distribution(self, days_back: int = 7) -> Dict[str, int]:
        """Generate mock workflow states distribution"""
        total_workflows = random.randint(100, 500)
        
        # Realistic distribution
        distribution = {
            'Succeeded': int(total_workflows * random.uniform(0.70, 0.85)),
            'Failed': int(total_workflows * random.uniform(0.05, 0.15)),
            'Running': int(total_workflows * random.uniform(0.02, 0.08)),
            'Queued': int(total_workflows * random.uniform(0.01, 0.05)),
            'Aborted': int(total_workflows * random.uniform(0.01, 0.03)),
            'Submitted': int(total_workflows * random.uniform(0.01, 0.02))
        }
        
        # Adjust to match total
        current_total = sum(distribution.values())
        if current_total != total_workflows:
            diff = total_workflows - current_total
            distribution['Succeeded'] += diff
        
        return distribution
    
    def get_configuration_metrics(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """Generate mock configuration metrics"""
        data = []
        
        for config in self.configs[:6]:  # Use first 6 configs
            total_samples = random.randint(20, 200)
            success_rate = random.uniform(0.60, 0.95)
            successful_samples = int(total_samples * success_rate)
            failed_samples = total_samples - successful_samples
            
            # Processing time varies by pipeline complexity
            avg_processing_time = random.uniform(15, 180)  # 15 minutes to 3 hours
            
            data.append({
                'config_id': config['id'],
                'config_name': config['name'],
                'total_samples': total_samples,
                'successful_samples': successful_samples,
                'failed_samples': failed_samples,
                'success_rate': success_rate * 100,
                'avg_processing_time_minutes': avg_processing_time
            })
        
        return sorted(data, key=lambda x: x['total_samples'], reverse=True)
    
    def get_recent_failures(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Generate mock recent failures"""
        data = []
        
        for _ in range(min(limit, random.randint(5, 25))):
            config = random.choice(self.configs)
            created_at = fake.date_time_between(start_date='-7d', end_date='now')
            submitted_at = created_at + timedelta(minutes=random.randint(5, 60))
            
            data.append({
                'entity_identifier': f'SAMPLE_{fake.random_int(1000, 9999)}',
                'config_id': config['id'],
                'config_name': config['name'],
                'workflow_state': 'Failed',
                'created_at': created_at,
                'submitted_at': submitted_at,
                'terra_submission_id': f'sub_{uuid.uuid4().hex[:8]}',
                'terra_workflow_id': f'wf_{uuid.uuid4().hex[:8]}'
            })
        
        return sorted(data, key=lambda x: x['created_at'], reverse=True)
    
    def get_processing_time_trends(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """Generate mock processing time trends"""
        data = []
        
        base_time = 60  # Base processing time in minutes
        
        for i in range(days_back):
            trend_date = date.today() - timedelta(days=i)
            
            # Add some trend - processing times might increase over time due to data complexity
            time_trend = i * 0.5  # Slight increase over time
            daily_variation = random.uniform(-15, 15)  # Daily variation
            
            avg_time = base_time + time_trend + daily_variation
            avg_time = max(10, avg_time)  # Minimum 10 minutes
            
            sample_count = random.randint(5, 50)
            
            data.append({
                'date': trend_date,
                'avg_processing_time_minutes': avg_time,
                'sample_count': sample_count
            })
        
        return data
    
    def get_active_configurations(self) -> List[Dict[str, Any]]:
        """Get mock active configurations"""
        return [config for config in self.configs if config['active']]
    
    def get_system_health_metrics(self) -> Dict[str, Any]:
        """Generate mock system health metrics"""
        total_samples = random.randint(1000, 5000)
        samples_24h = random.randint(50, 200)
        
        success_rate = random.uniform(0.80, 0.95)
        successful_24h = int(samples_24h * success_rate)
        failed_24h = samples_24h - successful_24h
        
        return {
            'total_samples': total_samples,
            'samples_last_24h': samples_24h,
            'successful_last_24h': successful_24h,
            'failed_last_24h': failed_24h,
            'currently_in_progress': random.randint(5, 25),
            'success_rate_24h': (successful_24h / samples_24h) * 100 if samples_24h > 0 else 0,
            'failure_rate_24h': (failed_24h / samples_24h) * 100 if samples_24h > 0 else 0
        }