import os
from flask import Flask
from flask_login import LoginManager
from app.models import db, User


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # SQLite stored next to the project root
    db_path = os.path.join(os.path.dirname(app.root_path), 'hypeclip.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Ensure output folder exists
    output_dir = os.path.join(app.root_path, '..', 'output')
    os.makedirs(output_dir, exist_ok=True)

    # Init SQLAlchemy
    db.init_app(app)

    # Init Flask-Login (no automatic redirect — app works without login)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = None  # don't auto-redirect; routes decide

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.shorts import shorts_bp
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.presets import presets_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(shorts_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(presets_bp)

    # Create tables, migrate schema, seed default admin
    with app.app_context():
        db.create_all()
        _migrate_schema()
        _seed_admin()

    return app


def _migrate_schema():
    """Add columns introduced after initial schema creation."""
    from sqlalchemy import text
    # presets.name_position (added in v2)
    try:
        db.session.execute(text("SELECT name_position FROM presets LIMIT 1"))
    except Exception:
        db.session.execute(text("ALTER TABLE presets ADD COLUMN name_position TEXT"))
        db.session.commit()


def _seed_admin():
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
