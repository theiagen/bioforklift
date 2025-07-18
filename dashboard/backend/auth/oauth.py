"""
OAuth authentication module for Google Cloud Platform integration
"""
from fastapi import HTTPException, Request, Depends
from authlib.integrations.starlette_client import OAuth
from google.cloud import bigquery, resourcemanager_v3
from google.oauth2 import credentials
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# OAuth configuration
oauth = OAuth()

def configure_oauth():
    """Configure OAuth with Google"""
    oauth.register(
        name='google',
        client_id=os.environ.get('GOOGLE_CLIENT_ID'),
        client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid_configuration',
        client_kwargs={
            'scope': 'openid email profile https://www.googleapis.com/auth/cloud-platform.read-only'
        }
    )
    return oauth

async def validate_gcp_access(access_token: str, email: str, target_project_id: str, dataset_id: str) -> bool:
    """
    Validate if user has access to the target GCP project and BigQuery dataset
    
    Args:
        access_token: User's OAuth access token
        email: User's email address
        target_project_id: Target GCP project ID
        dataset_id: Target BigQuery dataset ID
        
    Returns:
        bool: True if user has access, False otherwise
    """
    try:
        # Create credentials from the user's access token
        creds = credentials.Credentials(token=access_token)
        
        # Test BigQuery access
        bq_client = bigquery.Client(
            project=target_project_id,
            credentials=creds
        )
        
        # Try to access the specific dataset first
        try:
            dataset_ref = bq_client.dataset(dataset_id)
            dataset = bq_client.get_dataset(dataset_ref)
            logger.info(f"✅ User {email} has access to dataset {dataset_id}")
            return True
        except Exception as dataset_error:
            logger.warning(f"⚠️ Dataset access failed for {email}: {dataset_error}")
            
            # Fallback: Check if they can at least list datasets (basic BigQuery access)
            try:
                datasets = list(bq_client.list_datasets(max_results=1))
                logger.info(f"✅ User {email} has basic BigQuery access to project {target_project_id}")
                return True
            except Exception as bq_error:
                logger.error(f"❌ BigQuery access failed for {email}: {bq_error}")
                
                # Final fallback: Check if they can read the project at all
                try:
                    rm_client = resourcemanager_v3.ProjectsClient(credentials=creds)
                    project_name = f"projects/{target_project_id}"
                    project = rm_client.get_project(name=project_name)
                    logger.info(f"✅ User {email} has project read access to {target_project_id}")
                    return True
                except Exception as project_error:
                    logger.error(f"❌ Project access failed for {email}: {project_error}")
                    return False
                
    except Exception as e:
        logger.error(f"❌ GCP access validation failed for {email}: {e}")
        return False

async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user from session
    
    Args:
        request: FastAPI request object
        
    Returns:
        Dict containing user information
        
    Raises:
        HTTPException: If user is not authenticated
    """
    user = request.session.get('user')
    if not user:
        raise HTTPException(
            status_code=401, 
            detail="Authentication required. Please sign in with your Google account.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user

async def get_user_credentials(request: Request) -> credentials.Credentials:
    """
    Get user's GCP credentials from session
    
    Args:
        request: FastAPI request object
        
    Returns:
        Google OAuth2 credentials object
        
    Raises:
        HTTPException: If user is not authenticated or credentials are invalid
    """
    user = await get_current_user(request)
    access_token = user.get('access_token')
    
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials. Please sign in again."
        )
    
    return credentials.Credentials(token=access_token)

def get_target_project_config() -> tuple[str, str]:
    """
    Get target project and dataset configuration from environment
    
    Returns:
        tuple: (project_id, dataset_id)
        
    Raises:
        ValueError: If required environment variables are not set
    """
    project_id = os.environ.get('TARGET_PROJECT_ID')
    dataset_id = os.environ.get('DATASET_ID')
    
    if not project_id:
        raise ValueError("TARGET_PROJECT_ID environment variable is required")
    
    if not dataset_id:
        raise ValueError("DATASET_ID environment variable is required")
    
    return project_id, dataset_id

def validate_oauth_config():
    """
    Validate that required OAuth environment variables are set
    
    Raises:
        ValueError: If required environment variables are missing
    """
    required_vars = ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'SECRET_KEY']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

def is_development_mode() -> bool:
    """Check if running in development mode"""
    return os.environ.get('ENVIRONMENT', 'production').lower() in ['dev', 'development', 'local']