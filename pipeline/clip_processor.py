import os
import cv2
import numpy as np
import time
from moviepy.editor import VideoFileClip


def _get_encoding_params():
    """Get encoding parameters - GPU if available, else CPU."""
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        if result.returncode == 0:
            return {
                'codec': 'libx264',  # moviepy uses libx264 even with GPU
                'audio_codec': 'aac',
                'threads': 0,
                'fps': 30,
                'preset': 'medium',
                'bitrate': '8000k',
                'audio_bitrate': '320k',
                'ffmpeg_params': [
                    '-profile:v', 'high',
                    '-level', '4.0',
                    '-crf', '18',
                    '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart'
                ]
            }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return {
        'codec': 'libx264',
        'audio_codec': 'aac',
        'threads': 0,   # OPTIMISÉ: Auto-détection FFmpeg
        'fps': 30,
        'preset': 'medium',
        'bitrate': '8000k',
        'audio_bitrate': '320k',
        'ffmpeg_params': [
            '-profile:v', 'high',
            '-level', '4.0',
            '-crf', '18',
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart'
        ]
    }


def process_video(input_path, output_path):
    """Traite la vidéo pour l'optimiser pour TikTok."""
    try:
        encoding_params = _get_encoding_params()
        print(f"🚀 Encodage optimisé: {encoding_params['codec']} - {encoding_params['preset']}")

        # Charger la vidéo
        clip = VideoFileClip(input_path)

        try:
            # Redimensionner à 1080x1920 (format vertical TikTok)
            clip = clip.resize(height=1920)

            # Centrer la vidéo horizontalement
            w = clip.w
            if w > 1080:
                # Si la vidéo est plus large que 1080px, on la centre
                x1 = (w - 1080) // 2
                clip = clip.crop(x1=x1, width=1080)
            elif w < 1080:
                # Si la vidéo est plus étroite que 1080px, on ajoute des bordures noires
                def make_frame(t):
                    frame = clip.get_frame(t)
                    h, w = frame.shape[:2]
                    new_frame = np.zeros((h, 1080, 3), dtype=np.uint8)
                    x_offset = (1080 - w) // 2
                    new_frame[:, x_offset:x_offset+w] = frame
                    return new_frame
                clip = VideoFileClip(None, ismask=False, audio=clip.audio, duration=clip.duration, make_frame=make_frame)

            # Écrire la vidéo traitée avec les paramètres optimisés
            print(f"⏱️ [TIKTOK PROCESSING START] Fichier: {output_path}")
            print(f"⏱️ [TIKTOK PROCESSING START] Codec: {encoding_params.get('codec', 'N/A')}, Preset: {encoding_params.get('preset', 'N/A')}")
            start_time = time.time()

            clip.write_videofile(
                output_path,
                codec=encoding_params['codec'],
                audio_codec=encoding_params['audio_codec'],
                threads=encoding_params['threads'],
                fps=encoding_params['fps'],
                preset=encoding_params['preset'],
                bitrate=encoding_params['bitrate'],
                audio_bitrate=encoding_params['audio_bitrate'],
                ffmpeg_params=encoding_params['ffmpeg_params']
            )

            elapsed = time.time() - start_time
            print(f"⏱️ [TIKTOK PROCESSING END] Durée: {elapsed:.2f}s")

            print(f"✓ Vidéo traitée avec succès: {output_path}")

        finally:
            # Toujours fermer le clip
            clip.close()

    except Exception as e:
        print(f"⚠️ Erreur lors du traitement: {str(e)}")
        raise


def main(video_path, output_dir=None):
    """Fonction principale."""
    if not output_dir:
        raise ValueError("output_dir est requis pour le traitement du clip")
        
    os.makedirs(output_dir, exist_ok=True)
    print(f"Dossier de travail: {output_dir}")
    
    # Construire le chemin de sortie
    output_path = os.path.join(output_dir, os.path.basename(video_path).replace('.mp4', '_processed.mp4'))
    
    print(f"Traitement de la vidéo: {video_path}")
    print(f"Sortie traitement: {output_path}")
    
    if not os.path.exists(video_path):
        raise Exception(f"Le fichier {video_path} n'existe pas")
    
    # Traitement de la vidéo
    process_video(video_path, output_path)
    print(f"Vidéo traitée avec succès: {output_path}")
