import json
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from app.models import db, Preset, PresetStreamer
from app.services import twitch_service as twitch_svc

presets_bp = Blueprint('presets', __name__, url_prefix='/api/presets')


@presets_bp.route('/', methods=['GET'])
@login_required
def list_presets():
    presets = (Preset.query
               .filter_by(user_id=current_user.id)
               .order_by(Preset.updated_at.desc())
               .all())
    return jsonify([p.to_dict() for p in presets])


@presets_bp.route('/', methods=['POST'])
@login_required
def create_preset():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    streamers = data.get('streamers') or []

    if not name:
        return jsonify({'error': 'Nom requis'}), 400

    name_pos = data.get('name_position')
    preset = Preset(
        user_id=current_user.id,
        name=name,
        name_position=json.dumps(name_pos) if name_pos else None,
        game_name=(data.get('game_name') or '').strip() or None,
        clip_count=int(data['clip_count']) if data.get('clip_count') else None,
    )
    db.session.add(preset)
    db.session.flush()

    for i, s in enumerate(streamers):
        ps = PresetStreamer(
            preset_id=preset.id,
            streamer_login=(s.get('streamer_login') or '').strip(),
            webcam_region=json.dumps(s['webcam_region']) if s.get('webcam_region') else None,
            webcam_position=json.dumps(s['webcam_position']) if s.get('webcam_position') else None,
            sort_order=i,
        )
        db.session.add(ps)

    db.session.commit()
    return jsonify(preset.to_dict()), 201


@presets_bp.route('/<int:preset_id>', methods=['PUT'])
@login_required
def update_preset(preset_id):
    preset = Preset.query.filter_by(id=preset_id, user_id=current_user.id).first()
    if not preset:
        return jsonify({'error': 'Preset introuvable'}), 404

    data = request.get_json() or {}

    if 'name' in data:
        preset.name = (data['name'] or preset.name).strip()

    if 'name_position' in data:
        preset.name_position = json.dumps(data['name_position']) if data['name_position'] else None

    if 'game_name' in data:
        preset.game_name = (data['game_name'] or '').strip() or None

    if 'clip_count' in data:
        preset.clip_count = int(data['clip_count']) if data.get('clip_count') else None

    if 'streamers' in data:
        PresetStreamer.query.filter_by(preset_id=preset.id).delete()
        for i, s in enumerate(data['streamers']):
            ps = PresetStreamer(
                preset_id=preset.id,
                streamer_login=(s.get('streamer_login') or '').strip(),
                webcam_region=json.dumps(s['webcam_region']) if s.get('webcam_region') else None,
                webcam_position=json.dumps(s['webcam_position']) if s.get('webcam_position') else None,
                sort_order=i,
            )
            db.session.add(ps)

    preset.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(preset.to_dict())


@presets_bp.route('/<int:preset_id>', methods=['DELETE'])
@login_required
def delete_preset(preset_id):
    preset = Preset.query.filter_by(id=preset_id, user_id=current_user.id).first()
    if not preset:
        return jsonify({'error': 'Preset introuvable'}), 404
    db.session.delete(preset)
    db.session.commit()
    return jsonify({'ok': True})


@presets_bp.route('/<int:preset_id>/clips', methods=['GET'])
@login_required
def get_preset_clips(preset_id):
    preset = Preset.query.filter_by(id=preset_id, user_id=current_user.id).first()
    if not preset:
        return jsonify({'error': 'Preset introuvable'}), 404

    if not preset.game_name:
        return jsonify({'error': 'Ce preset n\'a pas de jeu configuré'}), 400

    logins = [s.streamer_login for s in preset.streamers]
    if not logins:
        return jsonify({'error': 'Aucun streamer dans ce preset'}), 400

    count = preset.clip_count or 5
    clips = twitch_svc.get_clips_for_streamers_game(logins, preset.game_name, count)

    if not clips:
        return jsonify({
            'error': f'Aucun clip "{preset.game_name}" trouvé dans les dernières 24h parmi ces streamers'
        }), 404

    return jsonify({'clips': clips, 'count': len(clips)})
