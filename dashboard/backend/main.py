from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
import logging
from contextlib import asynccontextmanager
from typing import Union
from api.metrics import router as metrics_router
from api.auth import router as auth_router
from services.data_service_factory import DataServiceFactory
from services.bigquery_service import BigQueryService
from services.mock_data_service import MockDataService
from auth.oauth import validate_oauth_config, get_target_project_config, is_development_mode
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global service instance
data_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global data_service
    
    # Startup
    logger.info("Starting bioforklift monitoring dashboard")
    
    # Validate OAuth configuration
    try:
        if not is_development_mode():
            validate_oauth_config()
            target_project_id, dataset_id = get_target_project_config()
            logger.info(f"OAuth configured for project: {target_project_id}, dataset: {dataset_id}")
        else:
            logger.info("Running in development mode - OAuth validation relaxed")
    except Exception as e:
        logger.error(f"OAuth configuration validation failed: {e}")
        if not is_development_mode():
            raise
    
    # Initialize data service (BigQuery or Mock)
    try:
        data_service = DataServiceFactory.create_data_service()
        service_type = type(data_service).__name__
        logger.info(f"Data service initialized: {service_type}")
        
    except Exception as e:
        logger.error(f"Failed to initialize data service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down bioforklift monitoring dashboard")


app = FastAPI(
    title="Bioforklift Monitoring Dashboard",
    description="Monitoring dashboard for bioforklift daily runs and workflow status",
    version="1.0.0",
    lifespan=lifespan
)

# Add session middleware (must be before CORS)
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production"),
    max_age=3600 * 24 * 7,  # 1 week
    same_site="lax",
    https_only=not is_development_mode()
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://127.0.0.1:5173",
        "http://localhost:3000", 
        "http://127.0.0.1:3000",
        "null"
    ],  # Svelte dev server + file://
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "bioforklift-monitoring"}


@app.get("/")
async def root():
    """Root endpoint - redirect to login or dashboard"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bioforklift Monitoring Dashboard</title>
        <style>
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                margin: 0; padding: 40px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh; display: flex; align-items: center; justify-content: center;
            }
            .container { 
                max-width: 500px; text-align: center; background: white; 
                padding: 40px; border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            }
            .logo { font-size: 3em; margin-bottom: 10px; }
            .title { color: #1a1a1a; margin-bottom: 10px; font-weight: 600; }
            .subtitle { color: #666; margin-bottom: 30px; }
            .btn { 
                display: inline-block; background: #1a73e8; color: white; padding: 16px 32px; 
                text-decoration: none; border-radius: 8px; font-weight: 500; font-size: 16px;
                transition: background 0.2s; margin: 10px;
            }
            .btn:hover { background: #1557b0; }
            .btn-secondary { background: #5f6368; }
            .btn-secondary:hover { background: #3c4043; }
            .features { 
                text-align: left; margin: 30px 0; padding: 20px; 
                background: #f8f9fa; border-radius: 8px;
            }
            .features ul { margin: 0; padding-left: 20px; }
            .features li { margin: 8px 0; color: #444; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">🧬</div>
            <h1 class="title">Bioforklift Monitoring Dashboard</h1>
            <p class="subtitle">Monitor your bioinformatics workflows and pipeline performance</p>
            
            <div class="features">
                <strong>Dashboard Features:</strong>
                <ul>
                    <li>Daily workflow run summaries</li>
                    <li>Real-time processing status</li>
                    <li>Configuration metrics and trends</li>
                    <li>Error tracking and debugging</li>
                    <li>System health monitoring</li>
                </ul>
            </div>
            
            <a href="/auth/login" class="btn">🔐 Sign in with Google</a>
            <a href="/auth/status" class="btn btn-secondary">📊 Check Status</a>
            
            <p style="margin-top: 30px; color: #666; font-size: 14px;">
                Secure access with Google Cloud Platform authentication
            </p>
        </div>
        
        <script>
            // Auto-redirect if already authenticated
            fetch('/auth/status')
                .then(response => response.json())
                .then(data => {
                    if (data.authenticated) {
                        window.location.href = '/dashboard';
                    }
                })
                .catch(() => {
                    // Continue showing login page
                });
        </script>
    </body>
    </html>
    """)

@app.get("/dashboard")
async def dashboard():
    """Dashboard page - serves the frontend or redirect to frontend URL"""
    frontend_url = os.environ.get('FRONTEND_URL')
    
    if frontend_url and frontend_url.startswith('http'):
        # Redirect to external frontend
        return RedirectResponse(url=frontend_url)
    else:
        # Serve a simple dashboard page
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Bioforklift Dashboard</title>
            <style>
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0; padding: 20px; background: #f5f5f5;
                }
                .header { 
                    display: flex; justify-content: space-between; align-items: center; 
                    background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .content { 
                    background: white; padding: 30px; border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .user-info { display: flex; align-items: center; gap: 15px; }
                .user-avatar { width: 40px; height: 40px; border-radius: 50%; }
                .btn { 
                    background: #1a73e8; color: white; padding: 8px 16px; 
                    text-decoration: none; border-radius: 4px; font-size: 14px;
                }
                .btn-danger { background: #d93025; }
                #dashboard-data { 
                    margin-top: 20px; padding: 20px; background: #f8f9fa; 
                    border-radius: 4px; font-family: monospace; white-space: pre-wrap;
                }
                .loading { text-align: center; padding: 40px; color: #666; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🧬 Bioforklift Dashboard</h1>
                <div class="user-info">
                    <span id="user-name">Loading...</span>
                    <a href="/auth/logout" class="btn btn-danger">Sign Out</a>
                </div>
            </div>
            
            <div class="content">
                <h2>Dashboard Metrics</h2>
                <p>Real-time monitoring of your bioforklift workflows</p>
                
                <div id="dashboard-data" class="loading">Loading dashboard data...</div>
                
                <div style="margin-top: 30px;">
                    <a href="/api/v1/metrics/dashboard" class="btn" target="_blank">📊 View API Data</a>
                    <a href="/docs" class="btn" target="_blank">📚 API Documentation</a>
                </div>
            </div>
            
            <script>
                // Load user info
                fetch('/auth/user')
                    .then(response => {
                        if (!response.ok) {
                            window.location.href = '/auth/login';
                            return;
                        }
                        return response.json();
                    })
                    .then(user => {
                        document.getElementById('user-name').textContent = user.name || user.email;
                    })
                    .catch(() => {
                        window.location.href = '/auth/login';
                    });
                
                // Load dashboard data
                fetch('/api/v1/metrics/dashboard')
                    .then(response => {
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }
                        return response.json();
                    })
                    .then(data => {
                        document.getElementById('dashboard-data').innerHTML = 
                            JSON.stringify(data, null, 2);
                    })
                    .catch(error => {
                        document.getElementById('dashboard-data').innerHTML = 
                            'Error loading dashboard data: ' + error.message + 
                            '\\n\\nPlease check your GCP permissions and try refreshing the page.';
                    });
            </script>
        </body>
        </html>
        """)


# Include routers
app.include_router(auth_router, prefix="/auth", tags=["authentication"])
app.include_router(metrics_router, prefix="/api/v1/metrics", tags=["metrics"])


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error"}
    )


def get_data_service() -> Union[BigQueryService, MockDataService]:
    """Get the global data service instance"""
    if data_service is None:
        raise HTTPException(status_code=500, detail="Data service not initialized")
    return data_service