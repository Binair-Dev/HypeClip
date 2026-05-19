import os
from flask import Flask, session, redirect, url_for, request


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Ensure output folder exists
    output_dir = os.path.join(app.root_path, '..', 'output')
    os.makedirs(output_dir, exist_ok=True)

    from app.routes.main import main_bp
    from app.routes.shorts import shorts_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(shorts_bp)

    # Routes that don't require authentication
    _PUBLIC = {'/login'}

    @app.before_request
    def require_auth():
        # Allow static files and the login route through
        if request.endpoint == 'static' or request.path in _PUBLIC:
            return
        if not session.get('authenticated'):
            return redirect(url_for('main.login', next=request.path))

    return app
