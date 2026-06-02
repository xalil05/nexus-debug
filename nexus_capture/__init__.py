"""
nexus-capture — Auto-capture d'erreurs pour Nexus-Debug v3.0

Intercepte automatiquement les exceptions dans Flask, FastAPI et scripts Python,
extrait le contexte (route, headers, stack trace, version, breadcrumbs) et
les POSTe sur l'API Nexus-Debug.

Usage:
    # Flask
    from nexus_capture.flask_middleware import NexusCaptureFlask
    app = Flask(__name__)
    NexusCaptureFlask(app, nexus_url="http://100.70.168.107:9001", api_key="...")

    # FastAPI
    from nexus_capture.fastapi_middleware import NexusCaptureFastAPI
    app = FastAPI()
    NexusCaptureFastAPI(app, nexus_url="http://100.70.168.107:9001", api_key="...")

    # Script
    from nexus_capture.capture import capture_exception
    try:
        risky_operation()
    except Exception as e:
        capture_exception(e, project="mon-projet", version="1.0.0")
"""
__version__ = "0.1.0"
