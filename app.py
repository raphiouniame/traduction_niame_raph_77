import os
import uuid
import time
import requests

from flask import Flask, render_template, request, jsonify
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


@app.route("/", methods=["GET", "POST"])
def home():
    translation = ""
    error = ""
    target_lang = ""

    if request.method == "POST":
        text = request.form.get("text")
        target_lang = request.form.get("lang")

        if not text:
            error = "Veuillez saisir du texte."
        elif not target_lang:
            error = "Veuillez choisir une langue cible."
        elif target_lang not in SUPPORTED_LANGUAGES:
            error = f"Langue cible '{target_lang}' non supportée."
        else:
            # Nettoyage du texte utilisateur
            cleaned_text = text.strip().lower()
            cleaned_text = cleaned_text.rstrip('?')  # Supprime le point d'interrogation en fin de ligne

            # Réponse statique si la question est détectée
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
                    except requests.exceptions.Timeout:
                        error = "Le service de traduction est temporairement indisponible (timeout)."
                    except requests.exceptions.RequestException as e:
                        error = f"Erreur réseau lors de la requête : {str(e)}"
                    except Exception as e:
                        error = f"Erreur inattendue : {str(e)}"

    return render_template(
        "index.html",
        translation=translation,
        error=error,
        languages=SUPPORTED_LANGUAGES,
        target_lang=target_lang
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


@app.before_request
def before_request():
    static_folder = app.static_folder or os.path.join(os.path.dirname(__file__), 'static')
    cleanup_old_files(static_folder)


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


# Route de santé pour Railway
@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)