# 🏠 Liliskane Monitor

Monitoring automatique des projets immobiliers de [liliskane.com](https://www.liliskane.com).

Chaque matin à **9h (heure Maroc)**, le système :
1. Scrape tous les projets du site (7 catégories)
2. Compare avec la baseline (`data/projets_liliskane.csv`)
3. Enregistre un diff JSON dans `logs/`
4. Envoie un **email HTML** si des changements sont détectés
5. Met à jour la baseline et commit/push automatiquement sur Git

---

## 📁 Structure

```
liliskane-monitor/
├── .github/
│   └── workflows/
│       └── daily_check.yml     ← GitHub Actions cron 9h
├── data/
│   └── projets_liliskane.csv   ← Baseline (référence courante)
├── logs/
│   └── diff_YYYY-MM-DD.json    ← Historique des changements
├── scraper.py                  ← Scraping liliskane.com
├── check_changes.py            ← Comparaison + email + mise à jour baseline
├── requirements.txt
└── README.md
```

---

## 🚀 Installation et premier lancement

### 1. Cloner / initialiser le repo

```bash
git clone https://github.com/VOTRE_USER/liliskane-monitor.git
cd liliskane-monitor
pip install -r requirements.txt
```

### 2. Générer la baseline initiale

Placez votre `projets_liliskane.csv` du 2026-04-13 dans `data/` :

```bash
cp /chemin/vers/projets_liliskane.csv data/projets_liliskane.csv
```

Ou générez-en un nouveau :

```bash
python -c "
from scraper import scrape
from check_changes import save_csv
from pathlib import Path
save_csv(scrape(), Path('data/projets_liliskane.csv'))
"
```

### 3. Configurer les GitHub Secrets

Dans votre repo GitHub → **Settings → Secrets and variables → Actions** → **New repository secret** :

| Secret            | Description                                      | Exemple                        |
|-------------------|--------------------------------------------------|--------------------------------|
| `EMAIL_SENDER`    | Adresse Gmail qui envoie l'email                 | `monbot@gmail.com`             |
| `EMAIL_PASSWORD`  | **Mot de passe d'application** Gmail (pas votre MDP habituel) | `xxxx xxxx xxxx xxxx` |
| `EMAIL_RECIPIENT` | Adresse qui reçoit les alertes                   | `vous@example.com`             |

> ⚠️ **Mot de passe d'application Gmail** : activez la validation en 2 étapes sur votre compte Gmail, puis allez dans [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) pour générer un mot de passe dédié à cette app.

### 4. Pousser sur GitHub

```bash
git add .
git commit -m "🚀 Initial setup — baseline $(date +%Y-%m-%d)"
git push
```

L'action se déclenchera automatiquement chaque matin à 9h.  
Vous pouvez aussi la lancer manuellement depuis **Actions → Liliskane Daily Monitor → Run workflow**.

---

## 📧 Format de l'email

L'email HTML reçu en cas de changement contient 3 sections :

- 🟢 **Nouveaux projets** (ajoutés depuis la veille)
- 🔴 **Projets supprimés** (absents du site)
- 🟡 **Projets modifiés** (prix, superficie, date… changés)

---

## 🔧 Lancement manuel local

```bash
# Avec les variables d'environnement
export EMAIL_SENDER="monbot@gmail.com"
export EMAIL_PASSWORD="xxxx xxxx xxxx xxxx"
export EMAIL_RECIPIENT="vous@example.com"

python check_changes.py
```

---

## 📊 Champs surveillés

| Champ          | Source                   |
|----------------|--------------------------|
| Prix (DHS)     | Page de liste            |
| Superficie Min | Page de détail du projet |
| Superficie Max | Page de détail du projet |
| Date de début  | Page de détail (si dispo)|
| Ville          | Page de détail           |
| Catégorie      | Catégorie de navigation  |

---

## 📝 Logs

Chaque exécution produit un fichier `logs/diff_YYYY-MM-DD.json` :

```json
{
  "date": "2026-04-14",
  "nouveaux": [ { "Nom du Projet": "...", "Ville": "...", ... } ],
  "supprimes": [ { ... } ],
  "modifies": [
    {
      "projet": "Amaïa",
      "ville": "Marrakech",
      "url": "https://www.liliskane.com/projet/211/amaia",
      "champs": {
        "Prix (DHS)": { "avant": "1 130 000 DHS", "apres": "1 200 000 DHS" }
      }
    }
  ]
}
```
