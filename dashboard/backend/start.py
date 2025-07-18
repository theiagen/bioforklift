#!/usr/bin/env python3
"""
Startup script for bioforklift monitoring dashboard backend
"""

import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    # Get configuration from environment variables
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    
    # Start the server
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=True  # For development
    )