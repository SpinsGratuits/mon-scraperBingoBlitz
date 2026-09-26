import json
import os
import re
from datetime import datetime, timedelta
import cloudscraper
from bs4 import BeautifulSoup

# --- 1. CONFIGURATION ---
# URL configurée spécifiquement pour la page Bingo Blitz de Mosttechs
url = "https://mosttechs.com/how-to-get-credits-in-bingo-blitz/"
filename = "scrapbingoblitz.json"  # Fichier dédié à Bingo Blitz

# Dictionnaire de traduction des mois pour la conversion en vraies dates Python
mois_en_to_num = {
    "january": "01", "januray": "01", "february": "02", "february ": "02", "march": "03", 
    "april": "04", "may": "05", "june": "06", "july": "07", "august": "08", 
    "september": "09", "october": "10", "november": "11", "december": "12"
}

# --- 2. CHARGEMENT DE L'HISTORIQUE ---
anciens_liens = {}
if os.path.exists(filename):
    try:
        with open(filename, mode="r", encoding="utf-8") as json_file:
            data_chargee = json.load(json_file)
            if isinstance(data_chargee, list):
                for item in data_chargee:
                    if "lienurl" in item:
                        anciens_liens[item["lienurl"]] = item
    except Exception as e:
        print(f"[Attention] Impossible de lire l'historique JSON : {e}")

# Client de contournement anti-bot Cloudflare
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
    
    now = datetime.now()
    date_now_str = now.strftime("%d/%m/%Y @ %H:%M")
    heure_actuelle_str = now.strftime("%H:%M")
    
    # Seuil limite : conservation de l'historique sur 6 jours glissants maximum
    limite_conservation = now - timedelta(days=6)
    
    json_data = []
    
    # Isolement du bloc de contenu pour éviter les menus et liens annexes de Mosttechs
    entry_content = soup.find(class_="entry-content")
    if not entry_content:
        entry_content = soup
        
    # 3. PARCOURS DE LA STRUCTURE TEXTUELLE
    current_date_str = now.strftime("%d/%m/%Y")  # Valeur par défaut
    
    for element in entry_content.find_all(["p", "ul", "ol", "strong"]):
        text = element.get_text().strip().lower()
        
        # Détection d'une ligne de date (Ex: "26 sep 2026", "26 september 2026" ou "26 july 2026")
        match_date = re.search(r'(\d{1,2})\s+([a-z]{3,})\s+(\d{4})', text)
        if match_date:
            jour = match_date.group(1).zfill(2)
            nom_mois = match_date.group(2)
            annee = match_date.group(3)
            
            # Normalisation des abréviations de mois courantes sur le site
            if nom_mois == "sep":
                nom_mois = "september"
            elif nom_mois == "feb":
                nom_mois = "february"
            elif nom_mois == "aug":
                nom_mois = "august"
                
            num_mois = mois_en_to_num.get(nom_mois, "01")
            current_date_str = f"{jour}/{num_mois}/{annee}"
            continue  # Date mise en mémoire, passage aux blocs inférieurs pour isoler les liens
            
        # Extraction des liens hypertextes présents dans le bloc courant
        links = element.find_all("a", href=True)
        for link in links:
            href = link["href"].strip()
            
            # Filtres sanitaires (Exclusion des partages sociaux et structures de navigation interne)
            if href.startswith("/") or "t.me" in href.lower() or "telegram.me" in href.lower():
                continue
            if any(p in href.lower() for p in ["twitter.com", "facebook.com", "whatsapp", "pinterest", "reddit.com"]):
                continue
                
            # Mots-clés d'identification des redirections de récompense Bingo Blitz
            keywords = ["bingoblitz", "playtika", "t.co", "bit.ly"]
            if any(key in href.lower() for key in keywords):
                
                # Validation de la politique d'auto-nettoyage à 6 jours
                try:
                    date_objet = datetime.strptime(current_date_str, "%d/%m/%Y")
                    if date_objet < limite_conservation:
                        continue  # Lien expiré par rapport au calendrier du site, ignoré
                except:
                    pass
                
                # Éviter la duplication si le même lien apparaît deux fois sur la même page
                if any(item["lienurl"] == href for item in json_data):
                    continue
                
                type_recompense = "Credits gratuits"
                
                # --- STRATÉGIE DE RECONSTITUTION ET DE CONSERVATION DES ANCIENNES HEURES ---
                if href in anciens_liens:
                    # ANCIEN LIEN : On réinjecte les anciennes clés historiques sans altération (l'heure ne bouge pas)
                    json_data.append({
                        "date_scraping": anciens_liens[href].get("date_scraping", date_now_str), 
                        "date_scraping1": anciens_liens[href].get("date_scraping1", f"{current_date_str} @ {heure_actuelle_str}"),
                        "date": current_date_str,  
                        "heure": anciens_liens[href].get("heure", "00:00"),
                        "recompense": anciens_liens[href].get("recompense", type_recompense), 
                        "lienurl": href,
                        "badge": "" 
                    })
                else:
                    # NOUVEAU LIEN : On capture la date de parution du site et l'heure courante de sa découverte
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

    # Restauration de l'historique existant en cas de panne temporaire du site distant
    if not json_data and anciens_liens:
        json_data = list(anciens_liens.values())

    # --- 4. TRI DE LA LISTE PAR ORDRE CHRONOLOGIQUE DES PARUTIONS (Le plus récent en haut) ---
    def extraire_cle_parution(item):
        try:
            date_part = datetime.strptime(item.get("date", ""), "%d/%m/%Y")
            return date_part.timestamp()
        except:
            return 0

    # Tri décroissant basé sur l'horodatage du calendrier du site
    json_data.sort(key=extraire_cle_parution, reverse=True)

    # --- 5. ENREGISTREMENT ---
    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"[Terminé] Fichier Bingo Blitz {filename} généré avec succès ({len(json_data)} liens classés chronologiquement).")
            
else:
    print(f"[Erreur] Échec de la communication réseau avec Mosttechs (Code {status_code}).")
