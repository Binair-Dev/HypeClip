import os
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from app.services import twitch_service as twitch_svc

main_bp = Blueprint('main', __name__)


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = False
    if request.method == 'POST':
        password = request.form.get('password', '')
        expected = os.environ.get('APP_PASSWORD', 'BETATEST')
        if password == expected:
            session['authenticated'] = True
            return redirect(request.args.get('next') or url_for('main.index'))
        error = True
    return render_template('login.html', error=error)


@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.login'))


@main_bp.route('/')
def index():
    return render_template('index.html')


@main_bp.route('/search')
def search_streamer():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Query required'}), 400
    results = twitch_svc.search_streamer(query)
    return jsonify(results)


@main_bp.route('/clips/<streamer_login>')
def get_clips(streamer_login):
    clips = twitch_svc.get_trending_clips(streamer_login)
    return render_template('clips.html', clips=clips, streamer_login=streamer_login)


@main_bp.route('/api/clips/<streamer_login>')
def api_clips(streamer_login):
    clips = twitch_svc.get_trending_clips(streamer_login)
    return jsonify(clips)
