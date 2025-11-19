from flask import Flask, url_for
from flask_minify import Minify
from flask_compress import Compress
from flask_talisman import Talisman
from flask_wtf import CSRFProtect
from supabase import create_client, Client
from datetime import timedelta
import os

# --- Configuration ---
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError(
        "The environment variables SUPABASE_URL and SUPABASE_KEY are required."
    )

SIGNED_URL_EXPIRATION_SECONDS = 3600 * 12  # 1 hour (adjust as needed)
supabase: Client = create_client(url, key)
STORAGE_BUCKET_NAME = "tree_files"

demo_id = os.environ.get("DEMO_TREE_ID")
support_email = os.environ.get("SUPPORT_EMAIL")

csrf = CSRFProtect()


def create_app():
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config["SECRET_KEY"] = os.environ.get(
        "FLASK_SECRET_KEY", "a-super-private-key-for-dev"
    )
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

    # Initialize the extensions
    is_vercel = os.environ.get("VERCEL") == "1"
    if not is_vercel:
        # Flask-Compress is not compatible with Vercel's serverless environment
        Compress(app=app)
    Minify(app=app, html=True, js=True, cssless=True)

    csp = {
        "default-src": [
            "'self'",
            "*.googleapis.com",
            "*.gstatic.com",
            "cdn.jsdelivr.net",
            "unpkg.com",
        ],
        "script-src": [
            "'self'",
            "'wasm-unsafe-eval'",
            "'unsafe-inline'",
            "*.googleapis.com",
            "unpkg.com",
            "cdn.jsdelivr.net",
        ],
        "style-src": [
            "'self'",
            "'unsafe-inline'",
            "*.googleapis.com",
            "cdn.jsdelivr.net",
            "unpkg.com",
        ],
        "font-src": ["'self'", "*.gstatic.com"],
        "img-src": [
            "'self'",
            "data:",
            "*",
        ],  # Allow images from any source, including data URIs
        "connect-src": ["'self'", "nominatim.openstreetmap.org"],
        "manifest-src": ["'self'"],
        "worker-src": ["'self'"],  # For Web Workers, potentially including WASM
    }
    Talisman(
        app=app,
        content_security_policy=csp,
    )

    csrf.init_app(app)
    app.config["WTF_CSRF_METHODS"] = ["POST", "PUT", "PATCH", "DELETE", "GET"]
    app.config["WTF_CSRF_ENABLED"] = False

    # Register the Blueprints
    from . import auth, pages, api_data, api_files, api_sharing, api_trees

    app.register_blueprint(auth.bp)
    app.register_blueprint(pages.bp)
    app.register_blueprint(api_data.bp)
    app.register_blueprint(api_files.bp)
    app.register_blueprint(api_sharing.bp)
    app.register_blueprint(api_trees.bp)

    return app
