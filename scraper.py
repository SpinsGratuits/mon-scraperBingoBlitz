import json
import os
import re
from datetime import datetime, timedelta
import cloudscraper
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. CONFIGURATION ---
url = "https://mosttechs.com/how-to-get-credits-in-bingo-blitz/"
filename = "scrapbingoblitz.json"

mois_en_to_num = {
    "january": "01", "jan": "01", "januray": "01",
    "february": "02", "feb": "02", "february ": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08", "augest": "08",
    "september": "09", "sep": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12"
}

now = datetime.now()
date_now_str = now.strftime("%d/%m/%Y @ %H:%M")
heure_actuelle_str = now.strftime("%H:%M")
limite_conservation = now - timedelta(days=6)

# --- 1B. INITIALISATION FIREBASE ---
firebase_key_raw = os.environ.get('FIREBASE_KEY')
if not firebase_key_raw:
    raise ValueError("Le secret FIREBASE_KEY est introuvable dans l'environnement.")

if not firebase_admin._apps:
    cred_json = json.loads(firebase_key_raw)
    cred = credentials.Certificate(cred_json)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 2. CHARGEMENT & NETTOYAGE DE L'HISTORIQUE ---
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

scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})

try:
    response = scraper.get(url, timeout=15)
    status_code = response.status_code
    html_text = response.text
except Exception as e:
    status_code = 500
    html_text = ""
    print(f"[Erreur] Connexion impossible : {e}")

if status_code == 200:
    soup = BeautifulSoup(html_text, "html.parser")
    json_data = []
    liens_visites_session = set()
    nouveaux_liens_detectes = 0  
    
    entry_content = soup.find(class_="entry-content")
    if not entry_content:
        entry_content = soup
        
    current_date_str = now.strftime("%d/%m/%Y")
    
    for element in entry_content.find_all(["p", "ul", "ol", "strong"]):
        text = element.get_text().strip().lower()
        
        match_date = re.search(r'(\d{1,2})\s+([a-z]{3,})\s+(\d{4})', text)
        if match_date:
            jour = match_date.group(1).zfill(2)
            nom_mois = match_date.group(2).strip()
            annee = match_date.group(3)
                
            num_mois = mois_en_to_num.get(nom_mois, "01")
            current_date_str = f"{jour}/{num_mois}/{annee}"
            continue  
            
        links = element.find_all("a", href=True)
        for link in links:
            href = link["href"].strip()
            
            if href.startswith("/") or "t.me" in href.lower() or "telegram.me" in href.lower():
                continue
            if any(p in href.lower() for p in ["twitter.com", "facebook.com", "whatsapp", "pinterest", "reddit.com"]):
                continue
                
            keywords = ["bingoblitz", "playtika", "t.co", "bit.ly"]
            if any(key in href.lower() for key in keywords):
                
                if href in liens_visites_session:
                    continue
                liens_visites_session.add(href)
                
                type_recompense = "Credits gratuits"
                
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
                        "heure": anciens_liens[href].get("heure", "00:00"),
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
                        "heure": heure_actuelle_str,
                        "recompense": type_recompense, 
                        "lienurl": href,
                        "badge": "NEW" 
                    })

    if not json_data and anciens_liens:
        json_data = list(anciens_liens.values())

    def extraire_cle_parution(item):
        try:
            return datetime.strptime(item.get("date", ""), "%d/%m/%Y").timestamp()
        except:
            return 0

    json_data.sort(key=extraire_cle_parution, reverse=True)

    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"[Terminé] Fichier Bingo Blitz {filename} mis à jour ({len(json_data)} liens valides).")
    print(f"[Diagnostic] Nombre de nouveaux liens détectés : {nouveaux_liens_detectes}")

    # --- 7. EXPORTATION NOTIFICATION & ENVOI PUSH DIRECT ---
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
    print(f"[Erreur] Échec de la communication réseau avec Mosttechs (Code {status_code}).")
