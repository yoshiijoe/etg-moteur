"""Classeur Excel du site : résultats, variantes, décision, séries, poids et prix. Sans formule."""
from __future__ import annotations

import csv
import datetime as dt
import io
import math

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.series import SeriesLabel
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .service import AVERTISSEMENTS, COLONNES_MESURES, ErreurRequete, charger, libelle_periode
from .univers import SERIES

SEMAINES_MAX = 520  # maximum du classeur de backtest de l'équipe
GRAS = Font(bold=True)
GRIS = PatternFill("solid", fgColor="D9D9D9")
ROUGE = PatternFill("solid", fgColor="F4B6B6")
FORMAT_DATE = "dd/mm/yyyy"
FORMATS = {"pct": "0.00%", "num": "0.000"}
ORANGE = "FF5B00"
GRIS_COURBE = "9A9A9A"
TITRE = Font(bold=True, size=16)
SOUS_TITRE = Font(bold=True, size=12)
DISCRET = Font(color="6B6B6B")
TRAIT = Border(bottom=Side(style="thin", color="E2E2E2"))
TRAIT_FORT = Border(bottom=Side(style="thin", color="0A0A0A"))
MARQUE = {"acheter": "+ acheter", "garder": "garder", "vendre": "− vendre", "—": "—"}  # pas de « = » : Excel le lirait comme une formule
# Mêmes chiffres clés et mêmes arrondis que l'en-tête du backtest sur le site
CHIFFRES_CLES = [("ann", "Rendement par an", "0.00%"), ("sharpe", "Sharpe", "0.00"),
                 ("perte_max", "Perte max", "0.00%"), ("rotation", "Rotation", "0.00")]


def _maintenant() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Europe/Paris"))
    except Exception:  # pragma: no cover - base de fuseaux absente
        return dt.datetime.now(dt.UTC)


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
    ws = wb.create_sheet("Lisez-moi")
    prm = bt["parametres"]
    prix_au = etat.get("dernier_vendredi") or dec["derniere_date"]
    lignes = [
        ("Moteur ETG : résultats du backtest et décision du mois", GRAS),
        (f"Fichier généré le {_maintenant():%d/%m/%Y à %H:%M}, avec les prix enregistrés sur le site à ce moment-là.", None),
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
        ("Onglets : Tableau de bord (mêmes chiffres et graphiques que le site), Tranches (6 mois), Lisez-moi, Resultats, Variantes, "
         "Decision, Serie, Poids, Prix_cloture, Prix_ouverture.", None),
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
                     "Perte du STOXX 600 depuis le sommet", "Mois (axe des graphiques)"], [14, 20, 22, 30, 32, 14])
    ws.auto_filter.ref = f"A1:F{len(s['dates']) + 1}"
    for i, x in enumerate(s["dates"]):
        ws.cell(i + 2, 6, f"{_date(x):%m/%Y}")
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


def _ligne_tableau(ws, ligne: int, titres: list) -> None:
    for j, t in enumerate(titres, 1):
        c = ws.cell(ligne, j, t)
        c.font = GRAS
        c.border = TRAIT_FORT
        c.alignment = Alignment(horizontal="left" if j <= 2 else "right", wrap_text=True)


def _tableau_de_bord(wb: Workbook, bt: dict, dec: dict, etat: dict) -> tuple:
    """Premier onglet : reprend la page du site (décision, chiffres clés, variantes). Graphiques ajoutés ensuite."""
    ws = wb.active
    ws.title = "Tableau de bord"
    ws.sheet_view.showGridLines = False
    prix_au = etat.get("dernier_vendredi") or dec["derniere_date"]
    source = etat.get("source", "Yahoo Finance")
    ws["A1"] = "Moteur ETG"
    ws["A1"].font = TITRE
    maj = etat.get("mise_a_jour")
    maj_txt = ""
    if maj:
        try:
            maj_txt = f" · mis à jour le {dt.datetime.fromisoformat(maj):%d/%m/%Y %H:%M} UTC"
        except ValueError:
            maj_txt = ""
    ws["A2"] = f"Prix au {_date(prix_au):%d/%m/%Y} · {source} · non validés{maj_txt}"
    ws["A2"].font = DISCRET
    ws["A3"] = f"Fichier généré le {_maintenant():%d/%m/%Y à %H:%M}"
    ws["A3"].font = DISCRET

    # Décision du mois
    ws["A5"] = "Décision du mois"
    ws["A5"].font = SOUS_TITRE
    ws["A6"] = f"Clôture du vendredi {_date(dec['date']):%d/%m/%Y}"
    if dec["apercu"]:
        ws["A7"] = (f"Aperçu : décision officielle le {_date(dec['date_officielle']):%d/%m/%Y}, "
                    "avec la clôture de ce jour-là.")
        ws["A7"].font = Font(bold=True, color=ORANGE)
    _ligne_tableau(ws, 8, ["Rang", "ETF", dec["libelle_court"], dec["libelle_long"], "Signal", "Détenu", "Décision"])
    ligne = 9
    for l in dec["lignes"]:
        ws.cell(ligne, 1, l["rang"]).alignment = Alignment(horizontal="left")
        etf = ws.cell(ligne, 2, l["etf"])
        if l["retenu"]:
            etf.font = Font(bold=True)
        for j, cle in ((3, "court"), (4, "long"), (5, "signal")):
            if l[cle] is not None:
                ws.cell(ligne, j, l[cle]).number_format = "+0.0%;-0.0%;0.0%"
        ws.cell(ligne, 6, "oui" if l["detenu"] else "").alignment = Alignment(horizontal="right")
        action = ws.cell(ligne, 7, MARQUE.get(l["action"], l["action"]))
        action.alignment = Alignment(horizontal="right")
        if l["action"] == "acheter":
            action.font = Font(bold=True, color=ORANGE)
        elif l["action"] == "vendre":
            action.font = Font(bold=True, color="6B6B6B")
        elif l["action"] == "—":
            action.font = DISCRET
        for j in range(1, 8):
            ws.cell(ligne, j).border = TRAIT
        ligne += 1
    places = dec["refuges"] + dec["cash"]
    ws.cell(ligne, 1, (f"Places remplacées par le filtre : {dec['refuges']} ETF monétaire(s), {dec['cash']} en cash. "
                       if places else "") + f"Chaque ligne retenue pèse {dec['poids']:.0%} de la poche moteur."
                      " Vérifier les cours du jour avant de passer les ordres.").font = DISCRET

    # Backtest
    ligne += 2
    ws.cell(ligne, 1, "Backtest").font = SOUS_TITRE
    prm = bt["parametres"]
    signal = (f"{prm['court']} + {prm['long']}" if prm["utiliser_court"] else f"{prm['long']}")
    ws.cell(ligne + 1, 1, f"Du {_date(bt['periode']['debut']):%d/%m/%Y} au {_date(bt['periode']['fin']):%d/%m/%Y} · "
                          f"{bt['periode']['semaines']} semaines · {'10 ETF' if prm['univers'] == '10' else '9 ETF'} · "
                          f"signal {signal} sem. · top {prm['top']}, tampon {prm['tampon']} · "
                          f"filtre {'oui' if prm['filtre'] else 'non'}").font = DISCRET
    ligne += 3
    _ligne_tableau(ws, ligne, ["", "Mesure", "Moteur", "STOXX Europe 600"])
    for k, (cle, titre, fmt) in enumerate(CHIFFRES_CLES, 1):
        ws.cell(ligne + k, 2, titre)
        m = ws.cell(ligne + k, 3, bt["moteur"].get(cle))
        m.number_format, m.font = fmt, Font(bold=True)
        r = bt["reference"].get(cle)
        ref = ws.cell(ligne + k, 4, r if r is not None else "sans objet")
        ref.number_format, ref.alignment = fmt, Alignment(horizontal="right")
        for j in range(2, 5):
            ws.cell(ligne + k, j).border = TRAIT
    ligne += len(CHIFFRES_CLES) + 2
    ancre_graphiques = ligne
    ligne += 37  # place des deux graphiques et de leurs titres

    ws.cell(ligne, 1, "Variantes").font = SOUS_TITRE
    ligne += 1
    _ligne_tableau(ws, ligne, ["Variante", ""] + [l for _, l, _ in COLONNES_MESURES])
    for v in bt["variantes"]:
        ligne += 1
        nom = ws.cell(ligne, 1, v["nom"])
        reference = v["nom"].startswith("STOXX")
        if reference:
            nom.font = DISCRET
        for j, (cle, _, fmt) in enumerate(COLONNES_MESURES, 3):
            x = v["mesures"].get(cle)
            if x is not None:
                c = ws.cell(ligne, j, x)
                c.number_format = FORMATS[fmt]
                if reference:
                    c.font = DISCRET
        for j in range(1, len(COLONNES_MESURES) + 3):
            ws.cell(ligne, j).border = TRAIT
    ligne += 2
    for a in AVERTISSEMENTS:
        ws.cell(ligne, 1, a).font = DISCRET
        ligne += 1
    for col, largeur in zip("ABCDEFGHIJK", (8, 24, 14, 18, 14, 12, 14, 16, 16, 16, 18)):
        ws.column_dimensions[col].width = largeur
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return ws, ancre_graphiques


def _bornes(valeurs: list, jusqu_a_zero: bool) -> tuple[float, float, float]:
    """Graduations « rondes » (1, 2, 2,5, 5 × 10^k) autour des données, comme les graphiques du site."""
    mini, maxi = min(valeurs), max(valeurs)
    if jusqu_a_zero:
        maxi = 0.0
    brut = (maxi - mini) / 4 or 1
    puissance = 10 ** math.floor(math.log10(brut))
    pas = next(k * puissance for k in (1, 2, 2.5, 5, 10) if k * puissance >= brut)
    return math.floor(mini / pas) * pas, math.ceil(maxi / pas) * pas, pas


def _graphiques(ws, ws_serie, ancre: int, n: int) -> None:
    """Les deux courbes du site, en graphiques Excel natifs : moteur en orange, STOXX 600 en gris."""
    mois = Reference(ws_serie, min_col=6, min_row=2, max_row=n + 1)
    for titre, colonnes, format_axe, ligne, jusqu_a_zero in (
            ("Valeur en base 100", (2, 3), "0", ancre, False),
            ("Perte depuis le sommet", (4, 5), "0%", ancre + 18, True)):
        ws.cell(ligne, 1, titre).font = SOUS_TITRE
        valeurs = [ws_serie.cell(r, c).value for c in colonnes for r in range(2, n + 2)]
        bas, haut, pas = _bornes(valeurs, jusqu_a_zero)
        g = LineChart()
        g.height, g.width = 7.5, 17
        g.legend.position = "t"
        g.legend.overlay = False
        g.y_axis.number_format = format_axe
        g.y_axis.scaling.min, g.y_axis.scaling.max, g.y_axis.majorUnit = bas, haut, pas
        g.y_axis.majorGridlines.spPr = GraphicalProperties(ln=LineProperties(solidFill="E2E2E2"))
        g.y_axis.spPr = GraphicalProperties(ln=LineProperties(noFill=True))
        g.x_axis.delete = False
        g.y_axis.delete = False
        g.x_axis.tickLblSkip = g.x_axis.tickMarkSkip = 13  # un repère par trimestre environ
        g.x_axis.tickLblPos = "low"
        for col, couleur, nom, epaisseur in ((colonnes[0], ORANGE, "Moteur", 22000),
                                             (colonnes[1], GRIS_COURBE, "STOXX Europe 600", 15000)):
            g.add_data(Reference(ws_serie, min_col=col, min_row=2, max_row=n + 1))
            serie = g.series[-1]
            serie.tx = SeriesLabel(v=nom)
            serie.graphicalProperties.line.solidFill = couleur
            serie.graphicalProperties.line.width = epaisseur
            serie.smooth = False
            serie.marker.symbol = "none"
        g.set_categories(mois)
        ws.add_chart(g, f"A{ligne + 1}")


def _tranches(wb: Workbook, tr: dict) -> None:
    """Onglet « Tranches » : mêmes chiffres, même graphique et mêmes tableaux que la section du site."""
    ws = wb.create_sheet("Tranches", 1)
    ws.sheet_view.showGridLines = False
    s = tr["synthese"]
    prm = tr["parametres"]
    signal = f"{prm['court']} + {prm['long']}" if prm["utiliser_court"] else f"{prm['long']}"
    ws["A1"] = "Tranches de 6 mois"
    ws["A1"].font = TITRE
    ws["A2"] = tr["note"]
    ws["A2"].font = DISCRET
    ws["A3"] = (f"{s['tranches']} tranches complètes · {'10 ETF' if prm['univers'] == '10' else '9 ETF'} · signal {signal} sem. "
                f"· top {prm['top']}, tampon {prm['tampon']} · filtre {'oui' if prm['filtre'] else 'non'}")
    ws["A3"].font = DISCRET
    _ligne_tableau(ws, 5, ["", "Mesure", "Moteur", tr["reference"]])
    lignes_synthese = [
        ("Rendement moyen sur 6 mois", s["moteur_moyenne"], s["stoxx_moyenne"], "+0.0%;-0.0%;0.0%"),
        ("Rendement médian sur 6 mois", s["moteur_mediane"], s["stoxx_mediane"], "+0.0%;-0.0%;0.0%"),
        ("Tranches où le moteur fait mieux", s["part_bat_stoxx"], None, "0%"),
        ("Pire tranche", s["pire"], s["stoxx_pire"], "+0.0%;-0.0%;0.0%"),
        ("Meilleure tranche", s["meilleure"], s["stoxx_meilleure"], "+0.0%;-0.0%;0.0%"),
        ("Écart moyen avec le STOXX 600", s["ecart_moyen"], None, "+0.0%;-0.0%;0.0%"),
        ("Écart médian avec le STOXX 600", s["ecart_median"], None, "+0.0%;-0.0%;0.0%"),
        ("Fiabilité de l'écart (t, 2 = solide)", s["t_ecart"], None, "0.00"),
        ("Moyenne des 10 ETF à parts égales", s["parts_egales_moyenne"], None, "+0.0%;-0.0%;0.0%"),
    ]
    for k, (titre, a, b, fmt) in enumerate(lignes_synthese, 6):
        ws.cell(k, 2, titre)
        c = ws.cell(k, 3, a)
        c.number_format, c.font = fmt, Font(bold=True)
        if b is not None:
            ws.cell(k, 4, b).number_format = fmt
        for j in range(2, 5):
            ws.cell(k, j).border = TRAIT
    debut_detail = 6 + len(lignes_synthese) + 21
    ws.cell(6 + len(lignes_synthese) + 1, 1, "Écart avec le STOXX 600, tranche par tranche").font = SOUS_TITRE

    ws.cell(debut_detail - 1, 1, "Détail").font = SOUS_TITRE
    titres = ["Tranche", "Du", "Au", "Semaines", "Moteur", tr["reference"], "Écart", "Parts égales", "Perte max",
              "ETF achetés au départ"]
    _ligne_tableau(ws, debut_detail, titres)
    r = debut_detail
    for l in tr["lignes"]:
        r += 1
        ws.cell(r, 1, l["tranche"])
        ws.cell(r, 2, _date(l["debut"])).number_format = FORMAT_DATE
        ws.cell(r, 3, _date(l["fin"])).number_format = FORMAT_DATE
        ws.cell(r, 4, l["semaines"])
        for j, cle in ((5, "moteur"), (6, "stoxx"), (7, "ecart"), (8, "parts_egales"), (9, "perte_max")):
            ws.cell(r, j, l[cle]).number_format = "+0.0%;-0.0%;0.0%"
        ecart = ws.cell(r, 7)
        ecart.font = Font(bold=True, color=ORANGE) if l["ecart"] > 0 else Font(bold=True, color="6B6B6B")
        depart = ", ".join(l["depart"]) or "aucun ETF"
        if l["refuge_depart"]:
            depart += f" + refuge {l['refuge_depart']:.0%}"
        ws.cell(r, 10, depart)
        for j in range(1, 11):
            ws.cell(r, j).border = TRAIT
    fin_detail = r

    r += 2
    ws.cell(r, 1, "Variantes sur 6 mois").font = SOUS_TITRE
    r += 1
    _ligne_tableau(ws, r, ["Variante", "", "Moyenne", "Médiane", "Écart moyen", "Bat le STOXX 600",
                           "Bat les parts égales", "Pire tranche"])
    for v in tr["variantes"]:
        r += 1
        x = v["synthese"]
        ws.cell(r, 1, v["nom"])
        for j, (cle, fmt) in enumerate((("moteur_moyenne", "+0.0%;-0.0%;0.0%"), ("moteur_mediane", "+0.0%;-0.0%;0.0%"),
                                        ("ecart_moyen", "+0.0%;-0.0%;0.0%"), ("part_bat_stoxx", "0%"),
                                        ("part_bat_parts_egales", "0%"), ("pire", "+0.0%;-0.0%;0.0%")), 3):
            ws.cell(r, j, x[cle]).number_format = fmt
        for j in range(1, 9):
            ws.cell(r, j).border = TRAIT

    g = BarChart()
    g.type = "col"
    g.height, g.width = 7.5, 22
    g.legend = None
    g.y_axis.number_format = "0%"
    g.y_axis.majorGridlines.spPr = GraphicalProperties(ln=LineProperties(solidFill="E2E2E2"))
    g.x_axis.delete = False
    g.y_axis.delete = False
    g.x_axis.tickLblPos = "low"
    g.gapWidth = 40
    g.add_data(Reference(ws, min_col=7, min_row=debut_detail + 1, max_row=fin_detail))
    g.set_categories(Reference(ws, min_col=1, min_row=debut_detail + 1, max_row=fin_detail))
    serie = g.series[0]
    serie.tx = SeriesLabel(v="Écart moteur − STOXX 600")
    serie.graphicalProperties.solidFill = ORANGE
    serie.graphicalProperties.line.noFill = True
    serie.invertIfNegative = True
    from openpyxl.chart.marker import DataPoint
    for k, l in enumerate(tr["lignes"]):
        if l["ecart"] < 0:
            point = DataPoint(idx=k)
            point.graphicalProperties.solidFill = GRIS_COURBE
            point.graphicalProperties.line.noFill = True
            serie.dPt.append(point)
    ws.add_chart(g, f"A{6 + len(lignes_synthese) + 2}")
    for col, largeur in zip("ABCDEFGHIJ", (10, 30, 12, 16, 12, 16, 12, 14, 12, 52)):
        ws.column_dimensions[col].width = largeur
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def construire_classeur(texte_csv: str, bt: dict, dec: dict, etat: dict, tr: dict | None = None) -> bytes:
    if not bt.get("variantes"):
        raise ErreurRequete("Le backtest doit contenir les variantes pour l'Excel.")
    wb = Workbook()
    tableau, ancre = _tableau_de_bord(wb, bt, dec, etat)
    _lisez_moi(wb, bt, dec, etat)
    _resultats(wb, bt)
    _variantes(wb, bt)
    _decision(wb, dec)
    _serie(wb, bt)
    _poids(wb, bt)
    _prix(wb, texte_csv)
    _graphiques(tableau, wb["Serie"], ancre, len(bt["series"]["dates"]))
    if tr:
        _tranches(wb, tr)
    sortie = io.BytesIO()
    wb.save(sortie)
    return sortie.getvalue()


def nom_fichier(dec: dict) -> str:
    return f"moteur-etg-{dec['date']}.xlsx"
