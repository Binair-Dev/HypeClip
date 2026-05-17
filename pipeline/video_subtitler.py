import cv2
import numpy as np
from faster_whisper import WhisperModel
from moviepy.editor import VideoFileClip, concatenate_videoclips, CompositeVideoClip, TextClip, AudioFileClip

import os
from tqdm import tqdm
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import time


def _get_encoding_params():
    """Get encoding parameters - defaults to CPU."""
    return {
        'codec': 'libx264',
        'audio_codec': 'aac',
        'threads': 8,
        'fps': 30,
        'preset': 'medium',
        'bitrate': '6000k',
        'audio_bitrate': '192k',
        'ffmpeg_params': ['-profile:v', 'high', '-level', '4.0', '-pix_fmt', 'yuv420p']
    }


def extract_audio(video_path):
    """Extrait l'audio de la vidéo."""
    print("Extraction de l'audio...")
    video = VideoFileClip(video_path)
    audio_path = video_path.rsplit('.', 1)[0] + '_temp.wav'
    video.audio.write_audiofile(audio_path, verbose=False, logger=None)
    video.close()
    return audio_path

def get_whisper_config_cpu_optimized():
    """Configuration Whisper optimisée pour CPU"""
    return {
        'model_size': 'medium',
        'device': 'cpu',
        'compute_type': 'int8',
        'cpu_threads': 12,
        'num_workers': 6,
        'beam_size': 1,
        'best_of': 1,
        'temperature': 0.0,
        'condition_on_previous_text': False,
        'compression_ratio_threshold': 1.8,
        'no_speech_threshold': 0.8,
        'word_timestamps': False
    }

def preprocess_audio_for_speed(audio_path):
    """Prétraite l'audio pour accélérer Whisper"""
    import subprocess

    optimized_path = audio_path.replace('.wav', '_optimized.wav')

    cmd = [
        'ffmpeg', '-i', audio_path,
        '-threads', '16',
        '-ar', '16000',
        '-ac', '1',
        '-af', 'silenceremove=1:0:-30dB',
        '-y', optimized_path
    ]

    subprocess.run(cmd, capture_output=True)
    return optimized_path

def transcribe_with_whisper(audio_path, language='fr'):
    """Transcrit l'audio avec Faster Whisper optimisé CPU."""
    print(f"🚀 Chargement Whisper optimisé — langue: {language}...")

    try:
        config = get_whisper_config_cpu_optimized()
        print(f"⚡ Configuration Whisper CPU: {config['model_size']} - {config['cpu_threads']} threads")
        
        print("🔄 Preprocessing audio pour optimisation...")
        optimized_audio = preprocess_audio_for_speed(audio_path)

        print("💻 Initialisation Whisper CPU optimisé...")
        whisper_kwargs = {
            'device': 'cpu',
            'compute_type': 'int8',
            'cpu_threads': config['cpu_threads'],
            'num_workers': config['num_workers']
        }
        download_root = os.environ.get('WHISPER_MODEL_PATH')
        if download_root:
            whisper_kwargs['download_root'] = download_root
        model = WhisperModel(
            config['model_size'],
            **whisper_kwargs
        )

        device_used = f"cpu-{config['cpu_threads']}threads"
        print(f"✅ Modèle Whisper {config['model_size']} chargé: {device_used}")

        print("⚡ Transcription ultra-rapide en cours...")
        segments, _ = model.transcribe(
            optimized_audio,
            language=language,
            beam_size=config['beam_size'],
            best_of=config['best_of'],
            temperature=config['temperature'],
            word_timestamps=config['word_timestamps'],
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=1500,
                speech_pad_ms=30
            ),
            condition_on_previous_text=config['condition_on_previous_text'],
            compression_ratio_threshold=config['compression_ratio_threshold'],
            no_speech_threshold=config['no_speech_threshold']
        )
        
        result_segments = []
        for segment in segments:
            start = segment.start
            end = segment.end
            text = segment.text.strip()
            if text:
                result_segments.append((start, end, text))
                print(f"Segment trouvé: {text}")
        
        return result_segments
        
    except Exception as e:
        print(f"⚠️ Erreur lors de la transcription Whisper: {str(e)}")
        print("🔄 Retour de segments vides pour déclencher les sous-titres par défaut")
        return []

def cv2_frame_to_pil(frame):
    """Convertit une frame CV2 en image PIL."""
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

def pil_to_cv2_frame(pil_image):
    """Convertit une image PIL en frame CV2."""
    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

def get_font(size=32, font_name='Heavitas.ttf'):
    """Charge la police personnalisée ou utilise une police de secours."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(script_dir, 'fonts', font_name)
    
    try:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
        else:
            print(f"Police {font_name} non trouvée dans le dossier fonts")
        
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except OSError:
            print("Attention: Utilisation de la police par défaut")
            return ImageFont.load_default()

def add_subtitle_to_frame(frame, text):
    """Ajoute un sous-titre à une frame avec un fond élégant."""
    height, width = frame.shape[:2]
    
    pil_image = cv2_frame_to_pil(frame)
    draw = ImageDraw.Draw(pil_image)
    
    font = get_font(48)
    
    padding = 20
    max_text_width = width - 100
    
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        current_line.append(word)
        line = ' '.join(current_line)
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        
        if text_width > max_text_width:
            if len(current_line) > 1:
                current_line.pop()
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(line)
                current_line = []
    
    if current_line:
        lines.append(' '.join(current_line))
    
    line_height = font.size + 10
    total_text_height = len(lines) * line_height
    rect_height = total_text_height + 2 * padding
    
    rect_y = height // 3 - rect_height // 2
    
    background = Image.new('RGBA', (width, rect_height), (0, 0, 0, 0))
    background_draw = ImageDraw.Draw(background)
    
    background_draw.rectangle([(0, 0), (width, rect_height)], fill=(0, 0, 0, 180))
    
    pil_image.paste(background, (0, rect_y), background)
    
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        text_x = (width - text_width) // 2
        text_y = rect_y + padding + (i * line_height)
        
        draw.text((text_x, text_y), line, font=font, fill="white")
    
    return pil_to_cv2_frame(pil_image)

def safe_remove_file(file_path, max_attempts=5, delay=3):
    """Tente de supprimer un fichier avec plusieurs essais."""
    for attempt in range(max_attempts):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
        except Exception as e:
            if attempt < max_attempts - 1:
                print(f"Tentative {attempt + 1}/{max_attempts} de suppression de {file_path}...")
                time.sleep(delay)
            else:
                print(f"Note: Impossible de supprimer le fichier après {max_attempts} tentatives: {e}")
    return False

def create_video_with_subtitles(video_path, channel_name, output_dir, subtitles_enabled=False, language='fr'):
    """Crée la vidéo avec les sous-titres et le nom du streamer."""
    print(f"Création de la vidéo (sous-titres {'activés' if subtitles_enabled else 'désactivés'}) — langue: {language}...")

    os.makedirs(output_dir, exist_ok=True)
    print(f"Dossier de travail: {output_dir}")

    video_basename = os.path.basename(video_path)
    if '_combined_output' in video_basename:
        video_name = video_basename.split('_combined_output')[0]
    elif '_processed' in video_basename:
        video_name = video_basename.split('_processed')[0]
    else:
        video_name = video_basename.rsplit('.', 1)[0]

    temp_output = os.path.join(output_dir, f"{video_name}_with_subtitles.mp4")
    final_output = os.path.join(output_dir, f"{video_name}_final.mp4")
    print(f"Nom de base extrait: {video_name}")
    print(f"Fichier temporaire: {temp_output}")
    print(f"Fichier final: {final_output}")

    if not subtitles_enabled:
        print("⚠️ Sous-titres désactivés - Ajout du nom du streamer uniquement")
        import shutil
        import subprocess

        ffmpeg_cmd = [
            'ffmpeg', '-i', video_path,
            '-vf', f"drawtext=text='{channel_name}':fontsize=48:fontcolor=white:x=w-tw-30:y=30:box=1:boxcolor=black@0.7:boxborderw=20",
            '-codec:a', 'copy',
            '-y', final_output
        ]

        try:
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
            print(f"✅ Nom du streamer ajouté via FFmpeg: {final_output}")
            return final_output
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Erreur FFmpeg, copie simple de la vidéo")
            shutil.copy2(video_path, final_output)
            return final_output

    audio_path = extract_audio(video_path)
    segments = transcribe_with_whisper(audio_path, language=language)
    
    if not segments:
        if subtitles_enabled:
            print("⚠️ Aucun segment audio détecté par Whisper")
            print("📝 Ajout de sous-titres par défaut pour garantir la présence de texte")
            default_texts = [
                f"🎮 {channel_name.upper()} BEST MOMENTS",
                f"🔥 CLIP EPIC DE {channel_name.upper()}",
                f"⚡ {channel_name.upper()} HIGHLIGHTS"
            ]
            import random
            selected_text = random.choice(default_texts)
            segments = [(0.0, 999.0, selected_text)]
            print(f"📝 Sous-titre par défaut ajouté: '{selected_text}'")
        else:
            print("ℹ️ Aucun sous-titre ne sera ajouté (désactivé par configuration)")
    else:
        print(f"✓ {len(segments)} segments audio détectés pour sous-titrage")
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_output, fourcc, fps, (width, height))
    
    frame_count = 0
    progress_bar = tqdm(total=total_frames, desc="Traitement des frames")
    
    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            current_time = frame_count / fps
            current_text = ""
            
            for start, end, text in segments:
                if start <= current_time <= end:
                    current_text = text
                    break
            
            if current_text:
                frame = add_subtitle_to_frame(frame, current_text)
                if frame_count % 100 == 0:
                    print(f"Frame {frame_count}: Sous-titre ajouté - '{current_text[:50]}...'")
            elif frame_count % 200 == 0:
                print(f"Frame {frame_count}: Aucun sous-titre à ce moment")
            
            pil_image = cv2_frame_to_pil(frame)
            draw = ImageDraw.Draw(pil_image)
            font = get_font(48)
            
            bbox = draw.textbbox((0, 0), channel_name, font=font)
            text_width = bbox[2] - bbox[0]
            text_x = width - text_width - 30
            text_y = 30
            
            background = Image.new('RGBA', (text_width + 40, font.size + 40), (0, 0, 0, 180))
            pil_image.paste(background, (text_x - 20, text_y - 20), background)
            
            draw.text((text_x, text_y), channel_name, font=font, fill="white")
            
            frame = pil_to_cv2_frame(pil_image)
            
            out.write(frame)
            frame_count += 1
            progress_bar.update(1)
    finally:
        progress_bar.close()
        cap.release()
        out.release()
    
    print("Finalisation de la vidéo avec l'audio...")
    
    video_with_subs = None
    original_video = None
    original_audio = None
    final_video = None
    
    try:
        encoding_params = _get_encoding_params()

        video_with_subs = VideoFileClip(temp_output)
        original_video = VideoFileClip(video_path)
        original_audio = original_video.audio
        final_video = video_with_subs.set_audio(original_audio)

        final_video.write_videofile(
            final_output,
            codec=encoding_params['codec'],
            audio_codec=encoding_params['audio_codec'],
            threads=encoding_params['threads'],
            fps=encoding_params['fps'],
            preset=encoding_params['preset'],
            bitrate=encoding_params['bitrate'],
            audio_bitrate=encoding_params['audio_bitrate'],
            ffmpeg_params=encoding_params['ffmpeg_params'],
            verbose=False,
            logger=None
        )
    finally:
        if video_with_subs:
            video_with_subs.close()
        if original_video:
            original_video.close()
        if final_video:
            final_video.close()
    
    safe_remove_file(temp_output)
    if audio_path:
        safe_remove_file(audio_path)

    return final_output

def add_text_to_clip(clip_path, title):
    clip = VideoFileClip(clip_path, target_resolution=(1920, 1080))
    
    formatted_title = title[0].upper() + title[1:]
    txt_clip = TextClip(formatted_title, 
                        fontsize=60, 
                        color='white', 
                        font='Arial', 
                        stroke_color='white', 
                        stroke_width=2)
    
    padding_top = 50
    padding_right = 50
    
    txt_clip = txt_clip.set_position((clip.w - txt_clip.w - padding_right, padding_top))
    txt_clip = txt_clip.set_duration(clip.duration)
    
    final_clip = CompositeVideoClip([clip, txt_clip])
    
    temp_path = clip_path.replace('.mp4', '_temp_titled.mp4')
    
    encoding_params = _get_encoding_params()

    final_clip.write_videofile(
        temp_path,
        codec=encoding_params['codec'],
        audio_codec=encoding_params['audio_codec'],
        threads=encoding_params['threads'],
        fps=encoding_params['fps'],
        preset=encoding_params['preset'],
        bitrate=encoding_params['bitrate'],
        audio_bitrate=encoding_params['audio_bitrate'],
        ffmpeg_params=encoding_params['ffmpeg_params']
    )
    
    final_clip.close()
    clip.close()
    txt_clip.close()
    
    os.replace(temp_path, clip_path)


def main(video_path, title, output_dir=None):
    """Fonction principale."""
    if not os.path.exists(video_path):
        print(f"Erreur: Le fichier {video_path} n'existe pas.")
        return
    
    if not output_dir:
        raise ValueError("output_dir est requis pour créer les vidéos")
    
    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"Dossier de travail: {output_dir}")
        
        add_text_to_clip(video_path, title)
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        fonts_dir = os.path.join(script_dir, 'fonts')
        if not os.path.exists(fonts_dir):
            os.makedirs(fonts_dir)
            print(f"Dossier 'fonts' créé dans {fonts_dir}")
            print("Placez votre fichier de police (*.ttf) dans ce dossier")
        
        audio_path = extract_audio(video_path)
        segments = transcribe_with_whisper(audio_path)
        
        if not segments:
            print("Aucun segment de parole n'a été détecté.")
            return
        
        output_path = create_video_with_subtitles(video_path, segments, output_dir)
        print(f"\nVidéo sous-titrée créée avec succès: {output_path}")
        
        time.sleep(10)
        
        safe_remove_file(audio_path, max_attempts=10, delay=5)
        safe_remove_file(video_path, max_attempts=10, delay=5)
        
    except Exception as e:
        print(f"Une erreur est survenue: {str(e)}")
    finally:
        import gc
        gc.collect()
