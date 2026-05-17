from flask import Blueprint, render_template, request, jsonify
from app.services import twitch_service as twitch_svc

main_bp = Blueprint('main', __name__)


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
