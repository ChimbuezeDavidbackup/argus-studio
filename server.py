"""
Argus Studio - Web & Mobile Backend Server Entrypoint.
Enables accessing Argus Studio from browsers, mobile phones, and tablets on the local network.
"""

import sys
import uvicorn
from core.config import load_config

if __name__ == "__main__":
    cfg = load_config()
    host = cfg.get("web_host", "0.0.0.0")
    port = int(cfg.get("web_port", 8000))
    
    print("=" * 60)
    print("  Argus Studio - Universal Web & Mobile Server")
    print(f"  Local Access:      http://localhost:{port}")
    print(f"  Network / Mobile:  http://<your-device-ip>:{port}")
    print("=" * 60)
    
    uvicorn.run("server.api:app", host=host, port=port, reload=False)
