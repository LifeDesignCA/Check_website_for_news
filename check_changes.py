"""
check_changes.py
────────────────
1. Scrape le site liliskane.com
2. Compare avec la baseline (data/projets_liliskane.csv)
3. Si des changements : enregistre un diff JSON dans logs/, envoie un email
4. Sauvegarde le nouveau CSV comme nouvelle baseline

Variables d'environnement requises (GitHub Secrets ou .env local) :
  EMAIL_SENDER      ex: moncompte@gmail.com
  EMAIL_PASSWORD    mot de passe d'application Gmail (pas le MDP habituel)
  EMAIL_RECIPIENT   ex: moi@example.com
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
DATA_FILE = ROOT / "data" / "projets_liliskane.csv"
LOGS_DIR  = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# ── CSV helpers ───────────────────────────────────────────────────────────────

def load_csv(path: Path) -> dict[str, dict]:
    """Charge le CSV et retourne un dict indexé par l'URL (clé unique)."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8-sig") as f:
        return {row["Lien"]: row for row in csv.DictReader(f, delimiter=";")}


def save_csv(data: list[dict], path: Path) -> None:
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, delimiter=";")
        writer.writeheader()
        writer.writerows(data)
    print(f"✅  Baseline mise à jour → {path}")


# ── Comparaison ───────────────────────────────────────────────────────────────

CHAMPS_SURVEILLES = ["Prix (DHS)", "Superficie Min", "Superficie Max",
                     "Date de début", "Ville", "Catégorie"]


def comparer(anciens: dict, nouveaux: list[dict]) -> dict:
    """
    Retourne un dict avec trois clés :
      - 'nouveaux'  : projets absents de la baseline
      - 'supprimes' : projets présents dans baseline mais absents du scrape
      - 'modifies'  : projets dont au moins un champ surveillé a changé
    """
    new_map     = {p["Lien"]: p for p in nouveaux}
    anciens_ids = set(anciens.keys())
    nouveaux_ids = set(new_map.keys())

    ajouts     = [new_map[k] for k in nouveaux_ids - anciens_ids]
    suppressions = [anciens[k] for k in anciens_ids - nouveaux_ids]

    modifications = []
    for url in anciens_ids & nouveaux_ids:
        ancien  = anciens[url]
        nouveau = new_map[url]
        champs_changes = {
            champ: {"avant": ancien.get(champ, ""), "apres": nouveau.get(champ, "")}
            for champ in CHAMPS_SURVEILLES
            if ancien.get(champ, "").strip() != nouveau.get(champ, "").strip()
        }
        if champs_changes:
            modifications.append({
                "projet": nouveau["Nom du Projet"],
                "ville":  nouveau["Ville"],
                "url":    url,
                "champs": champs_changes,
            })

    return {
        "date":        date.today().isoformat(),
        "nouveaux":    ajouts,
        "supprimes":   suppressions,
        "modifies":    modifications,
    }


def a_des_changements(diff: dict) -> bool:
    return bool(diff["nouveaux"] or diff["supprimes"] or diff["modifies"])


# ── Email ─────────────────────────────────────────────────────────────────────

def _build_html(diff: dict) -> str:
    today     = diff["date"]
    n_add     = len(diff["nouveaux"])
    n_del     = len(diff["supprimes"])
    n_mod     = len(diff["modifies"])

    rows_add = "".join(
        f"<tr><td><a href='{p['Lien']}'>{p['Nom du Projet']}</a></td>"
        f"<td>{p['Ville']}</td><td>{p['Prix (DHS)']}</td>"
        f"<td>{p['Superficie Min']}</td><td>{p['Superficie Max']}</td></tr>"
        for p in diff["nouveaux"]
    )

    rows_del = "".join(
        f"<tr><td><a href='{p['Lien']}'>{p['Nom du Projet']}</a></td>"
        f"<td>{p['Ville']}</td></tr>"
        for p in diff["supprimes"]
    )

    rows_mod = ""
    for m in diff["modifies"]:
        champs_html = "".join(
            f"<li><b>{c}</b> : <span style='color:#c0392b'>{v['avant'] or '—'}</span>"
            f" → <span style='color:#27ae60'>{v['apres'] or '—'}</span></li>"
            for c, v in m["champs"].items()
        )
        rows_mod += (
            f"<tr><td><a href='{m['url']}'>{m['projet']}</a></td>"
            f"<td>{m['ville']}</td><td><ul style='margin:0;padding-left:16px'>"
            f"{champs_html}</ul></td></tr>"
        )

    style_table = (
        "border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:13px"
    )
    style_th = (
        "background:#2c3e50;color:#fff;padding:8px 10px;text-align:left"
    )
    style_td = "padding:7px 10px;border-bottom:1px solid #eee;vertical-align:top"

    section_nouveaux = f"""
    <h3 style="color:#27ae60">🟢 Nouveaux projets ({n_add})</h3>
    <table style="{style_table}">
      <tr>
        <th style="{style_th}">Nom</th>
        <th style="{style_th}">Ville</th>
        <th style="{style_th}">Prix</th>
        <th style="{style_th}">Sup. Min</th>
        <th style="{style_th}">Sup. Max</th>
      </tr>
      {rows_add or '<tr><td colspan="5" style="padding:8px">—</td></tr>'}
    </table>""" if n_add else ""

    section_supprimes = f"""
    <h3 style="color:#c0392b">🔴 Projets supprimés ({n_del})</h3>
    <table style="{style_table}">
      <tr>
        <th style="{style_th}">Nom</th>
        <th style="{style_th}">Ville</th>
      </tr>
      {rows_del or '<tr><td colspan="2" style="padding:8px">—</td></tr>'}
    </table>""" if n_del else ""

    section_modifies = f"""
    <h3 style="color:#e67e22">🟡 Projets modifiés ({n_mod})</h3>
    <table style="{style_table}">
      <tr>
        <th style="{style_th}">Nom</th>
        <th style="{style_th}">Ville</th>
        <th style="{style_th}">Changements</th>
      </tr>
      {rows_mod or '<tr><td colspan="3" style="padding:8px">—</td></tr>'}
    </table>""" if n_mod else ""

    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#222;max-width:800px;margin:auto">
      <h2 style="background:#2c3e50;color:#fff;padding:14px 18px;border-radius:4px">
        📊 Liliskane — Rapport de changements du {today}
      </h2>
      <p>
        Bonjour,<br><br>
        Le monitoring quotidien de <a href="https://www.liliskane.com">liliskane.com</a>
        a détecté des changements ce matin :
        <b>{n_add} nouveau(x)</b>,
        <b>{n_del} supprimé(s)</b>,
        <b>{n_mod} modifié(s)</b>.
      </p>
      {section_nouveaux}
      {section_supprimes}
      {section_modifies}
      <hr>
      <p style="font-size:11px;color:#888">
        Email généré automatiquement par le monitoring Liliskane · {datetime.now().strftime("%Y-%m-%d %H:%M")}
      </p>
    </body></html>
    """


def envoyer_email(diff: dict) -> None:
    sender    = os.environ["EMAIL_SENDER"]
    password  = os.environ["EMAIL_PASSWORD"]
    recipient = os.environ["EMAIL_RECIPIENT"]
    host      = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port      = int(os.environ.get("SMTP_PORT", 587))

    n = len(diff["nouveaux"]) + len(diff["supprimes"]) + len(diff["modifies"])
    subject = f"[Liliskane] {n} changement(s) détecté(s) le {diff['date']}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = recipient

    # Version texte brut (fallback)
    txt = (
        f"Rapport Liliskane — {diff['date']}\n"
        f"Nouveaux   : {len(diff['nouveaux'])}\n"
        f"Supprimés  : {len(diff['supprimes'])}\n"
        f"Modifiés   : {len(diff['modifies'])}\n\n"
        + "\n".join(
            f"[MOD] {m['projet']} ({m['ville']}) — "
            + ", ".join(f"{c}: {v['avant']} → {v['apres']}" for c, v in m["champs"].items())
            for m in diff["modifies"]
        )
    )
    msg.attach(MIMEText(txt, "plain", "utf-8"))
    msg.attach(MIMEText(_build_html(diff), "html", "utf-8"))

    with smtplib.SMTP(host, port) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(sender, password)
        smtp.sendmail(sender, recipient, msg.as_string())

    print(f"📧  Email envoyé à {recipient}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print(f"🔍  Démarrage du monitoring — {date.today()}")
    print("=" * 60)

    # 1. Charger la baseline
    anciens = load_csv(DATA_FILE)
    print(f"\n📁  Baseline chargée : {len(anciens)} projets\n")

    # 2. Scraper
    nouveaux = scrape()
    print(f"\n🌐  Scraping terminé : {len(nouveaux)} projets récupérés")

    if not nouveaux:
        print("⚠️   Aucun projet récupéré — abandon (le site est peut-être indisponible)")
        sys.exit(1)

    # 3. Comparer
    diff = comparer(anciens, nouveaux)
    log_file = LOGS_DIR / f"diff_{diff['date']}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(diff, f, ensure_ascii=False, indent=2)
    print(f"\n📝  Diff enregistré → {log_file}")
    print(f"   Nouveaux   : {len(diff['nouveaux'])}")
    print(f"   Supprimés  : {len(diff['supprimes'])}")
    print(f"   Modifiés   : {len(diff['modifies'])}")

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
