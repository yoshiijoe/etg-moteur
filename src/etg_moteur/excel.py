"""Classeur Excel du site : résultats, variantes, décision, séries, poids et prix. Sans formule."""
from __future__ import annotations

import csv
import datetime as dt
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .service import AVERTISSEMENTS, COLONNES_MESURES, ErreurRequete, charger, libelle_periode
from .univers import SERIES

SEMAINES_MAX = 520  # maximum du classeur de backtest de l'équipe
GRAS = Font(bold=True)
GRIS = PatternFill("solid", fgColor="D9D9D9")
ROUGE = PatternFill("solid", fgColor="F4B6B6")
FORMAT_DATE = "dd/mm/yyyy"
FORMATS = {"pct": "0.00%", "num": "0.000"}


def _entetes(ws, ligne: int, titres: list, largeurs: list | None = None) -> None:
    for j, t in enumerate(titres, 1):
        c = ws.cell(ligne, j, t)
        c.font = GRAS
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = ws.cell(ligne + 1, 1)
    for j in range(1, len(titres) + 1):
        ws.column_dimensions[get_column_letter(j)].width = (largeurs or [])[j - 1] if largeurs and j <= len(largeurs) else 16


def _date(iso: str) -> dt.date:
    return dt.date.fromisoformat(iso)


def _lisez_moi(wb: Workbook, bt: dict, dec: dict, etat: dict) -> None:
    ws = wb.active
    ws.title = "Lisez-moi"
    prm = bt["parametres"]
    prix_au = etat.get("dernier_vendredi") or dec["derniere_date"]
    lignes = [
        ("Moteur ETG : résultats du backtest et décision du mois", GRAS),
        (f"Fichier généré le {dt.date.today():%d/%m/%Y}.", None),
        (f"Prix au {_date(prix_au):%d/%m/%Y} · Source : Yahoo Finance · prix non validés par l'équipe.", None),
        ("", None),
        ("Paramètres utilisés", GRAS),
        (f"Période du backtest : du {_date(bt['periode']['debut']):%d/%m/%Y} au {_date(bt['periode']['fin']):%d/%m/%Y} "
         f"({bt['periode']['semaines']} semaines).", None),
        (f"Univers : {'10 ETF' if prm['univers'] == '10' else '9 ETF, sans la Défense'}.", None),
        (f"Signal : {'moyenne des performances sur ' + str(prm['court']) + ' et ' + str(prm['long']) + ' semaines' if prm['utiliser_court'] else 'performance sur ' + str(prm['long']) + ' semaines seule'}.", None),
        (f"Lignes retenues : {prm['top']} ; une ligne détenue n'est vendue que si elle sort du top {prm['tampon']}.", None),
        (f"Filtre de signal négatif (remplacement par les ETF monétaires puis du cash) : {'oui' if prm['filtre'] else 'non'}.", None),
        (f"Décision : clôture du vendredi {_date(dec['date']):%d/%m/%Y}"
         + (f" (aperçu : décision officielle le {_date(dec['date_officielle']):%d/%m/%Y})." if dec["apercu"] else " (décision officielle)."), None),
        (f"ETF détenus pris en compte : {', '.join(dec['detenus']) or 'aucun'}.", None),
        ("", None),
        ("Avertissements", GRAS),
        *[(a, None) for a in AVERTISSEMENTS],
        ("", None),
        ("Onglets : Resultats, Variantes, Decision, Serie, Poids, Prix_cloture, Prix_ouverture.", None),
        ("Prix_cloture et Prix_ouverture reprennent la mise en page du classeur de backtest de l'équipe : "
         "à copier à partir de la ligne 6, en collage spécial valeurs. Gris : période prolongée par un fonds proche. "
         "Rouge : aucune donnée.", None),
    ]
    for i, (texte, police) in enumerate(lignes, 1):
        c = ws.cell(i, 1, texte)
        if police:
            c.font = police
    ws.column_dimensions["A"].width = 120


def _resultats(wb: Workbook, bt: dict) -> None:
    ws = wb.create_sheet("Resultats")
    _entetes(ws, 1, ["Mesure", "Moteur", "STOXX Europe 600"], [28, 16, 20])
    for i, (cle, libelle, fmt) in enumerate(COLONNES_MESURES, 2):
        ws.cell(i, 1, libelle)
        for j, source in ((2, bt["moteur"]), (3, bt["reference"])):
            v = source.get(cle)
            if v is not None:
                c = ws.cell(i, j, v)
                c.number_format = FORMATS[fmt]
    n = len(COLONNES_MESURES) + 3
    ws.cell(n, 1, "Les mesures sans valeur pour le STOXX 600 (rotation, HHI, bêta, volatilité ex-ante, diversification) "
                  "n'ont de sens que pour le moteur.")


def _variantes(wb: Workbook, bt: dict) -> None:
    ws = wb.create_sheet("Variantes")
    _entetes(ws, 1, ["Variante"] + [l for _, l, _ in COLONNES_MESURES], [22] + [16] * len(COLONNES_MESURES))
    for i, v in enumerate(bt["variantes"], 2):
        ws.cell(i, 1, v["nom"])
        for j, (cle, _, fmt) in enumerate(COLONNES_MESURES, 2):
            x = v["mesures"].get(cle)
            if x is not None:
                ws.cell(i, j, x).number_format = FORMATS[fmt]


def _decision(wb: Workbook, dec: dict) -> None:
    ws = wb.create_sheet("Decision")
    _entetes(ws, 1, ["Rang", "ETF", dec["libelle_court"], dec["libelle_long"], "Signal", "Détenu", "Décision"],
             [8, 24, 12, 12, 12, 10, 14])
    for i, l in enumerate(dec["lignes"], 2):
        ws.cell(i, 1, l["rang"])
        ws.cell(i, 2, l["etf"])
        for j, cle in ((3, "court"), (4, "long"), (5, "signal")):
            if l[cle] is not None:
                ws.cell(i, j, l[cle]).number_format = "0.0%"
        ws.cell(i, 6, "oui" if l["detenu"] else "non")
        ws.cell(i, 7, l["action"])
    n = len(dec["lignes"]) + 3
    ws.cell(n, 1, f"Clôture du vendredi {_date(dec['date']):%d/%m/%Y}.")
    if dec["apercu"]:
        ws.cell(n + 1, 1, f"Aperçu : la décision officielle se prend le {_date(dec['date_officielle']):%d/%m/%Y}, "
                          "avec la clôture de ce jour-là.")
    if dec["refuges"] or dec["cash"]:
        ws.cell(n + 2, 1, f"Places remplacées par le filtre : {dec['refuges']} ETF monétaire(s), {dec['cash']} en cash.")


def _serie(wb: Workbook, bt: dict) -> None:
    ws = wb.create_sheet("Serie")
    s = bt["series"]
    _entetes(ws, 1, ["Date", "Moteur (base 100)", "STOXX 600 (base 100)", "Perte du moteur depuis le sommet",
                     "Perte du STOXX 600 depuis le sommet"], [14, 20, 22, 30, 32])
    for i, x in enumerate(s["dates"]):
        ws.cell(i + 2, 1, _date(x)).number_format = FORMAT_DATE
        ws.cell(i + 2, 2, s["moteur"][i]).number_format = "0.00"
        ws.cell(i + 2, 3, s["reference"][i]).number_format = "0.00"
        ws.cell(i + 2, 4, s["perte_moteur"][i]).number_format = "0.00%"
        ws.cell(i + 2, 5, s["perte_reference"][i]).number_format = "0.00%"


def _poids(wb: Workbook, bt: dict) -> None:
    ws = wb.create_sheet("Poids")
    p = bt["poids"]
    _entetes(ws, 1, ["Date"] + p["colonnes"], [14] + [18] * len(p["colonnes"]))
    for i, x in enumerate(p["dates"]):
        ws.cell(i + 2, 1, _date(x)).number_format = FORMAT_DATE
        for j, v in enumerate(p["valeurs"][i], 2):
            ws.cell(i + 2, j, v).number_format = "0.0%"


def _prix(wb: Workbook, texte_csv: str) -> None:
    """Prix_cloture et Prix_ouverture : mise en page du classeur de l'équipe (titres lignes 3 à 5, données dès la ligne 6)."""
    d = charger(texte_csv, "10")
    brut = list(csv.DictReader(io.StringIO(texte_csv, newline="")))
    noms = [s[0] for s in SERIES]
    codes = [s[3] for s in SERIES]
    donnees_serie = {n: (d.cloture[i], d.ouverture[i]) for i, n in enumerate(d.noms)}
    for k, n in enumerate(["Monétaire n°1", "Monétaire n°2"]):
        donnees_serie[n] = (d.monetaire_cloture[k], d.monetaire_ouverture[k])
    donnees_serie[noms[-1]] = (d.reference_cloture, d.reference_ouverture)
    # Dernières semaines avec une ouverture du lundi pour la référence (comme le classeur de l'équipe)
    derniere = max(t for t in range(len(d.dates)) if d.reference_ouverture[t])
    debut = max(0, derniere + 1 - SEMAINES_MAX)
    intitules = ["ETF %d" % (i + 1) for i in range(10)] + ["Monétaire", "Monétaire", "Référence"]
    for titre, champ, indice in (("Prix_cloture", "Clôture du vendredi (dividendes réinvestis)", 0),
                                 ("Prix_ouverture", "Ouverture du lundi suivant (dividendes réinvestis)", 1)):
        ws = wb.create_sheet(titre)
        ws.cell(1, 1, champ).font = GRAS
        ws.cell(2, 1, "Gris : période prolongée par un fonds proche. Rouge : aucune donnée.")
        for j, valeur in enumerate(["Date (vendredi)"] + intitules, 1):
            ws.cell(3, j, valeur).font = GRAS
        for j, valeur in enumerate(["Nom"] + noms, 1):
            ws.cell(4, j, valeur).font = GRAS
        for j, valeur in enumerate(["Ticker"] + codes, 1):
            ws.cell(5, j, valeur).font = GRAS
        for r, t in enumerate(range(debut, derniere + 1), 6):
            ws.cell(r, 1, d.dates[t]).number_format = FORMAT_DATE
            ligne_brute = brut[t]
            for j, n in enumerate(noms, 2):
                v = donnees_serie[n][indice][t]
                c = ws.cell(r, j, v)
                c.number_format = "0.00"
                origine = ligne_brute.get(f"{n} origine", "")
                morceaux = origine.split("/")
                o = morceaux[indice] if len(morceaux) == 2 else morceaux[0]
                if v is None:
                    c.fill = ROUGE
                elif o == "pxy":
                    c.fill = GRIS
        ws.freeze_panes = "B6"
        ws.column_dimensions["A"].width = 15
        for j in range(2, 15):
            ws.column_dimensions[get_column_letter(j)].width = 16


def construire_classeur(texte_csv: str, bt: dict, dec: dict, etat: dict) -> bytes:
    if not bt.get("variantes"):
        raise ErreurRequete("Le backtest doit contenir les variantes pour l'Excel.")
    wb = Workbook()
    _lisez_moi(wb, bt, dec, etat)
    _resultats(wb, bt)
    _variantes(wb, bt)
    _decision(wb, dec)
    _serie(wb, bt)
    _poids(wb, bt)
    _prix(wb, texte_csv)
    sortie = io.BytesIO()
    wb.save(sortie)
    return sortie.getvalue()


def nom_fichier(dec: dict) -> str:
    return f"moteur-etg-{dec['date']}.xlsx"
