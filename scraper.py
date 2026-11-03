import json
import os
import re
from datetime import datetime, timedelta
import cloudscraper
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. CONFIGURATION ---
url = "https://gamewave.fr"
filename = "scrapbingoblitz.json"

now = datetime.now()
date_now_str = now.strftime("%d/%m/%Y @ %H:%M")
heure_actuelle_str = now.strftime("%H:%M")
limite_conservation = now - timedelta(days=5)

# --- 2. INITIALISATION FIREBASE ---
firebase_key_raw = os.environ.get('FIREBASE_KEY')
if not firebase_key_raw:
    raise ValueError("Le secret FIREBASE_KEY est introuvable dans l'environnement.")

if not firebase_admin._apps:
    cred_json = json.loads(firebase_key_raw)
    cred = credentials.Certificate(cred_json)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 3. CHARGEMENT & NETTOYAGE DE L'HISTORIQUE ---
anciens_liens = {}
if os.path.exists(filename):
    try:
        with open(filename, mode="r", encoding="utf-8") as json_file:
            data_chargee = json.load(json_file)
            if isinstance(data_chargee, list):
                for item in data_chargee:
                    if "lienurl" in item:
                        try:
                            date_objet = datetime.strptime(item.get("date", ""), "%d/%m/%Y")
                            if date_objet >= limite_conservation:
                                anciens_liens[item["lienurl"]] = item
                        except:
                            anciens_liens[item["lienurl"]] = item
    except Exception as e:
        print(f"[Attention] Impossible de lire l'historique JSON : {e}")

# --- 4. REQUÊTE HTTP AVEC CLOUDSCRAPER ---
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
try:
    response = scraper.get(url, timeout=15)
    status_code = response.status_code
    html_text = response.text
except Exception as e:
    status_code = 500
    html_text = ""
    print(f"[Erreur] Connexion impossible : {e}")

# --- 5. PARSING ET EXTRACTION DES DONNÉES ---
if status_code == 200:
    soup = BeautifulSoup(html_text, "html.parser")
    json_data = []
    liens_visites_session = set()
    nouveaux_liens_detectes = 0

    # On cible directement le tableau contenant les crédits gratuits
    table = soup.find("table")
    if table:
        # On parcourt toutes les lignes en ignorant l'en-tête (première ligne)
        rows = table.find_all("tr")[1:]
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue
            
            # Extraction et nettoyage de la date et de l'heure (ex: "02/11/2026 à 17:00")
            date_brute = cols[0].get_text().strip()
            match_date = re.search(r'(\d{2}/\d{2}/\d{4})', date_brute)
            if match_date:
                current_date_str = match_date.group(1)
            else:
                current_date_str = now.strftime("%d/%m/%Y")
            
            match_heure = re.search(r'(\d{2}:\d{2})', date_brute)
            heure_liens = match_heure.group(1) if match_heure else "00:00"

            # Vérification de la limite de conservation (Anciens liens ignorés)
            try:
                date_section = datetime.strptime(current_date_str, "%d/%m/%Y")
                if date_section < limite_conservation:
                    continue
            except:
                pass

            # Extraction du type de récompense (ex: "Crédits gratuits")
            type_recompense = cols[1].get_text().strip()

            # Extraction du lien hypertexte dans le bouton
            link_tag = cols[2].find("a", href=True)
            if not link_tag:
                continue
                
            href = link_tag["href"].strip()

            # Filtrage de sécurité contre les réseaux sociaux ou mauvais liens
            if href.startswith("/") or any(p in href.lower() for p in ["twitter.com", "facebook.com", "whatsapp", "pinterest", "reddit.com", "t.me", "telegram.me"]):
                continue

            # Éviter les doublons de session
            if href in liens_visites_session:
                continue
            liens_visites_session.add(href)

            # Structuration de la donnée (Ancien vs Nouveau lien)
            if href in anciens_liens:
                date_premier_scraping_str = anciens_liens[href].get("date_scraping", date_now_str)
                badge_actuel = ""
                try:
                    date_premier_scraping = datetime.strptime(date_premier_scraping_str, "%d/%m/%Y @ %H:%M")
                    if now - date_premier_scraping < timedelta(hours=6):
                        badge_actuel = "NEW"
                except:
                    badge_actuel = anciens_liens[href].get("badge", "")

                json_data.append({
                    "date_scraping": date_premier_scraping_str,
                    "date_scraping1": anciens_liens[href].get("date_scraping1", f"{current_date_str} @ {heure_actuelle_str}"),
                    "date": current_date_str,
                    "heure": anciens_liens[href].get("heure", heure_liens),
                    "recompense": anciens_liens[href].get("recompense", type_recompense),
                    "lienurl": href,
                    "badge": badge_actuel
                })
            else:
                nouveaux_liens_detectes += 1
                date_scraping1_combinee = f"{current_date_str} @ {heure_actuelle_str}"
                json_data.append({
                    "date_scraping": date_now_str,
                    "date_scraping1": date_scraping1_combinee,
                    "date": current_date_str,
                    "heure": heure_liens,
                    "recompense": type_recompense,
                    "lienurl": href,
                    "badge": "NEW"
                })
    else:
        print("[Attention] Aucun tableau de liens trouvé sur la page.")

    # Si aucun lien n'a été trouvé mais que l'historique existe, on préserve l'historique
    if not json_data and anciens_liens:
        json_data = list(anciens_liens.values())

    # Tri par date décroissante
    def extraire_cle_parution(item):
        try:
            return datetime.strptime(item.get("date", ""), "%d/%m/%Y").timestamp()
        except:
            return 0

    json_data.sort(key=extraire_cle_parution, reverse=True)

    # --- 6. SAUVEGARDE JSON ---
    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)

    print(f"[Terminé] Fichier Bingo Blitz {filename} mis à jour ({len(json_data)} liens valides).")
    print(f"[Diagnostic] Nombre de nouveaux liens détectés : {nouveaux_liens_detectes}")

    # --- 7. EXPORTATION NOTIFICATION & ENVOI PUSH VIA FIREBASE ---
    if nouveaux_liens_detectes > 0:
        try:
            from firebase_admin import messaging
            
            db.collection("notifications").add({
                "title": "🔮 Bingo Reward ! 🎁",
                "body": "New free credits have just been added !",
                "nom_du_jeu": "bingo_blitz",
                "created_at": firestore.SERVER_TIMESTAMP
            })
            print("[Firebase] Enregistrement d'historique créé pour Bingo Blitz.")

            message = messaging.Message(
                notification=messaging.Notification(
                    title="🔮 Bingo Reward ! 🎁",
                    body="New free credits have just been added !"
                ),
                topic="bingo_blitz"
            )
            response = messaging.send(message)
            print(f"[Firebase Push] Notification Bingo Blitz envoyée ! (ID: {response})")
        except Exception as e:
            print(f"[Firebase] [Erreur] Impossible d'envoyer l'alerte push direct Bingo Blitz : {e}")
else:
    print(f"[Erreur] Échec de la communication réseau avec Gamewave (Code {status_code}).")
