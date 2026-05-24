import os
from flask import Flask
from flask_login import LoginManager
from app.models import db, User


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # SQLite stored in the output folder (persisted Docker volume)
    output_dir_early = os.path.join(app.root_path, '..', 'output')
    os.makedirs(output_dir_early, exist_ok=True)
    db_path = os.path.join(output_dir_early, 'hypeclip.db')
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

    @app.errorhandler(401)
    def unauthorized_handler(e):
        from flask import jsonify
        return jsonify({'error': 'Non authentifié. Veuillez vous connecter.'}), 401

    # Create tables, migrate schema, seed default admin
    with app.app_context():
        db.create_all()
        _migrate_schema()
        _seed_admin()

    return app


def _migrate_schema():
    """Add columns introduced after initial schema creation."""
    from sqlalchemy import text

    _add_column(text("SELECT name_position FROM presets LIMIT 1"),
                text("ALTER TABLE presets ADD COLUMN name_position TEXT"))
    _add_column(text("SELECT game_name FROM presets LIMIT 1"),
                text("ALTER TABLE presets ADD COLUMN game_name TEXT"))
    _add_column(text("SELECT clip_count FROM presets LIMIT 1"),
                text("ALTER TABLE presets ADD COLUMN clip_count INTEGER"))


def _add_column(check_sql, alter_sql):
    try:
        db.session.execute(check_sql)
    except Exception:
        db.session.execute(alter_sql)
        db.session.commit()


def _seed_admin():
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
