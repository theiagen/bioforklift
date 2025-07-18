"""
Authentication API routes for OAuth with Google Cloud Platform
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from auth.oauth import (
    configure_oauth, 
    validate_gcp_access, 
    get_current_user,
    get_target_project_config,
    is_development_mode
)
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize OAuth
oauth = configure_oauth()

@router.get("/login")
async def login(request: Request):
    """Initiate OAuth login with Google"""
    try:
        redirect_uri = request.url_for('auth_callback')
        return await oauth.google.authorize_redirect(request, redirect_uri)
    except Exception as e:
        logger.error(f"OAuth login error: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate login")

@router.get("/callback")
async def auth_callback(request: Request):
    """Handle OAuth callback from Google"""
    try:
        # Get access token from OAuth
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        
        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")
        
        email = user_info.get('email')
        access_token = token.get('access_token')
        
        if not email or not access_token:
            raise HTTPException(status_code=400, detail="Incomplete user information received")
        
        # Get target project configuration
        target_project_id, dataset_id = get_target_project_config()
        
        # Validate GCP project access
        has_access = await validate_gcp_access(access_token, email, target_project_id, dataset_id)
        
        if not has_access:
            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Access Denied - Bioforklift Dashboard</title>
                <style>
                    body {{ 
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        margin: 0; padding: 40px; background: #f5f5f5; text-align: center;
                    }}
                    .container {{ 
                        max-width: 600px; margin: 0 auto; background: white; 
                        padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }}
                    .error {{ color: #d93025; }}
                    .code {{ background: #f8f9fa; padding: 4px 8px; border-radius: 4px; font-family: monospace; }}
                    .btn {{ 
                        display: inline-block; background: #1a73e8; color: white; padding: 12px 24px; 
                        text-decoration: none; border-radius: 6px; margin-top: 20px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1 class="error">🚫 Access Denied</h1>
                    <p>Sorry <strong>{email}</strong>, you don't have access to the BigQuery project:</p>
                    <p class="code">{target_project_id}</p>
                    <p>To access this dashboard, you need one of the following permissions:</p>
                    <ul style="text-align: left; max-width: 400px; margin: 20px auto;">
                        <li>BigQuery Data Viewer on dataset <code>{dataset_id}</code></li>
                        <li>BigQuery User on project <code>{target_project_id}</code></li>
                        <li>Project Viewer on project <code>{target_project_id}</code></li>
                    </ul>
                    <p>Please contact your GCP administrator to request access.</p>
                    <a href="/auth/login" class="btn">← Try Different Account</a>
                </div>
            </body>
            </html>
            """, status_code=403)
        
        # Store user info in session
        request.session['user'] = {
            'email': email,
            'name': user_info.get('name', email),
            'picture': user_info.get('picture', ''),
            'access_token': access_token,
            'authenticated_at': token.get('expires_at', 0)
        }
        
        # Redirect to dashboard
        frontend_url = os.environ.get('FRONTEND_URL', '/')
        if frontend_url and frontend_url != '/':
            return RedirectResponse(url=frontend_url)
        else:
            return RedirectResponse(url='/dashboard')
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Error - Bioforklift Dashboard</title>
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0; padding: 40px; background: #f5f5f5; text-align: center;
                }}
                .container {{ 
                    max-width: 600px; margin: 0 auto; background: white; 
                    padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .error {{ color: #d93025; }}
                .btn {{ 
                    display: inline-block; background: #1a73e8; color: white; padding: 12px 24px; 
                    text-decoration: none; border-radius: 6px; margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="error">⚠️ Authentication Error</h1>
                <p>Something went wrong during authentication.</p>
                <p>Please try signing in again.</p>
                <a href="/auth/login" class="btn">← Try Again</a>
            </div>
        </body>
        </html>
        """, status_code=400)

@router.get("/logout")
async def logout(request: Request):
    """Logout user and clear session"""
    request.session.clear()
    
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Signed Out - Bioforklift Dashboard</title>
        <style>
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                margin: 0; padding: 40px; background: #f5f5f5; text-align: center;
            }
            .container { 
                max-width: 600px; margin: 0 auto; background: white; 
                padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .btn { 
                display: inline-block; background: #1a73e8; color: white; padding: 12px 24px; 
                text-decoration: none; border-radius: 6px; margin-top: 20px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>👋 Signed Out</h1>
            <p>You have been successfully signed out of the Bioforklift Dashboard.</p>
            <a href="/auth/login" class="btn">Sign In Again</a>
        </div>
    </body>
    </html>
    """)

@router.get("/user")
async def get_user_info(user = Depends(get_current_user)):
    """Get current authenticated user information"""
    return {
        "email": user.get('email'),
        "name": user.get('name'),
        "picture": user.get('picture'),
        "authenticated": True
    }

@router.get("/status")
async def get_auth_status(request: Request):
    """Check authentication status without requiring authentication"""
    user = request.session.get('user')
    
    if user:
        target_project_id, dataset_id = get_target_project_config()
        return {
            "authenticated": True,
            "user": {
                "email": user.get('email'),
                "name": user.get('name'),
                "picture": user.get('picture')
            },
            "project": {
                "project_id": target_project_id,
                "dataset_id": dataset_id
            }
        }
    else:
        return {
            "authenticated": False,
            "login_url": "/auth/login"
        }