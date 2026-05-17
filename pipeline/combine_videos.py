import os
import time
from moviepy.editor import VideoFileClip, CompositeVideoClip


def _get_encoding_params():
    """Get encoding parameters - defaults to CPU."""
    return {
        'codec': 'libx264',
        'audio_codec': 'aac',
        'threads': 0,               # OPTIMISÉ: Auto-détection FFmpeg
        'fps': 30,
        'preset': 'fast',           # QUALITÉ: Meilleur compromis
        'bitrate': '6000k',         # QUALITÉ: 6 Mbps pour netteté
        'audio_bitrate': '192k',    # QUALITÉ: Audio amélioré
        'ffmpeg_params': [
            '-crf', '20',           # QUALITÉ: Très net
            '-profile:v', 'high',   # QUALITÉ: Profil high
            '-level', '4.1',
            '-pix_fmt', 'yuv420p',
            '-tune', 'film',        # QUALITÉ: Optimisé contenu vidéo
            '-movflags', '+faststart',
            '-bufsize', '12000k'    # Buffer adapté
        ]
    }


def process_video(clip_path, webcam_path, output_path):
    """Combine la vidéo principale avec la webcam."""
    try:
        # Charger les vidéos
        main_clip = VideoFileClip(clip_path)

        try:
            webcam_clip = VideoFileClip(webcam_path)

            try:
                # Redimensionner la webcam à 1/4 de la hauteur
                webcam_height = main_clip.h // 4
                webcam_clip = webcam_clip.resize(height=webcam_height)

                # Calculer la position pour centrer horizontalement
                x_position = (main_clip.w - webcam_clip.w) // 2

                # Positionner la webcam en haut centrée
                webcam_clip = webcam_clip.set_position((x_position, 0))

                # Combiner les vidéos
                final_clip = CompositeVideoClip([main_clip, webcam_clip])

                try:
                    encoding_params = _get_encoding_params()
                    print(f"🚀 Encodage optimisé: {encoding_params['codec']} - {encoding_params['preset']}")

                    # Écrire la vidéo finale avec fallback automatique
                    try:
                        print(f"⏱️ [COMBINE VIDEO START] Fichier: {output_path}")
                        print(f"⏱️ [COMBINE VIDEO START] Codec: {encoding_params.get('codec', 'N/A')}, Preset: {encoding_params.get('preset', 'N/A')}")
                        start_time = time.time()

                        final_clip.write_videofile(
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
                        print(f"⏱️ [COMBINE VIDEO END] Durée: {elapsed:.2f}s")
                    except Exception as gpu_error:
                        import traceback
                        print(f"⚠️ Encodage échoué: {str(gpu_error)}")
                        print(f"📋 Détails de l'erreur:")
                        traceback.print_exc()
                        print("🔄 Tentative avec encodage CPU...")

                        cpu_params = _get_encoding_params()

                        print(f"⏱️ [COMBINE CPU FALLBACK START] Fichier: {output_path}")
                        print(f"⏱️ [COMBINE CPU FALLBACK START] Preset: {cpu_params['preset']}, Threads: {cpu_params['threads']}")
                        cpu_start = time.time()

                        final_clip.write_videofile(
                            output_path,
                            codec=cpu_params['codec'],
                            audio_codec=cpu_params['audio_codec'],
                            threads=cpu_params['threads'],
                            fps=cpu_params['fps'],
                            preset=cpu_params['preset'],
                            bitrate=cpu_params['bitrate'],
                            audio_bitrate=cpu_params['audio_bitrate'],
                            ffmpeg_params=cpu_params['ffmpeg_params']
                        )

                        cpu_elapsed = time.time() - cpu_start
                        print(f"⏱️ [COMBINE CPU FALLBACK END] Durée: {cpu_elapsed:.2f}s")
                        print("✓ Encodage CPU réussi")

                    print(f"✓ Vidéos combinées avec succès: {output_path}")

                finally:
                    # Toujours fermer final_clip
                    final_clip.close()

            finally:
                # Toujours fermer webcam_clip
                webcam_clip.close()

        finally:
            # Toujours fermer main_clip
            main_clip.close()

    except Exception as e:
        print(f"⚠️ Erreur lors de la combinaison: {str(e)}")
        raise


def main(clip_path, webcam_path, output_dir=None):
    """Fonction principale."""
    if not output_dir:
        raise ValueError("output_dir est requis pour combiner les vidéos")
        
    os.makedirs(output_dir, exist_ok=True)
    print(f"Dossier de travail: {output_dir}")
    
    # Construire le chemin de sortie
    output_path = os.path.join(output_dir, os.path.basename(clip_path).replace('_processed.mp4', '_combined_output.mp4'))
    
    print(f"Traitement des vidéos:")
    print(f"- Clip principal: {clip_path}")
    print(f"- Webcam: {webcam_path}")
    print(f"- Sortie: {output_path}")
    
    if not os.path.exists(clip_path):
        raise Exception(f"Le fichier {clip_path} n'existe pas")
    if not os.path.exists(webcam_path):
        raise Exception(f"Le fichier {webcam_path} n'existe pas")
    
    # Traitement des vidéos
    process_video(clip_path, webcam_path, output_path)
    print(f"Vidéos combinées avec succès: {output_path}")
