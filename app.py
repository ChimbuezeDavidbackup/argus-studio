"""
Argus Studio - Universal Application Launcher
Defaults to the native desktop GUI, or launches the cross-platform Web/Mobile server with --server or --web.
"""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("--server", "--web", "-s", "-w"):
        import uvicorn
        from core.config import load_config
        cfg = load_config()
        host = cfg.get("web_host", "0.0.0.0")
        port = int(cfg.get("web_port", 8000))
        print("=" * 60)
        print("  Starting Argus Studio Web & Mobile Server...")
        print(f"  Access locally:   http://localhost:{port}")
        print(f"  Access on LAN:    http://<device-ip>:{port}")
        print("=" * 60)
        uvicorn.run("server.api:app", host=host, port=port, reload=False)
    else:
        from desktop.app import main
        main()
