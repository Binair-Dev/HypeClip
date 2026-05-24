from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from flask_login import login_user, logout_user, current_user

from app.models import db, User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            if request.is_json:
                return jsonify({'ok': True, 'username': user.username, 'role': user.role})
            return redirect(request.args.get('next') or url_for('main.index'))

        if request.is_json:
            return jsonify({'error': 'Identifiants incorrects'}), 401
        return render_template('login.html', error='Identifiants incorrects')

    return render_template('login.html')


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'error': 'Nom d\'utilisateur et mot de passe requis'}), 400
    if len(username) < 3 or len(username) > 50:
        return jsonify({'error': 'Le nom doit faire entre 3 et 50 caractères'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Le mot de passe doit faire au moins 6 caractères'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Ce nom d\'utilisateur est déjà pris'}), 400

    user = User(username=username, role='member')
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    login_user(user, remember=True)
    return jsonify({'ok': True, 'username': user.username, 'role': user.role})


@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))
