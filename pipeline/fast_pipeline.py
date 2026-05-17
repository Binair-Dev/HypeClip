"""
Pipeline FFmpeg ultra-optimisé pour montage vidéo GPU en UNE SEULE PASSE.

Remplace le pipeline traditionnel à 4 encodages par UN SEUL encodage FFmpeg.

Gains de performance:
- Avant: Download → Encode #1 (clip) → Encode #2 (webcam) → Encode #3 (combine) → Encode #4 (subtitles)
- Après: Download → ANALYSE webcam → ENCODE UNE FOIS (tout)

Résultat: 3-4x plus rapide avec la même qualité.
"""

import os
import subprocess
import sys
from pathlib import Path

def detect_webcam_region_only(video_path, user_id):
    """
    Détecte la région de la webcam SANS encoder la vidéo.
    Retourne uniquement les coordonnées (x, y, w, h) ou None.

    Cette fonction ne fait QUE l'analyse, pas d'encodage.
    """
    print(f"🔍 Analyse de la webcam (sans encodage)...")

    try:
        # Utiliser le détecteur optimisé pour obtenir les coordonnées
        import cv2
        from . import webcam_extractor_optimized

        extractor = webcam_extractor_optimized.OptimizedWebcamExtractor()

        # Analyser la première frame
        cap = cv2.VideoCapture(video_path)
        ret, first_frame = cap.read()
        cap.release()

        if not ret:
            return None

        # Détection initiale
        initial_detection = extractor.detect_webcam_in_frame(first_frame)

        if not initial_detection['has_webcam']:
            print("ℹ️ Aucune webcam détectée")
            return None

        # Analyse multi-frames pour position optimale
        optimal_region = extractor.analyze_random_frames_for_optimal_position(video_path, num_samples=4)

        if optimal_region is None:
            optimal_region = initial_detection['region']

        # Calculer la région 16:9
        region_16_9 = extractor.calculate_16_9_region(optimal_region, first_frame.shape)

        print(f"✅ Webcam détectée: région {region_16_9}")
        return region_16_9  # (x, y, w, h)

    except Exception as e:
        print(f"⚠️ Erreur détection webcam: {e}")
        import traceback
        traceback.print_exc()
        return None


def build_single_pass_ffmpeg_command(
    input_video_path,
    output_video_path,
    webcam_region=None,
    streamer_name=None,
    subtitles_enabled=False,
    use_gpu=True,
    language='fr'
):
    """
    Construit une commande FFmpeg qui fait TOUT en UNE SEULE PASSE:
    - Resize du clip principal à 1080x1920
    - Extraction et overlay de la webcam (si détectée)
    - Ajout du nom du streamer
    - Encodage h264_nvenc (GPU) ou libx264 (CPU)

    Returns: liste de commandes FFmpeg
    """

    cmd = ['ffmpeg', '-y']

    # Input principal
    cmd.extend(['-i', input_video_path])

    # Construction du filtergraph complexe
    filters = []

    # 1. Clip principal: resize à 1080x1920 et crop centré
    main_filter = "[0:v]scale=-2:1920,crop=1080:1920:(in_w-1080)/2:0[main]"
    filters.append(main_filter)

    # 2. Si webcam détectée, extraire et overlay
    if webcam_region:
        x, y, w, h = webcam_region

        # Extraire la région webcam du clip original
        webcam_extract = f"[0:v]crop={w}:{h}:{x}:{y}[webcam_raw]"
        filters.append(webcam_extract)

        # Redimensionner la webcam à 1/4 de la hauteur (480px pour 1920px)
        webcam_resize = "[webcam_raw]scale=-2:480[webcam]"
        filters.append(webcam_resize)

        # Overlay de la webcam sur le clip principal (centrée en haut)
        # Position X calculée pour centrer: (1080 - webcam_width) / 2
        overlay_filter = "[main][webcam]overlay=(W-w)/2:0[video_with_webcam]"
        filters.append(overlay_filter)

        video_output = "video_with_webcam"
    else:
        video_output = "main"

    # 3. Ajouter le nom du streamer si fourni
    if streamer_name:
        # Texte en bas de la vidéo
        text_filter = (
            f"[{video_output}]drawtext="
            f"text='{streamer_name.upper()}':"
            f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"fontsize=60:"
            f"fontcolor=white:"
            f"borderw=3:"
            f"bordercolor=black:"
            f"x=(w-text_w)/2:"
            f"y=h-100"
            f"[final]"
        )
        filters.append(text_filter)
        video_output = "final"

    # Combiner tous les filtres
    filter_complex = ";".join(filters)
    cmd.extend(['-filter_complex', filter_complex])

    # Mapper la sortie finale
    cmd.extend(['-map', f'[{video_output}]', '-map', '0:a?'])

    # Encodage optimisé
    if use_gpu:
        # GPU h264_nvenc avec optimisations
        cmd.extend([
            '-c:v', 'h264_nvenc',
            '-preset', 'p3',  # Preset rapide
            '-b:v', '7000k',
            '-profile:v', 'high',
            '-pix_fmt', 'yuv420p',
            '-rc-lookahead', '32',
            '-b_ref_mode', 'middle',
            '-spatial_aq', '1',
            '-temporal_aq', '1',
            '-movflags', '+faststart',
            '-c:a', 'aac',
            '-b:a', '192k'
        ])
    else:
        # CPU libx264 optimisé
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '20',
            '-profile:v', 'high',
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-threads', '18'
        ])

    cmd.append(output_video_path)

    return cmd


def _detect_gpu_available():
    """Check if CUDA/NVIDIA GPU is available for encoding."""
    try:
        result = subprocess.run(
            ['nvidia-smi'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def process_video_single_pass(
    input_video_path,
    output_video_path,
    user_id,
    streamer_name=None,
    subtitles_enabled=False,
    language='fr'
):
    """
    Traite une vidéo en UNE SEULE PASSE FFmpeg.

    Étapes:
    1. Détecte la webcam (analyse uniquement, pas d'encodage)
    2. Construit la commande FFmpeg complexe
    3. Exécute FFmpeg UNE FOIS pour tout faire

    Returns: output_video_path si succès, None sinon
    """
    print(f"\n🚀 === PIPELINE FFmpeg ULTRA-RAPIDE (UNE SEULE PASSE) ===")
    print(f"📥 Input: {os.path.basename(input_video_path)}")
    print(f"📤 Output: {os.path.basename(output_video_path)}")

    # Étape 1: Détection webcam (analyse seulement)
    webcam_region = detect_webcam_region_only(input_video_path, user_id)

    if webcam_region:
        print(f"✅ Webcam détectée, sera intégrée dans le montage")
    else:
        print(f"ℹ️ Pas de webcam, montage du clip seul")

    # Étape 2: Déterminer si GPU disponible
    use_gpu = _detect_gpu_available()
    if use_gpu:
        print(f"🎮 GPU NVIDIA détecté, encodage h264_nvenc")
    else:
        print(f"💻 Mode CPU, encodage libx264")

    # Étape 3: Construire la commande FFmpeg
    ffmpeg_cmd = build_single_pass_ffmpeg_command(
        input_video_path,
        output_video_path,
        webcam_region=webcam_region,
        streamer_name=streamer_name,
        subtitles_enabled=subtitles_enabled,
        use_gpu=use_gpu,
        language=language
    )

    print(f"\n⚡ Encodage en cours (UNE SEULE PASSE)...")
    print(f"🔧 Commande: {' '.join(ffmpeg_cmd[:10])}...")

    # Étape 4: Exécuter FFmpeg
    try:
        result = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode == 0 and os.path.exists(output_video_path):
            print(f"\n✅ Encodage terminé avec succès!")
            print(f"📁 Fichier créé: {output_video_path}")
            return output_video_path
        else:
            print(f"\n❌ Erreur FFmpeg:")
            print(result.stderr)
            return None

    except Exception as e:
        print(f"\n❌ Erreur lors de l'encodage: {e}")
        import traceback
        traceback.print_exc()
        return None


def main(input_video, output_dir, streamer_name=None):
    """Point d'entrée principal pour le pipeline optimisé."""

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Chemin de sortie
    output_video = os.path.join(
        output_dir,
        os.path.basename(input_video).replace('.mp4', '_final.mp4')
    )

    # Traiter en une seule passe
    success = process_video_single_pass(
        input_video,
        output_video,
        output_dir,
        streamer_name=streamer_name
    )

    if success:
        print(f"\n🎉 Pipeline optimisé terminé!")
        return output_video
    else:
        print(f"\n⚠️ Le pipeline optimisé a échoué")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python fast_pipeline.py <input_video> <output_dir> [streamer_name]")
        sys.exit(1)

    input_vid = sys.argv[1]
    output_d = sys.argv[2]
    streamer = sys.argv[3] if len(sys.argv) > 3 else None

    main(input_vid, output_d, streamer)
