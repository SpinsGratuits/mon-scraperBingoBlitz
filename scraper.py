import json
import os
from datetime import datetime, date
import cloudscraper
from bs4 import BeautifulSoup
import re

# 1. URL du site cible et nom de votre fichier JSON
url = "https://gamewave.fr/bingo-blitz/bingo-blitz-liens-credits-gratuits-free-credits/"
filename = "scrapbingoblitz.json"

# --- CHARGEMENT DE L'HISTORIQUE PRÉCÉDENT ---
# On crée un dictionnaire indexé par l'URL pour retrouver instantanément les données déjà scrapées
anciens_liens = {}
if os.path.exists(filename):
    try:
        with open(filename, mode="r", encoding="utf-8") as json_file:
            data_chargee = json.load(json_file)
            # On s'assure que c'est une liste valide et qu'elle ne contient pas le message "VIDE"
            if isinstance(data_chargee, list):
                for item in data_chargee:
                    if "lienurl" in item:
                        anciens_liens[item["lienurl"]] = item
    except Exception as e:
        print(f"Impossible de lire le fichier JSON précédent (il sera recréé) : {e}")

# Création d'un scraper imitant un navigateur Chrome sur Windows
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})

try:
    response = scraper.get(url)
    status_code = response.status_code
    html_text = response.text
except Exception as e:
    status_code = 500
    html_text = ""
    print(f"Erreur lors du contournement du blocage : {e}")

if status_code == 200:
    soup = BeautifulSoup(html_text, "html.parser")
    
    # Variables temporelles de VOTRE machine pour les NOUVEAUX liens uniquement
    now = datetime.now()
    date_now_str = now.strftime("%d/%m/%Y @ %H:%M")
    date_du_jour_str = now.strftime("%d/%m/%Y")
    heure_actuelle_str = now.strftime("%H:%M")
    
    # Liste finale qui sera réécrite dans le JSON
    json_data = []
    
    # 2. Scanner TOUS les liens hypertextes de la page
    all_links = soup.find_all("a", href=True)
    
    for link in all_links:
        href = link["href"]
        
        # Cibler uniquement les liens officiels de récompense bingo-app-dsa.playtika.com
        if "bingo-app-dsa.playtika.com" in href:
            # Éviter les doublons stricts au sein d'une même session de scraping
            if any(item["lienurl"] == href for item in json_data):
                continue
                
            # --- EXTRACTION DE LA RÉCOMPENSE ---
            parent_text = link.find_parent().get_text(separator=" ").strip() if link.find_parent() else ""
            if len(parent_text) < 15 and link.find_parent().find_parent():
                parent_text = link.find_parent().find_parent().get_text(separator=" ").strip()
            
            clean_text = " ".join(parent_text.split())
            recompense_match = re.search(r'\d+[\s\w]*(?:tours|spins|pieces|coins|tours\s*&\s*pièces)', clean_text, re.IGNORECASE)
            type_recompense = recompense_match.group(0).strip() if recompense_match else "Tours / Pièces"
            type_recompense = re.sub(r'^(?:Cliquez ici pour recevoir|Récupérer)\s*', '', type_recompense, flags=re.IGNORECASE)
            
            # --- LOGIQUE DE DOUBLE-VÉRIFICATION ET CONSERVATION ---
            if href in anciens_liens:
                # DOUBLON DETECTÉ : On conserve EXACTEMENT toutes les anciennes valeurs temporelles
                json_data.append({
                    "date_scraping": anciens_liens[href].get("date_scraping", date_now_str), 
                    "date": anciens_liens[href].get("date", date_du_jour_str), 
                    "heure": anciens_liens[href].get("heure", "00:00"),
                    "recompense": type_recompense, 
                    "lienurl": href,
                    "badge": ""  # Ancien lien, aucun texte additionnel
                })
            else:
                # NOUVEAU LIEN : On applique la date et l'heure de l'exécution actuelle de votre machine
                json_data.append({
                    "date_scraping": date_now_str, 
                    "date": date_du_jour_str, 
                    "heure": heure_actuelle_str,
                    "recompense": type_recompense, 
                    "lienurl": href,
                    "badge": "NEW"  # Texte "new" pour l'affichage sur votre site
                })

    # 3. Écriture du fichier JSON mis à jour
    if not json_data:
        json_data.append({
            "date_scraping": date_now_str,
            "statut": "VIDE",
            "message": "Aucun lien trouvé sur la page. Vérifiez manuellement le site."
        })
        print("Aucun lien extrait.")
    else:
        print(f"Succès total ! {len(json_data)} liens traités (Anciens préservés + Nouveaux ajoutés).")

    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
            
else:
    print(f"Erreur d'accès réseau (Code {status_code}). Le site bloque toujours.")
