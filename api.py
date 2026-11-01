"""
Root entrypoint for running the AQI India FastAPI Gateway.

Usage:
    uvicorn api:app --reload --port 8000
"""

from aqi_pipeline.api import app, create_app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
