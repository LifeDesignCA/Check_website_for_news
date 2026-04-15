"""
check_changes.py
────────────────
1. Scrape les sites : Liliskane, Al Omrane, Groupe Addoha
2. Compare avec la baseline (data/projets_multi.csv)
3. Si des changements : enregistre un diff JSON dans logs/, envoie un email HTML
4. Sauvegarde le nouveau CSV comme nouvelle baseline

Variables d'environnement requises (GitHub Secrets ou .env local) :
  EMAIL_SENDER      ex: moncompte@gmail.com
  EMAIL_PASSWORD    mot de passe d'application Gmail (pas le MDP habituel)
  EMAIL_RECIPIENT   ex: moi@example.com (plusieurs : séparés par virgule)
  SMTP_HOST         (optionnel, défaut: smtp.gmail.com)
  SMTP_PORT         (optionnel, défaut: 587)
"""

import csv
import json
import os
import smtplib
import sys
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from scraper import scrape, FIELDNAMES

# ── Chemins ──────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent
DATA_FILE = ROOT / "data" / "projets_multi.csv"   # renommé pour multi-sources
LOGS_DIR  = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# ── Champs surveillés pour détecter des modifications ────────────────────────
# "Source" et "Lien" sont des clés d'identité — pas des champs de changement.
CHAMPS_SURVEILLES = [
    "Nom du Projet",
    "Ville",
    "Catégorie",
    "Statut",
    "Prix (DHS)",
    "Superficie Min",
    "Superficie Max",
    "Date de début",
]


# ── CSV helpers ───────────────────────────────────────────────────────────────

def load_csv(path: Path) -> dict[str, dict]:
    """
    Charge le CSV et retourne un dict indexé par l'URL (clé unique).
    Compatibilité ascendante : les anciens CSV sans "Source" ou "Statut"
    reçoivent des valeurs par défaut.
    """
    if not path.exists():
        # Chercher aussi l'ancien nom liliskane-only
        old_path = path.parent / "projets_liliskane.csv"
        if old_path.exists():
            print(f"ℹ️   Migration : ancien fichier '{old_path.name}' détecté → chargé comme baseline.")
            path = old_path
        else:
            return {}

    result = {}
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            # Ajouter les nouveaux champs absents des anciens CSV
            row.setdefault("Source", "Liliskane")
            row.setdefault("Statut", "N/A")
            url = row.get("Lien", "").strip()
            if url:
                result[url] = row
    return result


def save_csv(data: list[dict], path: Path) -> None:
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, delimiter=";",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    print(f"✅  Baseline mise à jour → {path}")


# ── Comparaison ───────────────────────────────────────────────────────────────

def comparer(anciens: dict, nouveaux: list[dict]) -> dict:
    """
    Retourne un dict avec trois clés :
      - 'nouveaux'  : projets absents de la baseline
      - 'supprimes' : projets présents dans baseline mais absents du scrape
      - 'modifies'  : projets dont au moins un champ surveillé a changé
    """
    new_map      = {p["Lien"]: p for p in nouveaux}
    anciens_ids  = set(anciens.keys())
    nouveaux_ids = set(new_map.keys())

    ajouts      = [new_map[k] for k in nouveaux_ids - anciens_ids]
    suppressions = [anciens[k] for k in anciens_ids - nouveaux_ids]

    modifications = []
    for url in anciens_ids & nouveaux_ids:
        ancien  = anciens[url]
        nouveau = new_map[url]
        champs_changes = {
            champ: {
                "avant": ancien.get(champ, ""),
                "apres": nouveau.get(champ, ""),
            }
            for champ in CHAMPS_SURVEILLES
            if ancien.get(champ, "").strip() != nouveau.get(champ, "").strip()
        }
        if champs_changes:
            modifications.append({
                "source":  nouveau.get("Source", "?"),
                "projet":  nouveau["Nom du Projet"],
                "ville":   nouveau["Ville"],
                "url":     url,
                "champs":  champs_changes,
            })

    return {
        "date":      date.today().isoformat(),
        "nouveaux":  ajouts,
        "supprimes": suppressions,
        "modifies":  modifications,
    }


def a_des_changements(diff: dict) -> bool:
    return bool(diff["nouveaux"] or diff["supprimes"] or diff["modifies"])


# ── Email ─────────────────────────────────────────────────────────────────────

_SOURCES_LABELS = {
    "Liliskane": "🏠",
    "Al Omrane": "🏗️",
    "Addoha":    "🏢",
}


def _source_badge(projet: dict) -> str:
    src = projet.get("Source", "?")
    icon = _SOURCES_LABELS.get(src, "📍")
    return f"<span style='font-size:10px;background:#ecf0f1;padding:2px 6px;border-radius:3px'>{icon} {src}</span>"


def _build_html(diff: dict) -> str:
    today = diff["date"]
    n_add = len(diff["nouveaux"])
    n_del = len(diff["supprimes"])
    n_mod = len(diff["modifies"])

    style_table = "border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:13px"
    style_th    = "background:#2c3e50;color:#fff;padding:8px 10px;text-align:left"

    # ── Tableau Nouveaux ─────────────────────────────────────────────────────
    rows_add = "".join(
        f"<tr>"
        f"<td style='padding:7px 10px;border-bottom:1px solid #eee'>{_source_badge(p)}</td>"
        f"<td style='padding:7px 10px;border-bottom:1px solid #eee'>"
        f"<a href='{p['Lien']}'>{p['Nom du Projet']}</a></td>"
        f"<td style='padding:7px 10px;border-bottom:1px solid #eee'>{p['Ville']}</td>"
        f"<td style='padding:7px 10px;border-bottom:1px solid #eee'>{p.get('Catégorie','')}</td>"
        f"<td style='padding:7px 10px;border-bottom:1px solid #eee'>{p.get('Prix (DHS)','')}</td>"
        f"</tr>"
        for p in diff["nouveaux"]
    )

    # ── Tableau Supprimés ────────────────────────────────────────────────────
    rows_del = "".join(
        f"<tr>"
        f"<td style='padding:7px 10px;border-bottom:1px solid #eee'>{_source_badge(p)}</td>"
        f"<td style='padding:7px 10px;border-bottom:1px solid #eee'>"
        f"<a href='{p['Lien']}'>{p['Nom du Projet']}</a></td>"
        f"<td style='padding:7px 10px;border-bottom:1px solid #eee'>{p['Ville']}</td>"
        f"</tr>"
        for p in diff["supprimes"]
    )

    # ── Tableau Modifiés ─────────────────────────────────────────────────────
    rows_mod = ""
    for m in diff["modifies"]:
        src_icon = _SOURCES_LABELS.get(m.get("source", ""), "📍")
        champs_html = "".join(
            f"<li><b>{c}</b> : "
            f"<span style='color:#c0392b'>{v['avant'] or '—'}</span>"
            f" → <span style='color:#27ae60'>{v['apres'] or '—'}</span></li>"
            for c, v in m["champs"].items()
        )
        rows_mod += (
            f"<tr>"
            f"<td style='padding:7px 10px;border-bottom:1px solid #eee'>"
            f"{src_icon} {m.get('source','?')}</td>"
            f"<td style='padding:7px 10px;border-bottom:1px solid #eee'>"
            f"<a href='{m['url']}'>{m['projet']}</a></td>"
            f"<td style='padding:7px 10px;border-bottom:1px solid #eee'>{m['ville']}</td>"
            f"<td style='padding:7px 10px;border-bottom:1px solid #eee'>"
            f"<ul style='margin:0;padding-left:16px'>{champs_html}</ul></td>"
            f"</tr>"
        )

    section_nouveaux = f"""
    <h3 style="color:#27ae60">🟢 Nouveaux projets ({n_add})</h3>
    <table style="{style_table}">
      <tr>
        <th style="{style_th}">Source</th>
        <th style="{style_th}">Nom</th>
        <th style="{style_th}">Ville</th>
        <th style="{style_th}">Catégorie</th>
        <th style="{style_th}">Prix</th>
      </tr>
      {rows_add or '<tr><td colspan="5" style="padding:8px">—</td></tr>'}
    </table>""" if n_add else ""

    section_supprimes = f"""
    <h3 style="color:#c0392b">🔴 Projets supprimés ({n_del})</h3>
    <table style="{style_table}">
      <tr>
        <th style="{style_th}">Source</th>
        <th style="{style_th}">Nom</th>
        <th style="{style_th}">Ville</th>
      </tr>
      {rows_del or '<tr><td colspan="3" style="padding:8px">—</td></tr>'}
    </table>""" if n_del else ""

    section_modifies = f"""
    <h3 style="color:#e67e22">🟡 Projets modifiés ({n_mod})</h3>
    <table style="{style_table}">
      <tr>
        <th style="{style_th}">Source</th>
        <th style="{style_th}">Nom</th>
        <th style="{style_th}">Ville</th>
        <th style="{style_th}">Changements</th>
      </tr>
      {rows_mod or '<tr><td colspan="4" style="padding:8px">—</td></tr>'}
    </table>""" if n_mod else ""

    sources_actives = ", ".join(
        f"{icon} {src}" for src, icon in _SOURCES_LABELS.items()
    )

    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#222;max-width:900px;margin:auto">
      <h2 style="background:#2c3e50;color:#fff;padding:14px 18px;border-radius:4px">
        📊 Monitoring Immobilier Maroc — Rapport du {today}
      </h2>
      <p>
        Bonjour,<br><br>
        Le monitoring multi-sources ({sources_actives}) a détecté :
        <b>{n_add} nouveau(x)</b>,
        <b>{n_del} supprimé(s)</b>,
        <b>{n_mod} modifié(s)</b>.
      </p>
      {section_nouveaux}
      {section_supprimes}
      {section_modifies}
      <hr>
      <p style="font-size:11px;color:#888">
        Email généré automatiquement · {datetime.now().strftime("%Y-%m-%d %H:%M")}
      </p>
    </body></html>
    """


def envoyer_email(diff: dict) -> None:
    sender    = os.environ["EMAIL_SENDER"]
    password  = os.environ["EMAIL_PASSWORD"]
    raw_recip = os.environ.get("EMAIL_RECIPIENT", "")
    recipients = [r.strip() for r in raw_recip.split(",") if r.strip()]

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", 587))

    n = len(diff["nouveaux"]) + len(diff["supprimes"]) + len(diff["modifies"])
    subject = f"[Immo Maroc] {n} changement(s) détecté(s) le {diff['date']}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = ", ".join(recipients)

    txt = (
        f"Rapport Immobilier Maroc — {diff['date']}\n"
        f"Nouveaux  : {len(diff['nouveaux'])}\n"
        f"Supprimés : {len(diff['supprimes'])}\n"
        f"Modifiés  : {len(diff['modifies'])}\n"
    )

    msg.attach(MIMEText(txt, "plain", "utf-8"))
    msg.attach(MIMEText(_build_html(diff), "html", "utf-8"))

    try:
        with smtplib.SMTP(host, port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(sender, password)
            smtp.sendmail(sender, recipients, msg.as_string())
        print(f"📧  Email envoyé à {len(recipients)} destinataire(s)")
    except Exception as e:
        print(f"❌  Erreur envoi email : {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print(f"🔍  Démarrage du monitoring multi-sources — {date.today()}")
    print("=" * 60)

    # 1. Charger la baseline (gestion de l'ancien nom de fichier automatique)
    anciens = load_csv(DATA_FILE)
    print(f"\n📁  Baseline chargée : {len(anciens)} projets\n")

    # 2. Scraper toutes les sources
    nouveaux = scrape(
        include_liliskane=True,
        include_alomrane=True,
        include_addoha=True,
        alomrane_details=False,  # Mettre True pour enrichir statut/date (plus lent)
    )

    if not nouveaux:
        print("⚠️   Aucun projet récupéré — abandon (tous les sites sont peut-être indisponibles)")
        sys.exit(1)

    # 3. Comparer
    diff = comparer(anciens, nouveaux)
    log_file = LOGS_DIR / f"diff_{diff['date']}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(diff, f, ensure_ascii=False, indent=2)
    print(f"\n📝  Diff enregistré → {log_file}")
    print(f"   Nouveaux  : {len(diff['nouveaux'])}")
    print(f"   Supprimés : {len(diff['supprimes'])}")
    print(f"   Modifiés  : {len(diff['modifies'])}")

    # 4. Email si changements
    if a_des_changements(diff):
        print("\n🔔  Changements détectés → envoi de l'email...")
        try:
            envoyer_email(diff)
        except KeyError as e:
            print(f"⚠️   Variable d'environnement manquante : {e}")
            print("    (configurez EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT)")
    else:
        print("\n✅  Aucun changement — pas d'email envoyé")

    # 5. Mettre à jour la baseline
    save_csv(nouveaux, DATA_FILE)
    print("\n🏁  Monitoring terminé.")


if __name__ == "__main__":
    main()
