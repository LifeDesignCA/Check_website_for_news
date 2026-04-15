"""
scraper.py — Scrape multi-sources : Liliskane, Al Omrane, Groupe Addoha
Retourne une liste unifiée de dicts prêts à être comparés / exportés en CSV.

Sources :
  • Liliskane     → https://www.liliskane.com          (7 catégories)
  • Al Omrane     → https://www.alomrane.gov.ma         (50 pages, ~600 projets)
  • Groupe Addoha → https://www.groupeaddoha.com        (pagination à adapter)
"""

import re
import time

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
# ── Constantes communes ───────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# Colonnes du CSV — partagées par tous les scrapers
# ⚠️  Si vous avez un ancien CSV sans "Source" / "Statut", check_changes.py
#     les ajoutera automatiquement avec des valeurs par défaut.
FIELDNAMES = [
    "Source",
    "Nom du Projet",
    "Ville",
    "Catégorie",
    "Statut",
    "Prix (DHS)",
    "Superficie Min",
    "Superficie Max",
    "Date de début",
    "Lien",
]


# ══════════════════════════════════════════════════════════════════════════════
#  SCRAPER 1 — LILISKANE
# ══════════════════════════════════════════════════════════════════════════════

_LILISKANE_BASE = "https://www.liliskane.com"

_LILISKANE_CATEGORIES = [
    ("/projet/type/1/projets-economiques",    "Économique"),
    ("/projet/type/2/projets-moyen-standing", "Moyen Standing"),
    ("/projet/type/8/projets-haut-standing",  "Haut Standing"),
    ("/projet/type/3/lots-de-terrains",        "Lots de terrains"),
    ("/projet/type/4/locaux-commerciaux",      "Locaux commerciaux"),
    ("/projet/type/6/plateaux-de-bureaux",     "Plateaux de bureaux"),
    ("/projet/type/7/equipements-sociaux",     "Équipements sociaux"),
]

_VILLES_LILISKANE = [
    "Al Houceima", "Kénitra", "Nouacer", "Agadir", "Had Soualem",
    "Temara", "Casablanca", "Marrakech", "Essaouira", "Nador",
    "Mohammedia", "Tanger", "Sala Al Jadida", "Rabat", "K'sar El Kebir",
    "Sidi Rahal",
]


def _lili_separer_nom_ville(texte: str) -> tuple[str, str]:
    for ville in _VILLES_LILISKANE:
        if texte.endswith(ville):
            return texte[: -len(ville)].strip(), ville
    parts = texte.rsplit(" ", 1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (texte, "N/A")


def _lili_extraire_prix(container) -> str:
    for node in container.find_all(string=True):
        txt = node.strip()
        if re.search(r"\d", txt) and "DHS" in txt.upper():
            return re.sub(r"\s+", " ", txt)
    full = container.get_text(separator=" ")
    m = re.search(r"([\d][\d\s]*DHS)", full, re.IGNORECASE)
    return re.sub(r"\s+", " ", m.group(1).strip()) if m else "N/A"


def _lili_scrape_detail(url: str) -> dict:
    data = {
        "nom_propre":     "",
        "ville_propre":   "",
        "superficie_min": "N/A",
        "superficie_max": "N/A",
        "date_debut":     "N/A",
    }
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.content, "html.parser")
        text = soup.get_text(separator="\n")

        h1 = soup.find("h1")
        if h1:
            data["nom_propre"] = h1.get_text(strip=True)

        for ville in _VILLES_LILISKANE:
            if ville in text:
                data["ville_propre"] = ville
                break

        for field, pattern in [
            ("superficie_min", r"Superficie min\s*[:\-]\s*([\d\s]+m²)"),
            ("superficie_max", r"Superficie max\s*[:\-]\s*([\d\s]+m²)"),
            ("date_debut",     r"[Dd]ate de d[ée]but\s*[:\-]\s*([^\n]+)"),
        ]:
            m = re.search(pattern, text)
            if m:
                data[field] = re.sub(r"\s+", " ", m.group(1)).strip()

    except Exception as e:
        print(f"    ⚠  Liliskane détail {url} : {e}")
    return data


def scrape_liliskane() -> list[dict]:
    """Scrape tous les projets de liliskane.com."""
    all_projects = []
    seen_urls    = set()

    print("\n" + "─" * 50)
    print("🏠  SOURCE : Liliskane")
    print("─" * 50)

    for cat_path, cat_nom in _LILISKANE_CATEGORIES:
        cat_url = _LILISKANE_BASE + cat_path
        print(f"\n  📂  {cat_nom}")
        try:
            resp = requests.get(cat_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")
        except Exception as e:
            print(f"     ⚠  Impossible d'accéder : {e}")
            continue

        containers = [
            a for a in soup.find_all("a", href=re.compile(r"/projet/\d+/"))
            if a.find("h3")
        ]
        if not containers:
            for div in soup.find_all("div", class_="home_project"):
                a = div.find("a", href=re.compile(r"/projet/\d+/"))
                if a:
                    containers.append(div)

        print(f"     → {len(containers)} projets")

        for container in containers:
            href = (container.get("href", "")
                    if container.name == "a"
                    else (container.find("a", href=re.compile(r"/projet/\d+/")) or {}).get("href", ""))
            if not href:
                continue
            detail_url = href if href.startswith("http") else _LILISKANE_BASE + href

            if detail_url in seen_urls:
                continue
            seen_urls.add(detail_url)

            h3 = container.find("h3")
            nom_liste, ville_liste = _lili_separer_nom_ville(
                h3.get_text(strip=True) if h3 else ""
            )
            prix_liste = _lili_extraire_prix(container)

            print(f"     ✔  {nom_liste} | {ville_liste} | {prix_liste}")

            time.sleep(0.6)
            detail = _lili_scrape_detail(detail_url)

            all_projects.append({
                "Source":         "Liliskane",
                "Nom du Projet":  detail["nom_propre"]   or nom_liste,
                "Ville":          detail["ville_propre"] or ville_liste,
                "Catégorie":      cat_nom,
                "Statut":         "N/A",
                "Prix (DHS)":     prix_liste,
                "Superficie Min": detail["superficie_min"],
                "Superficie Max": detail["superficie_max"],
                "Date de début":  detail["date_debut"],
                "Lien":           detail_url,
            })

    print(f"\n  ✅  Liliskane : {len(all_projects)} projets récupérés")
    return all_projects


# ══════════════════════════════════════════════════════════════════════════════
#  SCRAPER 2 — AL OMRANE
# ══════════════════════════════════════════════════════════════════════════════

# _OMRANE_BASE      = "https://www.alomrane.gov.ma"
# _OMRANE_LIST_URL  = _OMRANE_BASE + "/Nos-produits/Projets"
# _OMRANE_MAX_PAGES = 50   # le site affiche 600 projets ÷ 12/page = 50 pages


# def _omrane_parse_listing_page(soup: BeautifulSoup, seen_urls: set) -> list[dict]:
#     """
#     Extrait les cartes-projets d'une page de liste Al Omrane.

#     Structure HTML observée (rendu) :
#       [Badge optionnel : Nouveau / Aide au logement / Promotion / Remise]
#       [img]
#       VILLE
#       <h3>NOM DU PROJET</h3>
#       description courte...
#       <a href="/Notre-reseau/...">Plus d'infos</a>
#     """
#     projects = []

#     # Tous les liens "Plus d'infos" qui pointent vers une page de projet
#     info_links = soup.find_all(
#         "a",
#         href=re.compile(r"/Notre-reseau/", re.IGNORECASE),
#         string=re.compile(r"Plus d'infos", re.IGNORECASE),
#     )

#     for link in info_links:
#         href = link.get("href", "")
#         if not href:
#             continue
#         detail_url = href if href.startswith("http") else _OMRANE_BASE + href

#         if detail_url in seen_urls:
#             continue
#         seen_urls.add(detail_url)

#         # Remonter au conteneur parent de la carte
#         card = link.parent
#         for _ in range(5):           # max 5 niveaux vers le haut
#             if card is None:
#                 break
#             h3 = card.find("h3")
#             if h3:
#                 break
#             card = card.parent

#         if card is None:
#             continue

#         # Nom du projet
#         h3 = card.find("h3")
#         nom = h3.get_text(strip=True) if h3 else "N/A"

#         # Ville — texte brut précédant le h3 dans le conteneur
#         ville = "N/A"
#         if h3:
#             for node in h3.previous_siblings:
#                 txt = ""
#                 if hasattr(node, "get_text"):
#                     txt = node.get_text(separator=" ", strip=True)
#                 elif isinstance(node, str):
#                     txt = node.strip()
#                 # On exclut les balises images et les badges longs
#                 if txt and len(txt) < 60 and not re.search(r"[<>]", txt):
#                     ville = txt
#                     break

#         # Badge / Catégorie — chercher un span ou div badge dans la carte
#         badge = "N/A"
#         badge_patterns = [
#             "aide au logement", "nouveau", "promotion", "remise",
#         ]
#         card_text = card.get_text(separator=" ").lower()
#         for bp in badge_patterns:
#             if bp in card_text:
#                 badge = bp.title()
#                 break

#         print(f"     ✔  {nom} | {ville} | {badge}")

#         projects.append({
#             "Source":         "Al Omrane",
#             "Nom du Projet":  nom,
#             "Ville":          ville,
#             "Catégorie":      badge,
#             "Statut":         "N/A",   # récupéré en détail si besoin
#             "Prix (DHS)":     "N/A",   # Al Omrane ne publie pas les prix en ligne
#             "Superficie Min": "N/A",
#             "Superficie Max": "N/A",
#             "Date de début":  "N/A",
#             "Lien":           detail_url,
#         })

#     return projects


# def _omrane_scrape_detail(url: str) -> dict:
#     """
#     Enrichit un projet Al Omrane avec les infos de sa page détail :
#       - Statut   (En cours / Livrable / Titres fonciers disponibles)
#       - Catégorie / badge précis
#       - Date de début si mentionnée dans la description
#     """
#     data = {"statut": "N/A", "date_debut": "N/A", "categorie": "N/A"}
#     try:
#         resp = requests.get(url, headers=HEADERS, timeout=15)
#         soup = BeautifulSoup(resp.content, "html.parser")
#         text = soup.get_text(separator="\n")

#         # Statut
#         for statut in ["En cours de travaux", "En cours", "Livrable",
#                        "Titres fonciers disponibles"]:
#             if statut.lower() in text.lower():
#                 data["statut"] = statut
#                 break

#         # Badge/catégorie (chercher dans les spans visibles)
#         for badge_kw in ["Aide au logement", "Nouveau", "Promotion", "Remise"]:
#             if badge_kw.lower() in text.lower():
#                 data["categorie"] = badge_kw
#                 break

#         # Date de début / lancement
#         for pat in [
#             r"[Dd]ate de lancement[^:]*[:\-]\s*([^\n]{4,30})",
#             r"[Dd]ate de d[ée]but[^:]*[:\-]\s*([^\n]{4,30})",
#             r"à partir du\s+([^\n]{4,25})",
#         ]:
#             m = re.search(pat, text)
#             if m:
#                 data["date_debut"] = re.sub(r"\s+", " ", m.group(1)).strip()
#                 break

#     except Exception as e:
#         print(f"    ⚠  Al Omrane détail {url} : {e}")
#     return data


# def scrape_alomrane(fetch_details: bool = False) -> list[dict]:
#     """
#     Scrape tous les projets d'alomrane.gov.ma (600 projets / 50 pages).

#     Args:
#         fetch_details: Si True, visite chaque page détail pour enrichir
#                        Statut, Catégorie précise et Date. Plus lent (~10 min).
#                        Si False (défaut), listing seulement — rapide (~30 sec).
#     """
#     all_projects = []
#     seen_urls    = set()

#     print("\n" + "─" * 50)
#     print("🏗️   SOURCE : Al Omrane")
#     print("─" * 50)

#     for page in range(1, _OMRANE_MAX_PAGES + 1):
#         url = f"{_OMRANE_LIST_URL}?pagelist={page}"
#         print(f"\n  📄  Page {page}/{_OMRANE_MAX_PAGES}  →  {url}")
#         try:
#             resp = requests.get(url, headers=HEADERS, timeout=20)
#             if resp.status_code != 200:
#                 print(f"     ⚠  HTTP {resp.status_code} — arrêt de la pagination")
#                 break
#             soup = BeautifulSoup(resp.content, "html.parser")
#         except Exception as e:
#             print(f"     ⚠  Erreur réseau page {page} : {e}")
#             time.sleep(2)
#             continue

#         page_projects = _omrane_parse_listing_page(soup, seen_urls)

#         if not page_projects:
#             print(f"     ⚠  Aucun projet trouvé — fin de pagination à la page {page}")
#             break

#         # Enrichissement optionnel via la page détail
#         if fetch_details:
#             for proj in page_projects:
#                 time.sleep(0.4)
#                 detail = _omrane_scrape_detail(proj["Lien"])
#                 if detail["statut"] != "N/A":
#                     proj["Statut"] = detail["statut"]
#                 if detail["categorie"] != "N/A":
#                     proj["Catégorie"] = detail["categorie"]
#                 if detail["date_debut"] != "N/A":
#                     proj["Date de début"] = detail["date_debut"]

#         all_projects.extend(page_projects)

#         # Pause courtoise entre les pages
#         time.sleep(0.8)

#     print(f"\n  ✅  Al Omrane : {len(all_projects)} projets récupérés")
#     return all_projects


# ══════════════════════════════════════════════════════════════════════════════
#  SCRAPER 3 — GROUPE ADDOHA
# ══════════════════════════════════════════════════════════════════════════════
#
#  ⚠️  NOTE : Le site groupeaddoha.com était inaccessible lors de l'analyse
#  (erreur serveur). Ce scraper est fonctionnel mais les sélecteurs HTML
#  devront peut-être être ajustés une fois le site accessible.
#
#  Structure probable (à vérifier) :
#    Liste : https://www.groupeaddoha.com/projets  (ou /nos-projets)
#    Cartes avec : nom, ville, type de bien, lien détail
#    Détail : prix, superficie, statut selon le projet
#
# ══════════════════════════════════════════════════════════════════════════════

# --- CONFIGURATION ---
# Ces headers simulent un humain pour éviter le blocage 403
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,ar;q=0.7",
}

_ADDOHA_BASE = "https://www.groupeaddoha.com/?page_id=7"

def _addoha_find_listing_url():
    try:
        r = requests.get(_ADDOHA_BASE, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            print(f"      ✔ URL Addoha fonctionnelle trouvée : {_ADDOHA_BASE}")
            return r.text
    except Exception as e:
        print(f"Erreur lors de l'accès à la page liste : {e}")
    return None

def _extract_project_links(html):
    """Trouve tous les liens projet"""
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    # On cherche les liens de type ?projet=X
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "?projet=" in href:
            links.add(urljoin(_ADDOHA_BASE, href))
    return list(links)

def _parse_addoha_project(url):
    """Scrape une page projet avec une détection par score pour la ville"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.content, "html.parser")
        
        # On cible le corps de la page pour éviter le menu/footer
        content_area = soup.find("main") or soup.find("article") or soup.find("div", {"id": "content"}) or soup
        text_full = content_area.get_text(" ", strip=True)

        # NOM DU PROJET (H1 est le plus fiable)
        title = soup.find("h1")
        nom = title.get_text(strip=True) if title else "Projet Addoha"

        # --- VILLE (Stratégie par score pour éviter les erreurs) ---
        ville = "N/A"
        ville_scores = {}
        villes_dict = {
            "Marrakech": ["مراكش", "Marrakech"],
            "Oujda": ["وجدة", "Oujda"],
            "Tanger": ["طنجة", "Tanger"],
            "Rabat": ["الرباط", "Rabat"],
            "Agadir": ["أكادير", "Agadir"],
            "Fès": ["فاس", "Fès"],
            "Tétouan": ["تطوان", "Tétouan"],
            "Meknès": ["مكناس", "Meknès"],
            "Salé": ["سلا", "Salé"],
            "Casablanca": ["الدار البيضاء", "Casablanca"],
        }

        # On cherche d'abord dans le titre du projet (très fiable)
        nom_lower = nom.lower()
        for fr, variations in villes_dict.items():
            if any(var.lower() in nom_lower or var in nom for var in variations):
                ville = fr
                break

        # Si pas trouvé dans le titre, on compte les points dans le texte
        if ville == "N/A":
            text_lower = text_full.lower()
            for fr, variations in villes_dict.items():
                score = 0
                for var in variations:
                    score += text_lower.count(var.lower())
                if score > 0:
                    ville_scores[fr] = score
            
            if ville_scores:
                # La ville qui apparaît le plus gagne
                ville = max(ville_scores, key=ville_scores.get)

        # --- PRIX ---
        prix = "N/A"
        # Cherche les chiffres suivis de درهم ou DH
        prix_match = re.search(r"([\d\.\s]{3,})\s*(درهم|DH|DHS)", text_full, re.IGNORECASE)
        if prix_match:
            # Nettoyage : on enlève les points et espaces pour avoir un nombre pur
            prix = prix_match.group(1).replace(".", "").replace(" ", "").strip()

        return {
            "Source": "Addoha",
            "Nom du Projet": nom,
            "Ville": ville,
            "Catégorie": "N/A",
            "Statut": "N/A",
            "Prix (DHS)": prix,
            "Superficie Min": "N/A",
            "Superficie Max": "N/A",
            "Date de début": "N/A",
            "Lien": url,
        }

    except Exception as e:
        print(f"Erreur sur {url}: {e}")
        return None

def scrape_addoha():
    all_projects = []
    print("\n" + "─" * 50)
    print("🏢  SOURCE : Groupe Addoha")
    print("─" * 50)

    html = _addoha_find_listing_url()
    if not html:
        print("⚠ Addoha inaccessible")
        return []

    project_links = _extract_project_links(html)
    print(f"🔍 {len(project_links)} projets détectés sur la page liste...")

    for link in project_links:
        project = _parse_addoha_project(link)
        if project:
            all_projects.append(project)
            print(f"      ✔ {project['Nom du Projet'][:25]} | {project['Ville']} | {project['Prix (DHS)']} DH")
        
        # Pause pour ne pas être banni par le serveur
        time.sleep(1)

    print(f"\n  ✅ Addoha : {len(all_projects)} projets récupérés")
    return all_projects
# ══════════════════════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE UNIFIÉ
# ══════════════════════════════════════════════════════════════════════════════

def scrape(
    include_liliskane: bool = True,
    include_alomrane:  bool = True,
    include_addoha:    bool = True,
    alomrane_details:  bool = False,
) -> list[dict]:
    """
    Lance tous les scrapers activés et retourne une liste unifiée.

    Args:
        include_liliskane : scraper Liliskane (défaut True)
        include_alomrane  : scraper Al Omrane (défaut True)
        include_addoha    : scraper Addoha    (défaut True)
        alomrane_details  : visiter les pages détail Al Omrane (défaut False,
                            ~10 min supplémentaires pour ~600 projets)

    Returns:
        Liste de dicts avec les colonnes FIELDNAMES.
    """
    all_projects: list[dict] = []

    if include_liliskane:
        all_projects.extend(scrape_liliskane())

    # if include_alomrane:
    #     all_projects.extend(scrape_alomrane(fetch_details=alomrane_details))

    if include_addoha:
        all_projects.extend(scrape_addoha())

    print(f"\n{'=' * 50}")
    print(f"📦  TOTAL : {len(all_projects)} projets toutes sources confondues")
    print(f"{'=' * 50}\n")

    return all_projects
