from flask import Blueprint, render_template, request, jsonify
from app.services import twitch_service as twitch_svc

main_bp = Blueprint('main', __name__)

CATEGORIES = {
    'trending':    {'sort': 'TRENDING',   'period': 'LAST_DAY',  'label': 'Trending',    'icon': 'fa-fire'},
    'most_viewed': {'sort': 'VIEWS_DESC', 'period': 'ALL_TIME',  'label': 'Most Viewed', 'icon': 'fa-eye'},
    'recent':      {'sort': 'VIEWS_DESC', 'period': 'LAST_WEEK', 'label': 'Recent',      'icon': 'fa-clock'},
}


@main_bp.route('/')
def index():
    return render_template('index.html')


@main_bp.route('/search')
def search_streamer():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Query required'}), 400
    return jsonify(twitch_svc.search_streamer(query))


@main_bp.route('/clips/<streamer_login>')
def get_clips(streamer_login):
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
        streamer_login, sort=cat['sort'], period=cat['period'],
    )
    return jsonify(clips)
