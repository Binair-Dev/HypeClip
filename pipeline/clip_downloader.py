import os
import requests
import time
import uuid
from functools import lru_cache

# Hardcoded configuration (previously from Config)
CLIPS_DEFAULT_SORT = "VIEWS_DESC"
CLIPS_DEFAULT_PERIOD = "LAST_DAY"
CLIPS_SORT_OPTIONS = ["VIEWS_DESC", "TIME_DESC", "TRENDING"]
CLIPS_PERIOD_OPTIONS = ["LAST_DAY", "LAST_WEEK", "LAST_MONTH", "ALL_TIME"]

CLIP_AMOUNT = 1

# Réduit le nombre de clips par chaîne
CHANNELS = []

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko',
    'Content-Type': 'application/json',
}

# Cache pour éviter les requêtes répétées
@lru_cache(maxsize=128)
def get_access_token(clip_slug):
    query = {
        "operationName": "VideoAccessToken_Clip",
        "variables": {"slug": clip_slug},
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "36b89d2507fce29e5ca551df756d27c1cfe079e2609642b4390aa4c35796eb11"
            }
        }
    }

    try:
        with requests.post('https://gql.twitch.tv/gql', headers=HEADERS, json=query) as response:
            response.raise_for_status()
            data = response.json()
            
            clip_data = data.get('data', {}).get('clip', {})
            if not clip_data:
                return None, None
                
            token = clip_data.get('playbackAccessToken', {})
            return token.get('signature'), token.get('value')
            
    except Exception as e:
        print(f"Erreur token: {str(e)}")
        return None, None

def get_clips(channel_name, sort_criteria=None, period_criteria=None, game_name_filter=None):
    # Utiliser les valeurs par défaut si non spécifiées
    sort_value = sort_criteria or CLIPS_DEFAULT_SORT
    period_value = period_criteria or CLIPS_DEFAULT_PERIOD

    query = {
        "operationName": "ClipsCards__User",
        "variables": {
            "login": channel_name,
            "limit": CLIP_AMOUNT,
            "criteria": {
                "sort": sort_value,
                "period": period_value
            }
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "90c33f5e6465122fba8f9371e2a97076f9ed06c6fed3788d002ab9eba8f91d88"
            }
        }
    }

    try:
        with requests.post('https://gql.twitch.tv/gql', headers=HEADERS, json=query) as response:
            response.raise_for_status()
            data = response.json()
            clips_data = data.get('data', {}).get('user', {}).get('clips', {}).get('edges', [])
            
            if not clips_data:
                print(f"Aucun clip trouvé pour {channel_name}")
                return []

            clips_result = []
            for clip in clips_data[:CLIP_AMOUNT]:
                clip_game = clip['node'].get('game', {}).get('name', 'Unknown Game')
                clip_info = {
                    'slug': clip['node']['slug'],
                    'title': clip['node'].get('title', 'Sans titre'),
                    'duration': clip['node'].get('durationSeconds', 0),
                    'view_count': clip['node'].get('viewCount', 0),
                    'game': clip_game
                }
                
                # Si un filtre de jeu est spécifié, ne retourner que les clips du bon jeu
                if game_name_filter:
                    if clip_game.lower() == game_name_filter.lower():
                        clips_result.append(clip_info)
                else:
                    clips_result.append(clip_info)
            
            return clips_result

    except Exception as e:
        print(f"Erreur clips: {str(e)}")
        return []

def get_clip_url(clip_slug):
    signature, token = get_access_token(clip_slug)
    if not signature or not token:
        return None

    try:
        with requests.post('https://gql.twitch.tv/gql', headers=HEADERS, json={
            "operationName": "VideoAccessToken_Clip",
            "variables": {"slug": clip_slug},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "36b89d2507fce29e5ca551df756d27c1cfe079e2609642b4390aa4c35796eb11"
                }
            }
        }) as response:
            response.raise_for_status()
            data = response.json()
            qualities = data.get('data', {}).get('clip', {}).get('videoQualities', [])
            
            if qualities:
                # Utilise la meilleure qualité
                quality_index = 0
                base_url = qualities[quality_index].get('sourceURL', '')
                if base_url:
                    device_id = str(uuid.uuid4())
                    return f"{base_url}?sig={signature}&token={token}&device_id={device_id}"
            
            return None

    except Exception as e:
        print(f"Erreur URL: {str(e)}")
        return None

def download_clip(url, filename):
    try:
        with requests.get(url, stream=True) as response:
            response.raise_for_status()
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=16384):  # Augmente la taille du chunk
                    if chunk:
                        f.write(chunk)
            
            return os.path.getsize(filename) > 0

    except Exception as e:
        print(f"Erreur téléchargement: {str(e)}")
        if os.path.exists(filename):
            os.remove(filename)
        return False

def process_channel(channel, game_name=None, sort_criteria=None, period_criteria=None):
    # Obtenir le chemin absolu du dossier clips
    clips_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clips")
    os.makedirs(clips_dir, exist_ok=True)
    
    clips = get_clips(channel, sort_criteria, period_criteria)
    successful_downloads = []
    
    for i, clip in enumerate(clips, 1):
        # Accepter les jeux populaires ou le jeu spécifié
        popular_games = ["Grand Theft Auto V", "VALORANT", "League of Legends", "Fortnite", "Call of Duty", "Apex Legends"]
        if game_name == "NONE" or (game_name and clip['game'] == game_name) or clip['game'] in popular_games:
            download_url = get_clip_url(clip['slug'])
            if download_url:
                filename = os.path.join(clips_dir, f"{channel}.mp4")
                if download_clip(download_url, filename):
                    successful_downloads.append(filename)
                time.sleep(1)  # Réduit le délai entre les téléchargements
        else:
            print(f"Le jeu {clip['game']} n'est pas supporté")
    return successful_downloads

def main(channel, amount, output_dir=None, game_name=None, sort_criteria=None, period_criteria=None):
    """Fonction principale."""
    # Use output_dir if provided, otherwise fall back to clips directory
    if output_dir:
        target_dir = output_dir
    else:
        target_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clips")
    os.makedirs(target_dir, exist_ok=True)
    print(f"Dossier de téléchargement: {target_dir}")
    
    clips = get_clips(channel, sort_criteria, period_criteria)
    successful_downloads = []

    for i, clip in enumerate(clips):
        if i >= amount:
            break
        # Accepter les jeux populaires ou le jeu spécifié
        popular_games = ["Grand Theft Auto V", "VALORANT", "League of Legends", "Fortnite", "Call of Duty", "Apex Legends"]
        if game_name == "NONE" or (game_name and clip['game'] == game_name) or clip['game'] in popular_games:
            download_url = get_clip_url(clip['slug'])
            if download_url:
                filename = os.path.join(target_dir, f"{channel}.mp4")
                print(f"Téléchargement dans: {filename}")
                if download_clip(download_url, filename):
                    successful_downloads.append(filename)
                time.sleep(1)
        else:
            print(f"Le jeu {clip['game']} n'est pas supporté")

    return successful_downloads

if __name__ == "__main__":
    main()
