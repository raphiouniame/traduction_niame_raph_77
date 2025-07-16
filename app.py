from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import os
import uuid
import time
import requests
import hashlib
import json
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify, make_response
from dotenv import load_dotenv
from gtts import gTTS

# Charger les variables d'environnement
load_dotenv()

# Initialiser Flask
app = Flask(__name__)

# Récupérer la clé API depuis les variables d'environnement
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
DEEPL_API_URL = "https://api-free.deepl.com/v2/translate" 

# Créer le dossier static s'il n'existe pas
os.makedirs(os.path.join(os.path.dirname(__file__), 'static'), exist_ok=True)

# Vérifier que la clé API est bien définie (optionnel en production)
if not DEEPL_API_KEY:
    print("ATTENTION: La clé API DeepL n'est pas définie dans les variables d'environnement")

# Vérifier si Tesseract est disponible
def is_tesseract_available():
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False

TESSERACT_AVAILABLE = is_tesseract_available()
if not TESSERACT_AVAILABLE:
    print("ATTENTION: Tesseract OCR n'est pas disponible")

# Langues supportées par DeepL et gTTS
SUPPORTED_LANGUAGES = {
    'fr': 'Français',
    'en': 'Anglais',
    'es': 'Espagnol',
    'de': 'Allemand',
    'it': 'Italien',
    'pt': 'Portugais',
    'ja': 'Japonais',
    'ko': 'Coréen',
    'zh': 'Chinois (simplifié)',
}

# Réponses fixes selon certaines requêtes
STATIC_RESPONSES = {
    "qui t'a créé": "Raphaël Niamé (+225 05 06 53 15 22)",
    "who created you": "Raphaël Niamé (+225 05 06 53 15 22)",
    "wer hat dich erstellt": "Raphaël Niamé (+225 05 06 53 15 22)",
    "quién te creó": "Raphaël Niamé (+225 05 06 53 15 22)",
}

# Configuration pour la limitation d'utilisation
USAGE_LIMIT_DAYS = 7  # Limite de 7 jours
USAGE_TRACKING = {}  # Stockage en mémoire des utilisateurs

def get_device_fingerprint(request):
    """Génère une empreinte unique pour l'appareil basée sur l'IP et le User-Agent"""
    user_agent = request.headers.get('User-Agent', '')
    ip_address = request.remote_addr or request.environ.get('HTTP_X_FORWARDED_FOR', '127.0.0.1')
    
    # Créer une empreinte unique
    fingerprint_data = f"{ip_address}_{user_agent}"
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()

def is_device_expired(device_id):
    """Vérifie si l'appareil a dépassé la limite d'utilisation"""
    if device_id not in USAGE_TRACKING:
        return False
    
    first_access = datetime.fromisoformat(USAGE_TRACKING[device_id]['first_access'])
    expiration_date = first_access + timedelta(days=USAGE_LIMIT_DAYS)
    
    return datetime.now() > expiration_date

def register_device_access(device_id):
    """Enregistre l'accès d'un appareil"""
    if device_id not in USAGE_TRACKING:
        USAGE_TRACKING[device_id] = {
            'first_access': datetime.now().isoformat(),
            'last_access': datetime.now().isoformat(),
            'access_count': 1
        }
    else:
        USAGE_TRACKING[device_id]['last_access'] = datetime.now().isoformat()
        USAGE_TRACKING[device_id]['access_count'] += 1

def get_remaining_days(device_id):
    """Calcule le nombre de jours restants pour un appareil"""
    if device_id not in USAGE_TRACKING:
        return USAGE_LIMIT_DAYS
    
    first_access = datetime.fromisoformat(USAGE_TRACKING[device_id]['first_access'])
    expiration_date = first_access + timedelta(days=USAGE_LIMIT_DAYS)
    remaining = expiration_date - datetime.now()
    
    return max(0, remaining.days)

def check_device_access():
    """Middleware pour vérifier l'accès de l'appareil"""
    device_id = get_device_fingerprint(request)
    
    if is_device_expired(device_id):
        return render_template(
            "expired.html",
            message="Délai d'utilisation dépassé. Veuillez contacter le concepteur de l'application.",
            contact="Raphaël Niamé (+225 05 06 53 15 22)"
        ), 403
    
    register_device_access(device_id)
    return None

@app.before_request
def before_request():
    # Nettoyer les anciens fichiers audio
    static_folder = app.static_folder or os.path.join(os.path.dirname(__file__), 'static')
    cleanup_old_files(static_folder)
    
    # Vérifier l'accès pour les routes principales (sauf les assets statiques)
    if request.endpoint and request.endpoint not in ['static', 'health']:
        access_check = check_device_access()
        if access_check:
            return access_check

@app.route("/", methods=["GET", "POST"])
def home():
    translation = ""
    error = ""
    target_lang = ""
    extracted_text = ""
    
    # Informations sur l'utilisation
    device_id = get_device_fingerprint(request)
    remaining_days = get_remaining_days(device_id)

    if request.method == "POST":
        text = request.form.get("text")
        target_lang = request.form.get("lang")
        image_file = request.files.get("image")

        if image_file and image_file.filename != '':
            if not TESSERACT_AVAILABLE:
                error = "OCR non disponible sur ce serveur. Veuillez saisir le texte manuellement."
            else:
                try:
                    # Ouvrir l'image avec Pillow
                    img = Image.open(image_file)

                    # Amélioration basique de l'image pour l'OCR
                    img = img.convert('L')  # En niveaux de gris
                    enhancer = ImageEnhance.Contrast(img)
                    img = enhancer.enhance(2)  # Augmenter le contraste
                    img = img.point(lambda x: 0 if x < 140 else 255, '1')  # Binarisation

                    # Extraire le texte avec Tesseract OCR
                    extracted_text = pytesseract.image_to_string(img).strip()

                    if not extracted_text:
                        error = "Aucun texte trouvé dans l'image."
                    else:
                        text = extracted_text  # Utiliser le texte extrait pour la traduction
                except Exception as e:
                    error = f"Erreur lors du traitement de l'image : {str(e)}"

        if not text and not extracted_text:
            error = "Veuillez saisir du texte ou téléverser une image."
        elif not target_lang:
            error = "Veuillez choisir une langue cible."
        elif target_lang not in SUPPORTED_LANGUAGES:
            error = f"Langue cible '{target_lang}' non supportée."
        else:
            cleaned_text = text.strip().lower().rstrip('?')

            if cleaned_text in STATIC_RESPONSES:
                translation = STATIC_RESPONSES[cleaned_text]
            else:
                if not DEEPL_API_KEY:
                    error = "Service de traduction non configuré."
                else:
                    data = {
                        "auth_key": DEEPL_API_KEY,
                        "text": text,
                        "target_lang": target_lang
                    }

                    try:
                        response = requests.post(DEEPL_API_URL, data=data, timeout=10)
                        if response.status_code == 200:
                            result = response.json()
                            translation = result["translations"][0]["text"]
                        else:
                            error = f"Erreur DeepL ({response.status_code}) : {response.text}"
                    except Exception as e:
                        error = f"Erreur réseau : {str(e)}"
    
    return render_template(
        "index.html",
        translation=translation,
        error=error,
        languages=SUPPORTED_LANGUAGES,
        target_lang=target_lang,
        extracted_text=extracted_text,
        ocr_available=TESSERACT_AVAILABLE,
        remaining_days=remaining_days
    )

@app.route("/speak/<path:text>")
def speak(text):
    lang = request.args.get('lang', 'fr')

    supported_languages = list(SUPPORTED_LANGUAGES.keys())
    if lang not in supported_languages:
        return jsonify({"error": "Langue non supportée"}), 400

    try:
        # Assurer que le dossier static existe
        static_folder = app.static_folder or os.path.join(os.path.dirname(__file__), 'static')
        os.makedirs(static_folder, exist_ok=True)
        
        filename = f"translation_{uuid.uuid4()}.mp3"
        filepath = os.path.join(static_folder, filename)

        tts = gTTS(text=text, lang=lang)
        tts.save(filepath)

        return jsonify({"audio_url": f"/static/{filename}"})

    except Exception as e:
        return jsonify({"error": f"Erreur lors de la génération audio : {str(e)}"}), 500

def cleanup_old_files(folder, max_age_seconds=3600):
    try:
        if not os.path.exists(folder):
            return
        now = time.time()
        for filename in os.listdir(folder):
            filepath = os.path.join(folder, filename)
            if os.path.isfile(filepath) and filename.startswith("translation_"):
                if now - os.path.getmtime(filepath) > max_age_seconds:
                    try:
                        os.remove(filepath)
                    except Exception as e:
                        print(f"Erreur lors de la suppression de {filename}: {str(e)}")
    except Exception as e:
        print(f"Erreur lors du nettoyage: {str(e)}")

@app.route("/usage-info")
def usage_info():
    """Route pour afficher les informations d'utilisation (pour le développeur)"""
    device_id = get_device_fingerprint(request)
    
    info = {
        "device_id": device_id[:8] + "...",  # Masquer l'ID complet
        "remaining_days": get_remaining_days(device_id),
        "total_tracked_devices": len(USAGE_TRACKING),
        "is_expired": is_device_expired(device_id)
    }
    
    if device_id in USAGE_TRACKING:
        info["first_access"] = USAGE_TRACKING[device_id]["first_access"]
        info["access_count"] = USAGE_TRACKING[device_id]["access_count"]
    
    return jsonify(info)

@app.errorhandler(404)
def page_not_found(e):
    return render_template("error.html", error="Page introuvable (404)"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("error.html", error="Erreur interne du serveur (500)"), 500

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Une erreur non gérée s'est produite : {str(e)}")
    return render_template("error.html", error=f"Une erreur est survenue : {str(e)}"), 500

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "ocr_available": TESSERACT_AVAILABLE,
        "tracked_devices": len(USAGE_TRACKING)
    }), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)