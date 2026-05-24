from functools import wraps

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app.models import db, User

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin():
            return jsonify({'error': 'Accès refusé'}), 403
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/')
@admin_required
def index():
    users = User.query.order_by(User.created_at).all()
    return render_template('admin.html', users=users, current_user=current_user)


@admin_bp.route('/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    role = data.get('role', 'member')

    if not username or not password:
        return jsonify({'error': 'Nom et mot de passe requis'}), 400
    if role not in ('admin', 'member'):
        return jsonify({'error': 'Rôle invalide'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Nom d\'utilisateur déjà pris'}), 400

    user = User(username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    data = request.get_json() or {}

    if 'username' in data:
        new_name = (data['username'] or '').strip()
        if new_name and new_name != user.username:
            if User.query.filter_by(username=new_name).first():
                return jsonify({'error': 'Nom d\'utilisateur déjà pris'}), 400
            user.username = new_name

    if data.get('password'):
        if len(data['password']) < 6:
            return jsonify({'error': 'Mot de passe trop court (min 6 caractères)'}), 400
        user.set_password(data['password'])

    if 'role' in data:
        if data['role'] not in ('admin', 'member'):
            return jsonify({'error': 'Rôle invalide'}), 400
        # Prevent removing the last admin
        if user.role == 'admin' and data['role'] != 'admin':
            admin_count = User.query.filter_by(role='admin').count()
            if admin_count <= 1:
                return jsonify({'error': 'Impossible de retirer le dernier administrateur'}), 400
        user.role = data['role']

    db.session.commit()
    return jsonify(user.to_dict())


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({'error': 'Impossible de se supprimer soi-même'}), 400
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    db.session.delete(user)
    db.session.commit()
    return jsonify({'ok': True})
