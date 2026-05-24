from datetime import datetime
import json

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role       = db.Column(db.String(20), default='member', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    presets = db.relationship('Preset', backref='user', lazy=True,
                              cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def to_dict(self):
        return {
            'id':         self.id,
            'username':   self.username,
            'role':       self.role,
            'created_at': self.created_at.isoformat(),
        }


class Preset(db.Model):
    __tablename__ = 'presets'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name       = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    name_position  = db.Column(db.Text, nullable=True)   # JSON {x_pct,y_pct,height_pct}

    streamers = db.relationship(
        'PresetStreamer', backref='preset', lazy=True,
        cascade='all, delete-orphan',
        order_by='PresetStreamer.sort_order',
    )

    def to_dict(self):
        return {
            'id':            self.id,
            'name':          self.name,
            'created_at':    self.created_at.isoformat(),
            'updated_at':    self.updated_at.isoformat(),
            'name_position': json.loads(self.name_position) if self.name_position else None,
            'streamers':     [s.to_dict() for s in self.streamers],
        }


class PresetStreamer(db.Model):
    __tablename__ = 'preset_streamers'

    id               = db.Column(db.Integer, primary_key=True)
    preset_id        = db.Column(db.Integer, db.ForeignKey('presets.id'), nullable=False)
    streamer_login   = db.Column(db.String(100), nullable=False)
    webcam_region    = db.Column(db.Text, nullable=True)   # JSON {x,y,w,h}
    webcam_position  = db.Column(db.Text, nullable=True)   # JSON {x_pct,y_pct,height_pct}
    sort_order       = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'streamer_login':  self.streamer_login,
            'webcam_region':   json.loads(self.webcam_region) if self.webcam_region else None,
            'webcam_position': json.loads(self.webcam_position) if self.webcam_position else None,
            'sort_order':      self.sort_order,
        }
