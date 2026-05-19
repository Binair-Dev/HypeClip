import os
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from app.services import twitch_service as twitch_svc

main_bp = Blueprint('main', __name__)

# Category definitions: (sort, period)
CATEGORIES = {
    'trending':    {'sort': 'TRENDING',   'period': 'LAST_DAY',   'label': 'Trending',    'icon': 'fa-fire'},
    'most_viewed': {'sort': 'VIEWS_DESC', 'period': 'ALL_TIME',   'label': 'Most Viewed', 'icon': 'fa-eye'},
    'recent':      {'sort': 'VIEWS_DESC', 'period': 'LAST_WEEK',  'label': 'Recent',      'icon': 'fa-clock'},
}


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
    # Default: load trending clips server-side
    clips = twitch_svc.get_trending_clips(
        streamer_login,
        sort=CATEGORIES['trending']['sort'],
        period=CATEGORIES['trending']['period'],
    )
    return render_template(
        'clips.html',
        clips=clips,
        streamer_login=streamer_login,
        categories=CATEGORIES,
        active_category='trending',
    )


@main_bp.route('/api/clips/<streamer_login>/<category>')
def api_clips_category(streamer_login, category):
    cat = CATEGORIES.get(category)
    if not cat:
        return jsonify({'error': f'Unknown category: {category}'}), 400

    clips = twitch_svc.get_trending_clips(
        streamer_login,
        sort=cat['sort'],
        period=cat['period'],
    )
    return jsonify(clips)
