import cv2
import numpy as np
import os
import json
import random
import subprocess
from typing import Dict, Optional, Tuple, List
from pathlib import Path

# CRITIQUE: Forcer MediaPipe CPU AVANT l'import
# La variable doit être définie AVANT l'import, sinon GPU sera déjà initialisé
os.environ['MEDIAPIPE_DISABLE_GPU'] = '1'

import mediapipe as mp


def _detect_gpu_available():
    """Check if NVIDIA GPU is available for encoding."""
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


class OptimizedWebcamExtractor:
    """
    Extracteur de webcam optimisé pour HypeClip
    Remplace l'ancien système webcam_extractor.py + webcam_detector.py
    """
    
    def __init__(self):
        # Detect GPU availability directly
        self.use_gpu = _detect_gpu_available()
        if self.use_gpu:
            print("GPU Mode GPU active pour l'extraction webcam optimisee")
        else:
            print("CPU Mode CPU pour l'extraction webcam optimisee")

        # MediaPipe pour la détection de visages humains (CPU forcé au niveau module)
        self.mp_face_detection = mp.solutions.face_detection
        self.face_detection = self.mp_face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.6  # Plus strict pour éviter les faux positifs
        )

        print("OK Extracteur webcam optimise initialise (MediaPipe: CPU force)")
        
    def extract_search_region(self, frame: np.ndarray) -> Tuple[np.ndarray, Tuple[int, int]]:
        """
        Extrait la zone de recherche optimisée (bande gauche étendue)
        Basé sur l'analyse : webcams toujours dans la zone gauche
        """
        h, w = frame.shape[:2]
        # Zone étendue : 1/4 de la largeur + 30px, 50% de la hauteur
        region_w = min((w // 4) + 30, w)
        region_h = h // 2  # Seulement 50% de la hauteur
        
        search_region = frame[0:region_h, 0:region_w]
        return search_region, (0, 0)
    
    def detect_face_in_region(self, region: np.ndarray) -> Optional[Dict]:
        """
        Détecte un visage dans la région de recherche
        """
        rgb_region = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
        results = self.face_detection.process(rgb_region)
        
        if results.detections:
            # Prendre la détection avec le meilleur score
            best_detection = max(results.detections, key=lambda d: d.score[0])
            
            if best_detection.score[0] > 0.6:  # Seuil strict
                bbox = best_detection.location_data.relative_bounding_box
                h, w = region.shape[:2]
                
                x = max(0, int(bbox.xmin * w))
                y = max(0, int(bbox.ymin * h))
                width = min(int(bbox.width * w), w - x)
                height = min(int(bbox.height * h), h - y)
                
                # Taille minimale pour être considéré comme une webcam
                if width > 30 and height > 30:
                    return {
                        'bbox': (x, y, width, height),
                        'confidence': float(best_detection.score[0]),
                        'has_face': True
                    }
        
        return None
    
    def analyze_skin_texture(self, face_roi: np.ndarray) -> Dict:
        """
        Analyse rapide pour distinguer vrai visage vs 3D
        Version simplifiée et optimisée
        """
        features = {}
        
        if face_roi.size == 0:
            return features
        
        # 1. Variance de couleur (les vraies webcams ont plus de variation)
        hsv = cv2.cvtColor(face_roi, cv2.COLOR_BGR2HSV)
        features['color_variance'] = float(np.std(hsv))
        
        # 2. Niveau de bruit (les webcams ont du bruit, les jeux sont plus propres)
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        features['noise_level'] = float(np.std(laplacian))
        
        # 3. Saturation moyenne (les jeux ont tendance à être plus saturés)
        features['mean_saturation'] = float(np.mean(hsv[:, :, 1]))
        
        # 4. Présence de tons chair
        lower_skin = np.array([0, 30, 60], dtype=np.uint8)
        upper_skin = np.array([20, 150, 255], dtype=np.uint8)
        skin_mask = cv2.inRange(hsv, lower_skin, upper_skin)
        features['skin_presence'] = float(np.sum(skin_mask > 0) / skin_mask.size)
        
        return features
    
    def is_real_webcam(self, features: Dict) -> bool:
        """
        Détermine si c'est une vraie webcam - version optimisée
        """
        score = 0
        
        # Critères basés sur l'analyse des vrais streamers
        if features.get('color_variance', 0) > 30:
            score += 1
        if features.get('noise_level', 0) > 3:
            score += 1
        if features.get('mean_saturation', 255) < 120:
            score += 1
        if features.get('skin_presence', 0) > 0.1:
            score += 1
            
        # Au moins 2 critères sur 4 pour être considéré comme réel
        return score >= 2
    
    def detect_webcam_in_frame(self, frame: np.ndarray) -> Dict:
        """
        Détecte une webcam en cherchant dans la zone optimisée
        """
        result = {
            'has_webcam': False,
            'confidence': 0.0,
            'region': None,
            'method': 'optimized_detector'
        }
        
        # Extraire la zone de recherche optimisée
        search_region, offset = self.extract_search_region(frame)
        
        # Chercher un visage dans cette région
        face_detection = self.detect_face_in_region(search_region)
        
        if face_detection:
            # Analyser la qualité de la région du visage
            x, y, w, h = face_detection['bbox']
            face_roi = search_region[y:y+h, x:x+w]
            
            if face_roi.size > 0:
                features = self.analyze_skin_texture(face_roi)
                
                if self.is_real_webcam(features):
                    result['has_webcam'] = True
                    result['confidence'] = face_detection['confidence']
                    result['region'] = face_detection['bbox']
                    result['features'] = features
        
        return result
    
    def analyze_random_frames_for_optimal_position(self, video_path: str, num_samples: int = 4) -> Optional[Tuple[int, int, int, int]]:
        """
        Analyse plusieurs frames aléatoires pour la position optimale
        OPTIMISÉ: 4 samples suffisent (-50% temps, précision identique)
        """
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            return None
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        
        if total_frames < num_samples:
            num_samples = total_frames
        
        # Éviter les 5 premières et 5 dernières secondes
        start_frame = min(fps * 5, total_frames // 4)
        end_frame = max(total_frames - fps * 5, total_frames * 3 // 4)
        
        if end_frame <= start_frame:
            start_frame = 0
            end_frame = total_frames
        
        frame_positions = random.sample(range(start_frame, end_frame), num_samples)
        detections = []
        
        print(f"  Analyse de {num_samples} frames pour position optimale...")
        
        for frame_pos in frame_positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
            ret, frame = cap.read()
            
            if ret:
                detection = self.detect_webcam_in_frame(frame)
                
                if detection['has_webcam'] and detection['region']:
                    detections.append({
                        'region': detection['region'],
                        'confidence': detection['confidence']
                    })
        
        cap.release()
        
        if not detections:
            print("  Aucune webcam détectée dans l'analyse multi-frames")
            return None
        
        # Position moyenne pondérée par la confiance
        total_weight = sum(d['confidence'] for d in detections)
        
        if total_weight == 0:
            return None
        
        avg_x = sum(d['region'][0] * d['confidence'] for d in detections) / total_weight
        avg_y = sum(d['region'][1] * d['confidence'] for d in detections) / total_weight
        avg_w = sum(d['region'][2] * d['confidence'] for d in detections) / total_weight
        avg_h = sum(d['region'][3] * d['confidence'] for d in detections) / total_weight
        
        optimal_region = (int(avg_x), int(avg_y), int(avg_w), int(avg_h))
        
        print(f"  Position optimale calculée: {optimal_region}")
        print(f"  Basée sur {len(detections)} détections fiables")
        
        return optimal_region
    
    def calculate_16_9_region(self, webcam_bbox: Tuple[int, int, int, int], 
                             frame_shape: Tuple[int, int]) -> Tuple[int, int, int, int]:
        """
        Calcule une région 16:9 centrée sur la webcam détectée
        """
        frame_h, frame_w = frame_shape[:2]
        webcam_x, webcam_y, webcam_w, webcam_h = webcam_bbox
        
        # Centre de la webcam
        center_x = webcam_x + webcam_w // 2
        center_y = webcam_y + webcam_h // 2
        
        # Calculer la taille de la région 16:9
        base_size = max(webcam_w, webcam_h)
        
        # Facteur d'agrandissement optimisé pour les shorts
        expansion_factor = 3.5
        
        # Dimensions 16:9
        region_width = int(base_size * expansion_factor)
        region_height = int(region_width * 9 / 16)
        
        # Tailles minimales et maximales
        min_width, min_height = 320, 180
        if region_width < min_width:
            region_width = min_width
            region_height = min_height
        
        if region_width > frame_w:
            region_width = frame_w
            region_height = int(frame_w * 9 / 16)
            
        if region_height > frame_h:
            region_height = frame_h
            region_width = int(frame_h * 16 / 9)
        
        # Centrer sur la webcam
        region_x = center_x - region_width // 2
        region_y = center_y - region_height // 2
        
        # Rester dans les limites
        region_x = max(0, min(region_x, frame_w - region_width))
        region_y = max(0, min(region_y, frame_h - region_height))
        
        # Ajuster les dimensions finales
        region_width = min(region_width, frame_w - region_x)
        region_height = min(region_height, frame_h - region_y)
        
        return (region_x, region_y, region_width, region_height)
    
    def extract_webcam_16_9(self, video_path: str, output_path: str, duration: int = None) -> bool:
        """
        Extrait la webcam en format 16:9 avec analyse optimisée
        Fonction principale qui remplace l'ancien système
        """
        print(f"Extraction webcam optimisee: {os.path.basename(video_path)}")
        
        # 1. Analyser la première frame pour détecter une webcam
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            print(f"ERREUR Impossible d'ouvrir la video: {video_path}")
            return False
        
        # Lire la première frame
        ret, first_frame = cap.read()
        if not ret:
            print("ERREUR Impossible de lire la premiere frame")
            cap.release()
            return False
        
        # Détection initiale
        initial_detection = self.detect_webcam_in_frame(first_frame)
        
        if not initial_detection['has_webcam']:
            print("ERREUR Aucune webcam detectee dans la premiere frame")
            cap.release()
            return False
        
        print(f"OK Webcam detectee (confiance: {initial_detection['confidence']:.2f})")
        
        # 2. Analyse multi-frames pour position optimale
        cap.release()  # Fermer avant de rouvrir pour l'analyse
        
        optimal_region = self.analyze_random_frames_for_optimal_position(video_path)
        
        if optimal_region is None:
            print("ATTENTION Utilisation de la detection initiale")
            optimal_region = initial_detection['region']
        else:
            print("OK Position optimisee calculee")
        
        # 3. Calculer la région 16:9
        region_16_9 = self.calculate_16_9_region(optimal_region, first_frame.shape)
        region_x, region_y, region_w, region_h = region_16_9
        
        print(f"Region 16:9: {region_w}x{region_h} a ({region_x}, {region_y})")
        
        # 4. Extraire la vidéo avec FFmpeg GPU (h264_nvenc)
        print(f"Extraction GPU en cours... (région: {region_w}x{region_h})")

        # Déterminer la durée maximale
        cap = cv2.VideoCapture(video_path)
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        # Calculer la durée en secondes
        if duration is None:
            duration_sec = total_frames / fps if fps > 0 else None
        else:
            duration_sec = duration

        # Utiliser FFmpeg avec h264_nvenc pour extraction GPU ultra-rapide
        try:
            import sys

            use_nvenc = self.use_gpu

            # Construction de la commande FFmpeg
            ffmpeg_cmd = ['ffmpeg', '-y', '-i', video_path]

            # Filtre de crop pour extraire la région webcam
            crop_filter = f'crop={region_w}:{region_h}:{region_x}:{region_y}'

            # Durée limitée si spécifiée
            if duration_sec:
                ffmpeg_cmd.extend(['-t', str(duration_sec)])

            # Encodage GPU si disponible, sinon CPU rapide
            if use_nvenc:
                print("🚀 Extraction webcam GPU (h264_nvenc)")
                ffmpeg_cmd.extend([
                    '-filter:v', crop_filter,
                    '-c:v', 'h264_nvenc',
                    '-preset', 'p3',  # Preset rapide
                    '-b:v', '4000k',
                    '-c:a', 'aac',
                    '-b:a', '128k'
                ])
            else:
                print("💻 Extraction webcam CPU (libx264)")
                ffmpeg_cmd.extend([
                    '-filter:v', crop_filter,
                    '-c:v', 'libx264',
                    '-preset', 'faster',
                    '-crf', '23',
                    '-c:a', 'aac',
                    '-b:a', '128k'
                ])

            ffmpeg_cmd.append(output_path)

            # Exécuter FFmpeg
            result = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode == 0 and os.path.exists(output_path):
                print(f"OK Extraction terminee (GPU): {output_path}")
                return True
            else:
                print(f"⚠️ Erreur FFmpeg: {result.stderr}")
                return False

        except Exception as e:
            print(f"⚠️ Erreur extraction FFmpeg: {e}")
            return False


def process_video(input_path, output_path):
    """
    Fonction compatible avec l'ancien interface webcam_extractor.py
    Traite la vidéo et extrait la webcam en 16:9
    """
    extractor = OptimizedWebcamExtractor()
    
    # Vérifier que le fichier d'entrée existe
    if not os.path.exists(input_path):
        raise Exception(f"Le fichier {input_path} n'existe pas")
    
    # Extraire la webcam avec le nouveau système
    success = extractor.extract_webcam_16_9(input_path, output_path)
    
    if not success:
        raise Exception("Impossible de détecter ou extraire une webcam dans cette vidéo")
    
    print(f"OK Webcam extraite avec succes: {output_path}")


def main(channel, output_dir=None):
    """
    Fonction principale pour l'extraction webcam.
    """
    if not output_dir:
        raise ValueError("output_dir est requis pour extraire la webcam")
        
    os.makedirs(output_dir, exist_ok=True)
    print(f"Dossier de travail: {output_dir}")
    
    # Construire les chemins
    input_path = os.path.join(output_dir, f"{channel}.mp4")
    output_path = os.path.join(output_dir, f"{channel}_webcam_output.mp4")
    
    print(f"Video d'entree: {input_path}")
    print(f"Sortie webcam: {output_path}")
    
    # Créer l'extracteur optimisé
    extractor = OptimizedWebcamExtractor()
    
    # Extraction avec le nouveau système
    success = extractor.extract_webcam_16_9(input_path, output_path)
    
    if not success:
        raise Exception("Aucune webcam réelle détectée dans la vidéo")
    
    print(f"OK Extraction optimisee terminee: {output_path}")
    
    # Créer aussi le fichier "detected" pour compatibilité avec l'ancien workflow
    detected_path = os.path.join(output_dir, f"{channel}_webcam_detected.mp4")
    import shutil
    shutil.copy2(output_path, detected_path)
    print(f"OK Fichier de compatibilite cree: {detected_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        main(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python webcam_extractor_optimized.py <channel> <output_dir>")
