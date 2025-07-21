"""
OAuth authentication module for Google Cloud Platform integration
"""
from fastapi import HTTPException, Request, Depends
from authlib.integrations.starlette_client import OAuth
from google.cloud import bigquery, resourcemanager_v3
from google.oauth2 import credentials
import os
import logging
import httpx
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# OAuth configuration
oauth = OAuth()

def configure_oauth():
    """Configure OAuth with Google"""
    logger.info("Configuring OAuth with Google")
    logger.info("GOOGLE_CLIENT_ID: %s", os.environ.get('GOOGLE_CLIENT_ID'))
    logger.info("GOOGLE_CLIENT_SECRET: %s", os.environ.get('GOOGLE_CLIENT_SECRET'))
    oauth.register(
        name='google',
        client_id=os.environ.get('GOOGLE_CLIENT_ID'),
        client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile https://www.googleapis.com/auth/cloud-platform.read-only'
        }
    )
    return oauth

async def validate_bearer_token(access_token: str) -> Optional[Dict[str, Any]]:
    """
    Validate Google OAuth access token and return user info
    
    Args:
        access_token: The OAuth access token from Authorization header
        
    Returns:
        Dict containing user information if valid, None if invalid
    """
    try:
        async with httpx.AsyncClient() as client:
            # Validate token with Google's tokeninfo endpoint
            response = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?access_token={access_token}"
            )
            
            if response.status_code != 200:
                logger.warning(f"Token validation failed with status {response.status_code}")
                return None
            
            token_info = response.json()
            
            # Check if token has required scope
            scope = token_info.get('scope', '')
            required_scopes = ['openid', 'email', 'profile', 'https://www.googleapis.com/auth/cloud-platform.read-only']
            
            if not all(req_scope in scope for req_scope in required_scopes[:3]):  # At minimum need openid, email, profile
                logger.warning(f"Token missing required scopes. Has: {scope}")
                return None
            
            # Get user info from Google's userinfo endpoint
            userinfo_response = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if userinfo_response.status_code != 200:
                logger.warning(f"Failed to get user info: {userinfo_response.status_code}")
                return None
            
            user_info = userinfo_response.json()
            
            return {
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'picture': user_info.get('picture'),
                'access_token': access_token
            }
            
    except Exception as e:
        logger.error(f"Bearer token validation error: {e}")
        return None

def extract_bearer_token(request: Request) -> Optional[str]:
    """
    Extract Bearer token from Authorization header
    
    Args:
        request: FastAPI request object
        
    Returns:
        Access token string if found, None otherwise
    """
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header[7:]  # Remove 'Bearer ' prefix
    return None

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
    Dependency to get current authenticated user from session or Bearer token
    
    Args:
        request: FastAPI request object
        
    Returns:
        Dict containing user information
        
    Raises:
        HTTPException: If user is not authenticated
    """
    # First, try Bearer token authentication
    bearer_token = extract_bearer_token(request)
    if bearer_token:
        user_info = await validate_bearer_token(bearer_token)
        if user_info:
            # Validate GCP access for Bearer token users
            email = user_info.get('email')
            access_token = user_info.get('access_token')
            
            if email and access_token:
                try:
                    target_project_id, dataset_id = get_target_project_config()
                    has_access = await validate_gcp_access(access_token, email, target_project_id, dataset_id)
                    
                    if has_access:
                        return user_info
                    else:
                        raise HTTPException(
                            status_code=403,
                            detail=f"Access denied. User {email} does not have access to GCP project {target_project_id}."
                        )
                except ValueError as e:
                    # Missing environment variables - allow in development mode
                    if is_development_mode():
                        logger.warning(f"GCP validation skipped in development mode: {e}")
                        return user_info
                    else:
                        raise HTTPException(status_code=500, detail=str(e))
        
        # Bearer token was provided but invalid
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Fallback to session-based authentication
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