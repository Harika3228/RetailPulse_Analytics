# Support running as package or as a script. Try relative import first.
try:
    from ..main import app  # when executed as package (backend.app.main)
except Exception:
    try:
        from backend.main import app  # when backend is on sys.path
    except Exception:
        from main import app  # fallback when running from backend/ directory
