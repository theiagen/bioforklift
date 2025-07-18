# Bioforklift Monitoring Dashboard

A lightweight monitoring dashboard for visualizing the status of daily runs and workflow performance in bioforklift. The dashboard provides real-time insights into system health, processing trends, and failure analysis.

## Features

### 📊 Dashboard Components
- **System Health Overview**: Real-time metrics for the last 24 hours
- **Daily Runs Trend**: Historical view of workflow execution counts and success rates
- **Workflow State Distribution**: Visual breakdown of current workflow states
- **Configuration Performance**: Success rates and processing times by configuration
- **Recent Failures**: Detailed view of failed workflows for debugging
- **Processing Time Trends**: Performance trends over time

### 🚀 Technology Stack
- **Backend**: FastAPI with Python 3.11+
- **Frontend**: Svelte with TypeScript and Tailwind CSS
- **Data Source**: Google BigQuery (existing bioforklift data)
- **Visualization**: Chart.js for interactive charts
- **Deployment**: Docker with docker-compose

## Prerequisites

- Docker and Docker Compose
- Access to Google BigQuery with bioforklift data
- Google Cloud credentials (service account or default application credentials)

## Quick Start

### 1. Clone and Setup

```bash
# Navigate to the dashboard directory
cd dashboard

# Copy environment configuration
cp .env.example .env

# For local testing with mock data (recommended for first time)
# No additional configuration needed - mock data is enabled by default
```

### 2. Configure Environment

#### Option A: Use Mock Data (Recommended for Testing)
The dashboard comes with realistic mock data enabled by default. No BigQuery setup required!

```bash
# .env file (default configuration)
MOCK_DATA=true
```

#### Option B: Use Real BigQuery Data
Edit `.env` file for production use:

```bash
# Disable mock data
MOCK_DATA=false

# BigQuery Configuration
BIGQUERY_PROJECT_ID=your-gcp-project-id
BIGQUERY_DATASET_ID=your-bigquery-dataset
BIGQUERY_SAMPLES_TABLE=samples
BIGQUERY_CONFIGS_TABLE=configs

# Google Cloud Authentication
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

### 3. Run with Docker Compose

#### Production Mode
```bash
# Start the dashboard
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the dashboard
docker-compose down
```

#### Development Mode
```bash
# Start in development mode with hot reload
docker-compose --profile dev up -d

# The frontend will be available at http://localhost:5173
# The backend will be available at http://localhost:8000
```

### 4. Access the Dashboard

- **Production**: http://localhost:3000
- **Development**: http://localhost:5173
- **API Documentation**: http://localhost:8000/docs

## Development Setup

### Backend Development

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export BIGQUERY_PROJECT_ID=your-project
export BIGQUERY_DATASET_ID=your-dataset
# ... other variables

# Run development server
python start.py
```

### Frontend Development

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MOCK_DATA` | No | `true` | Use mock data for testing (true/false) |
| `BIGQUERY_PROJECT_ID` | Conditional* | - | GCP project ID containing BigQuery dataset |
| `BIGQUERY_DATASET_ID` | Conditional* | - | BigQuery dataset name with bioforklift tables |
| `BIGQUERY_SAMPLES_TABLE` | No | `samples` | Name of the samples table |
| `BIGQUERY_CONFIGS_TABLE` | No | `configs` | Name of the configurations table |
| `GOOGLE_APPLICATION_CREDENTIALS` | Conditional* | - | Path to service account key file |
| `HOST` | No | `0.0.0.0` | Backend host address |
| `PORT` | No | `8000` | Backend port number |
| `LOG_LEVEL` | No | `info` | Log level (debug, info, warning, error) |

*Required only when `MOCK_DATA=false`

### BigQuery Tables

The dashboard expects the following table structure:

#### Samples Table
- `id` (STRING): Unique identifier
- `entity_identifier` (STRING): Sample identifier
- `config_id` (STRING): Configuration ID
- `workflow_state` (STRING): Current workflow state
- `created_at` (TIMESTAMP): Creation timestamp
- `submitted_at` (TIMESTAMP): Submission timestamp
- `terra_submission_id` (STRING): Terra submission ID
- `terra_workflow_id` (STRING): Terra workflow ID

#### Configs Table
- `id` (STRING): Configuration ID
- `name` (STRING): Configuration name
- `active` (BOOLEAN): Whether configuration is active
- `created_at` (TIMESTAMP): Creation timestamp

## API Endpoints

### Metrics Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/metrics/daily-runs` | GET | Daily runs summary |
| `/api/v1/metrics/workflow-states` | GET | Workflow state distribution |
| `/api/v1/metrics/configurations` | GET | Configuration performance metrics |
| `/api/v1/metrics/recent-failures` | GET | Recent failed workflows |
| `/api/v1/metrics/processing-times` | GET | Processing time trends |
| `/api/v1/metrics/system-health` | GET | System health overview |
| `/api/v1/metrics/dashboard` | GET | All metrics in single request |

### Utility Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/metrics/cache/clear` | POST | Clear query cache |

## Deployment

### Production Deployment

1. **Prepare Environment**
   ```bash
   # Copy and configure environment
   cp .env.example .env
   # Edit .env with production values
   ```

2. **Deploy with Docker Compose**
   ```bash
   # Start services
   docker-compose up -d
   
   # Check health
   curl http://localhost:8000/health
   curl http://localhost:3000
   ```

3. **Configure Reverse Proxy** (Optional)
   ```nginx
   # Nginx example
   server {
       listen 80;
       server_name your-domain.com;
       
       location / {
           proxy_pass http://localhost:3000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
       
       location /api/ {
           proxy_pass http://localhost:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

### Google Cloud Run Deployment

1. **Build and Push Images**
   ```bash
   # Build backend
   cd backend
   gcloud builds submit --tag gcr.io/PROJECT-ID/bioforklift-dashboard-backend
   
   # Build frontend
   cd ../frontend
   gcloud builds submit --tag gcr.io/PROJECT-ID/bioforklift-dashboard-frontend
   ```

2. **Deploy Services**
   ```bash
   # Deploy backend
   gcloud run deploy bioforklift-backend \
       --image gcr.io/PROJECT-ID/bioforklift-dashboard-backend \
       --platform managed \
       --region us-central1 \
       --allow-unauthenticated
   
   # Deploy frontend
   gcloud run deploy bioforklift-frontend \
       --image gcr.io/PROJECT-ID/bioforklift-dashboard-frontend \
       --platform managed \
       --region us-central1 \
       --allow-unauthenticated
   ```

## Monitoring & Maintenance

### Health Checks

- Backend: `GET /health`
- Frontend: Available on main URL
- Docker health checks included in compose file

### Logs

```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f backend
docker-compose logs -f frontend
```

### Cache Management

The dashboard includes a 5-minute TTL cache for BigQuery queries. To clear cache:

```bash
curl -X POST http://localhost:8000/api/v1/metrics/cache/clear
```

## Troubleshooting

### Common Issues

1. **BigQuery Connection Failed**
   - Verify `BIGQUERY_PROJECT_ID` and `BIGQUERY_DATASET_ID`
   - Check Google Cloud credentials
   - Ensure tables exist and have correct schema

2. **Frontend Can't Connect to Backend**
   - Verify backend is running on port 8000
   - Check CORS configuration
   - Ensure API base URL is correct in frontend

3. **No Data Displayed**
   - Check if tables contain data
   - Verify table names match configuration
   - Check query logs in backend

4. **Docker Issues**
   - Ensure Docker daemon is running
   - Check port conflicts (8000, 3000, 5173)
   - Verify environment file is properly configured

### Debug Mode

```bash
# Test mock data generation
python test-mock-data.py

# Run backend in debug mode
export LOG_LEVEL=debug
python start.py

# Run with development profile
docker-compose --profile dev up
```

### Mock Data Testing

To test the visualizations with realistic mock data:

```bash
# Test mock data generation
python test-mock-data.py

# This will generate sample data and save it to 'sample_dashboard_data.json'
# You can inspect this file to see the structure of generated data
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is part of the bioforklift package and follows the same license terms.