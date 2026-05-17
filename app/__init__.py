import os
from flask import Flask


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

    return app
