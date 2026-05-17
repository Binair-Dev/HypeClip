from flask import Blueprint, render_template, request, jsonify, send_file
from app.services.shorts_service import ShortsService
import os

shorts_bp = Blueprint('shorts', __name__)


@shorts_bp.route('/generate', methods=['GET'])
def generate_page():
    """Serve the generate.html page. Clip data is loaded from sessionStorage via JS."""
    return render_template('generate.html')


@shorts_bp.route('/api/generate', methods=['POST'])
def generate():
    """Create a shorts generation job. Returns {session_id}."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON body provided'}), 400

    clips = data.get('clips', [])
    options = data.get('options', {})

    if not clips:
        return jsonify({'error': 'No clips provided'}), 400

    service = ShortsService()
    session_id = service.generate_shorts(clips, options)
    return jsonify({'session_id': session_id})


@shorts_bp.route('/api/progress/<session_id>')
def progress(session_id):
    """Return progress JSON for a generation session."""
    service = ShortsService()
    status = service.get_progress(session_id)
    return jsonify(status)


@shorts_bp.route('/result/<session_id>')
def result(session_id):
    """Serve the result page for a generation session."""
    return render_template('result.html', shorts=[], session_id=session_id)


@shorts_bp.route('/api/results/<session_id>')
def api_results(session_id):
    """Return generated shorts as JSON."""
    service = ShortsService()
    shorts = service.get_results(session_id)
    return jsonify(shorts)


@shorts_bp.route('/download/<session_id>/<filename>')
def download(session_id, filename):
    """Download a generated file."""
    output_dir = os.path.join('output', session_id)
    filepath = os.path.join(output_dir, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404
