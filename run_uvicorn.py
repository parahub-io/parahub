#!/usr/bin/env python3
"""
Run Parahub with Uvicorn ASGI server
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "parahub.asgi:application",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        access_log=True,
        use_colors=True,
        # WebSocket support
        ws_ping_interval=20,
        ws_ping_timeout=20,
        # Performance settings
        workers=1,  # Use 1 worker for development, increase for production
        loop="uvloop",  # High-performance event loop
        lifespan="on",
    )