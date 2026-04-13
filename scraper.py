"""
scraper.py — Scrape tous les projets de liliskane.com
Retourne une liste de dicts prêts à être comparés / exportés en CSV.
"""

import requests
from bs4 import BeautifulSoup
import re
import time

BASE_URL = "https://www.liliskane.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

CATEGORIES = [
    ("/projet/type/1/projets-economiques",    "Économique"),
    ("/projet/type/2/projets-moyen-standing", "Moyen Standing"),
    ("/projet/type/8/projets-haut-standing",  "Haut Standing"),
    ("/projet/type/3/lots-de-terrains",        "Lots de terrains"),
    ("/projet/type/4/locaux-commerciaux",      "Locaux commerciaux"),
    ("/projet/type/6/plateaux-de-bureaux",     "Plateaux de bureaux"),
    ("/projet/type/7/equipements-sociaux",     "Équipements sociaux"),
]

VILLES = [
    "Al Houceima", "Kénitra", "Nouacer", "Agadir", "Had Soualem",
    "Temara", "Casablanca", "Marrakech", "Essaouira", "Nador",
    "Mohammedia", "Tanger", "Sala Al Jadida", "Rabat", "K'sar El Kebir",
    "Sidi Rahal",
]

FIELDNAMES = [
    "Nom du Projet", "Ville", "Catégorie",
    "Prix (DHS)", "Superficie Min", "Superficie Max",
    "Date de début", "Lien",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _separer_nom_ville(texte: str) -> tuple[str, str]:
    for ville in VILLES:
        if texte.endswith(ville):
            return texte[: -len(ville)].strip(), ville
    parts = texte.rsplit(" ", 1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (texte, "N/A")


def _extraire_prix(container) -> str:
    for node in container.find_all(string=True):
        txt = node.strip()
        if re.search(r"\d", txt) and "DHS" in txt.upper():
            return re.sub(r"\s+", " ", txt)
    full = container.get_text(separator=" ")
    m = re.search(r"([\d][\d\s]*DHS)", full, re.IGNORECASE)
    return re.sub(r"\s+", " ", m.group(1).strip()) if m else "N/A"


def _scrape_detail(url: str) -> dict:
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

        for ville in VILLES:
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
        print(f"    ⚠  Détail {url} : {e}")
    return data


# ── Scraping principal ────────────────────────────────────────────────────────

def scrape() -> list[dict]:
    """
    Lance le scraping complet et retourne une liste de projets (dicts).
    Chaque dict utilise les clés de FIELDNAMES.
    """
    all_projects = []
    seen_urls    = set()

    for cat_path, cat_nom in CATEGORIES:
        cat_url = BASE_URL + cat_path
        print(f"\n📂  {cat_nom}")
        try:
            resp = requests.get(cat_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")
        except Exception as e:
            print(f"   ⚠  Impossible d'accéder : {e}")
            continue

        # Cartes : <a href="/projet/ID/slug"> qui contiennent un <h3>
        containers = [
            a for a in soup.find_all("a", href=re.compile(r"/projet/\d+/"))
            if a.find("h3")
        ]
        if not containers:
            for div in soup.find_all("div", class_="home_project"):
                a = div.find("a", href=re.compile(r"/projet/\d+/"))
                if a:
                    containers.append(div)

        print(f"   → {len(containers)} projets")

        for container in containers:
            href = (container.get("href", "")
                    if container.name == "a"
                    else (container.find("a", href=re.compile(r"/projet/\d+/")) or {}).get("href", ""))
            if not href:
                continue
            detail_url = href if href.startswith("http") else BASE_URL + href

            if detail_url in seen_urls:
                continue
            seen_urls.add(detail_url)

            h3 = container.find("h3")
            nom_liste, ville_liste = _separer_nom_ville(h3.get_text(strip=True) if h3 else "")
            prix_liste = _extraire_prix(container)

            print(f"   ✔  {nom_liste} | {ville_liste} | {prix_liste}")

            time.sleep(0.6)
            detail = _scrape_detail(detail_url)

            all_projects.append({
                "Nom du Projet":  detail["nom_propre"]   or nom_liste,
                "Ville":          detail["ville_propre"] or ville_liste,
                "Catégorie":      cat_nom,
                "Prix (DHS)":     prix_liste,
                "Superficie Min": detail["superficie_min"],
                "Superficie Max": detail["superficie_max"],
                "Date de début":  detail["date_debut"],
                "Lien":           detail_url,
            })

    return all_projects
