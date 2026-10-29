import os
from flask import Flask, jsonify, render_template
from config import Config
from database import init_db
from routes.views import views_bp
from routes.api import api_bp

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Register blueprints
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)

    # Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("base.html", error_title="404 - Page Not Found",
                               error_msg="The requested page could not be located."), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template("base.html", error_title="500 - Internal Server Error",
                               error_msg="An unexpected error occurred on the server."), 500

    # Ensure DB is initialized
    with app.app_context():
        if not os.path.exists(Config.DATABASE_PATH):
            print("Database not found on startup. Initializing and seeding...")
            from seed_all import populate_database_and_models
            populate_database_and_models()

    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Hostel Energy AI on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
