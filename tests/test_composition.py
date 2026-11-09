"""Simulateur du portefeuille : chiffres de contrôle de la section 6 du cahier des charges et mathématiques des indicateurs."""
import math
import random

import pytest

from etg_moteur import composition as c
from etg_moteur.moteur import Donnees, Parametres, _ex_ante
from etg_moteur.univers import SERIES

# --- Chiffres de contrôle (poids cibles de la page Stratégie, section 6) --------------------------


@pytest.fixture(scope="module")
def cible():
    return c.portefeuille_cible()


def test_controle_total_des_poids(cible):
    assert sum(l.poids for l in cible) == pytest.approx(1.0, abs=1e-12)
    assert len(cible) == 19  # 4 moteur + 6 socle + 8 convictions + cash


def test_controle_scenarios_A_B_C(cible):
    s = c.poids_scenarios(cible)
    assert s["A"] == pytest.approx(0.260, abs=1e-12)
    assert s["B"] == pytest.approx(0.305, abs=1e-12)
    assert s["C"] == pytest.approx(0.435, abs=1e-12)
    assert s[""] == pytest.approx(0.0, abs=1e-12)


def test_controle_lignes_au_dessus_de_5_pourcent(cible):
    assert c.somme_grosses_lignes(cible) == pytest.approx(0.32, abs=1e-12)
    assert {l.code for l in cible if l.type != "cash" and l.poids > 0.05} == {"HLT", "TNO", "ENRG", "FOO"}


def test_controle_hhi_cash_exclu(cible):
    assert round(c.hhi(cible), 5) == 0.05395


def test_controle_exposition_nette_aux_actions(cible):
    assert c.exposition_nette(cible) == pytest.approx(0.815, abs=1e-12)


def test_controle_ligne_la_plus_lourde(cible):
    assert c.ligne_la_plus_lourde(cible).poids == pytest.approx(0.08)


def test_les_controles_de_regles_ne_sont_pas_hors_regle_sur_les_poids_cibles(cible):
    liste = {x["id"]: x for x in c.controles(cible, {l.code: 50.0 for l in cible})}
    assert not [x for x in liste.values() if x["statut"] == c.HORS_REGLE]
    # Scénarios A (26 %) et C (43,5 %) sont proches des bornes 25 % et 45 % : attention
    assert liste["scenario_A"]["statut"] == c.ATTENTION and liste["scenario_C"]["statut"] == c.ATTENTION
    assert liste["scenario_B"]["statut"] == c.CONFORME
    assert liste["ligne"]["statut"] == c.CONFORME
    assert liste["secteur"]["valeur"] == pytest.approx(0.125)  # ETF 8 % + action 4,5 % : Énergie, Santé, Agroalimentaire
    assert liste["actions_secteur"]["statut"] == c.CONFORME
    assert liste["places"]["statut"] == c.CONFORME


def test_ordres_du_notion_conserves(cible):
    par_code = {l.code: l for l in cible}
    assert par_code["KRX"].scenario == "B"      # « B (et A) » : première lettre
    assert par_code["ENX"].scenario == "A" and par_code["NN"].scenario == "A"
    assert par_code["MOWI"].devise == "NOK"
    assert par_code["CASH"].scenario == "C" and par_code["CASH"].poids == pytest.approx(0.05)


# --- Règles -----------------------------------------------------------------------------------


def ligne(code, poids, type_="action", secteur="X", scenario="A", symbole=None, poche="Convictions"):
    return c.Ligne(code, code, poche, type_, symbole or f"{code}.PA", None, secteur, scenario, poids)


def test_plafond_ligne_a_10_pourcent():
    base = [ligne("A", 0.10), ligne("B", 0.90 - 0.001, "etf_actions"), ligne("CASH", 0.001, "cash")]
    tous = {x["id"]: x["statut"] for x in c.controles(base)}
    assert tous["ligne"] == c.ATTENTION or tous["ligne"] == c.HORS_REGLE  # B pèse 89,9 %
    ok = [ligne(str(i), 0.10, "etf_actions") for i in range(10)] + [ligne("CASH", 0.0, "cash")]
    assert {x["id"]: x["statut"] for x in c.controles(ok)}["ligne"] == c.ATTENTION   # au plafond : attention
    hors = [ligne("A", 0.11), ligne("CASH", 0.89, "cash")]
    assert {x["id"]: x["statut"] for x in c.controles(hors)}["ligne"] == c.HORS_REGLE


def test_somme_des_grosses_lignes_et_refuge_monetaire():
    grosses = [ligne(str(i), 0.09, "etf_actions", secteur=str(i)) for i in range(5)] + [ligne("CASH", 0.55, "cash")]
    liste = {x["id"]: x for x in c.controles(grosses)}
    assert liste["grosses"]["statut"] == c.HORS_REGLE and liste["grosses"]["valeur"] == pytest.approx(0.45)
    refuge = [ligne("M", 0.09, "etf_monetaire", secteur="Monétaire"), ligne("CASH", 0.91, "cash")]
    assert {x["id"]: x["statut"] for x in c.controles(refuge)}["refuge"] == c.HORS_REGLE
    refuge[0].poids = 0.08
    assert {x["id"]: x["statut"] for x in c.controles(refuge)}["refuge"] == c.ATTENTION


def test_secteur_cumule_et_actions_par_secteur():
    lignes = [ligne("E", 0.08, "etf_actions", secteur="Énergie", poche="Moteur"),
              ligne("G", 0.04, "action", secteur="Énergie"), ligne("H", 0.04, "action", secteur="Énergie"),
              ligne("CASH", 0.84, "cash")]
    liste = {x["id"]: x for x in c.controles(lignes)}
    assert liste["secteur"]["statut"] == c.HORS_REGLE and liste["secteur"]["valeur"] == pytest.approx(0.16)
    assert liste["actions_secteur"]["statut"] == c.HORS_REGLE and "Énergie" in liste["actions_secteur"]["detail"]


def test_scenarios_hors_fourchette():
    lignes = [ligne("A1", 0.05, scenario="A"), ligne("B1", 0.50, "etf_actions", scenario="B", secteur=""),
              ligne("CASH", 0.45, "cash")]
    liste = {x["id"]: x["statut"] for x in c.controles(lignes)}
    assert liste["scenario_A"] == c.HORS_REGLE and liste["scenario_B"] == c.HORS_REGLE and liste["scenario_C"] == c.HORS_REGLE


def test_scenario_a_definir_signale():
    lignes = [ligne("X", 0.30, scenario=""), ligne("CASH", 0.70, "cash")]
    liste = {x["id"]: x for x in c.controles(lignes)}
    assert liste["scenario_a_definir"]["valeur"] == pytest.approx(0.30)


@pytest.mark.parametrize("symbole,attendu", [("ENX.PA", True), ("NN.AS", True), ("UCB.BR", True), ("GALP.LS", True),
                                             ("PRY.MI", True), ("MOWI.OL", True), ("KRX.IR", True), ("AAPL", False),
                                             ("SAP.DE", False), ("VOD.L", False), ("ENX.pa", True), (None, None), ("", None)])
def test_places_autorisees(symbole, attendu):
    assert c.place_autorisee(symbole) is attendu


def test_place_non_autorisee_hors_regle_et_symbole_inconnu_attention():
    lignes = [ligne("A", 0.05, symbole="SAP.DE"), ligne("B", 0.05), ligne("CASH", 0.9, "cash")]
    liste = {x["id"]: x for x in c.controles(lignes)}
    assert liste["places"]["statut"] == c.HORS_REGLE and "A" in liste["places"]["detail"]
    lignes[0].symbole = None
    assert {x["id"]: x["statut"] for x in c.controles(lignes)}["places"] == c.ATTENTION


def test_alerte_penny_stock():
    lignes = [ligne("P", 0.05), ligne("Q", 0.05), ligne("CASH", 0.9, "cash")]
    liste = {x["id"]: x for x in c.controles(lignes, {"P": 0.84, "Q": 1.0})}
    assert liste["penny"]["statut"] == c.ATTENTION and "P (0.84 €)" in liste["penny"]["detail"]
    assert {x["id"]: x["statut"] for x in c.controles(lignes, {"P": 5.0, "Q": 1.0})}["penny"] == c.CONFORME


def test_pire_statut():
    assert c.pire_statut([{"statut": c.CONFORME}, {"statut": c.ATTENTION}]) == c.ATTENTION
    assert c.pire_statut([{"statut": c.ATTENTION}, {"statut": c.HORS_REGLE}]) == c.HORS_REGLE
    assert c.pire_statut([]) == c.CONFORME


# --- Exposition, secteurs, HHI --------------------------------------------------------------------


def test_exposition_nette_obligations_cash_et_inverse():
    lignes = [ligne("A", 0.40, "etf_actions"), ligne("O", 0.20, "etf_obligations"), ligne("I", 0.10, "etf_inverse"),
              ligne("M", 0.10, "etf_monetaire"), ligne("CASH", 0.20, "cash")]
    assert c.exposition_nette(lignes) == pytest.approx(0.30)


def test_nombre_de_secteurs_ignore_les_lignes_non_sectorielles():
    lignes = [ligne("A", 0.1, secteur="Santé"), ligne("B", 0.1, secteur="Santé"), ligne("C", 0.1, secteur="Énergie"),
              ligne("D", 0.1, "etf_actions", secteur="Multi-secteurs"), ligne("E", 0.1, secteur=""),
              ligne("CASH", 0.5, "cash")]
    assert c.nombre_secteurs(lignes) == 2


def test_hhi_exclut_le_cash_sans_renormaliser():
    assert c.hhi([ligne("A", 0.5), ligne("B", 0.2), ligne("CASH", 0.3, "cash")]) == pytest.approx(0.29)


def test_poids_depuis_positions():
    lignes = [ligne("A", 0, symbole="A.PA"), ligne("B", 0, symbole="B.PA"), ligne("CASH", 0, "cash")]
    res = c.poids_depuis_positions(lignes, {"A": 10, "B": 5}, 50.0, {"A": 10.0, "B": 20.0})
    assert [round(l.poids, 6) for l in res] == [0.4, 0.4, 0.2]
    assert sum(l.poids for l in res) == pytest.approx(1.0)
    with pytest.raises(c.ErreurComposition, match="Pas de cours"):
        c.poids_depuis_positions(lignes, {"A": 10}, 0.0, {})
    with pytest.raises(c.ErreurComposition, match="vide"):
        c.poids_depuis_positions(lignes, {}, 0.0, {})
    with pytest.raises(c.ErreurComposition, match="négative"):
        c.poids_depuis_positions(lignes, {"A": -1}, 10.0, {"A": 1.0})


# --- Mathématiques du risque ------------------------------------------------------------------------


def marche(n, graine, vol=0.02, derive=0.001):
    g = random.Random(graine)
    v, sortie = 100.0, []
    for _ in range(n):
        v *= 1 + g.gauss(derive, vol)
        sortie.append(v)
    return sortie


def donnees_synthetiques(n=230):
    noms = ["E0", "E1", "E2"]
    cloture = [marche(n, i + 1) for i in range(3)]
    monetaire = [marche(n, 10, 0.0005, 0.0001), marche(n, 11, 0.0005, 0.0001)]
    ref = marche(n, 20, 0.015)
    return Donnees([None] * n, noms, cloture, [list(x) for x in cloture], monetaire, [list(x) for x in monetaire], ref, list(ref))


def test_volatilite_et_diversification_identiques_a_celles_du_moteur():
    """Même fenêtre (180 dernières semaines), même écart-type : les chiffres du simulateur égalent `moteur._ex_ante`."""
    d = donnees_synthetiques()
    w = [0.25, 0.25, 0.25, 0.25, 0.0]  # 3 ETF, monétaire n°1, monétaire n°2
    attendu = _ex_ante(d, Parametres(), w, len(d.cloture[0]) - 1, 0.1)
    series = d.cloture + d.monetaire_cloture
    codes = ["E0", "E1", "E2", "M1", "M2"]
    rend = {k: c.rendements_hebdo(s) for k, s in zip(codes, series)}
    lignes = [ligne(k, p, "etf_actions", secteur=k) for k, p in zip(codes, w)] + [ligne("CASH", 0.0, "cash")]
    r = c.risque(lignes, rend)
    assert r.semaines == attendu["ex_ante_semaines"] == 180
    assert r.vol_ex_ante == pytest.approx(attendu["vol_ex_ante"], rel=1e-12)
    assert r.diversification == pytest.approx(attendu["diversification"], rel=1e-12)


def test_contributions_au_risque_somment_a_un_et_beta_de_la_reference_vaut_un():
    d = donnees_synthetiques()
    codes = ["E0", "E1", "E2"]
    rend = {k: c.rendements_hebdo(s) for k, s in zip(codes, d.cloture)}
    rend["REF"] = c.rendements_hebdo(d.reference_cloture)
    lignes = [ligne("E0", 0.5, "etf_actions"), ligne("E1", 0.3, "etf_actions"), ligne("E2", 0.1, "etf_actions"),
              ligne("CASH", 0.1, "cash")]
    r = c.risque(lignes, rend, rend["REF"])
    assert sum(r.contributions.values()) == pytest.approx(1.0)
    pur = [ligne("REF", 1.0, "etf_actions"), ligne("CASH", 0.0, "cash")]
    assert c.risque(pur, rend, rend["REF"]).beta == pytest.approx(1.0)
    moitie = [ligne("REF", 0.5, "etf_actions"), ligne("CASH", 0.5, "cash")]
    assert c.risque(moitie, rend, rend["REF"]).beta == pytest.approx(0.5)


def test_une_seule_ligne_ratio_de_diversification_egal_un():
    rend = {"A": c.rendements_hebdo(marche(100, 1))}
    assert c.risque([ligne("A", 0.6, "etf_actions"), ligne("CASH", 0.4, "cash")], rend).diversification == pytest.approx(1.0)


def test_diversifier_reduit_la_volatilite():
    rend = {"A": c.rendements_hebdo(marche(120, 1)), "B": c.rendements_hebdo(marche(120, 2))}
    seule = c.risque([ligne("A", 1.0, "etf_actions")], rend)
    mixte = c.risque([ligne("A", 0.5, "etf_actions"), ligne("B", 0.5, "etf_actions")], rend)
    assert mixte.vol_ex_ante < seule.vol_ex_ante and mixte.diversification > 1.0


def test_risque_historique_insuffisant_ou_absent():
    rend = {"A": c.rendements_hebdo(marche(20, 1))}
    with pytest.raises(c.ErreurComposition, match="semaines communes"):
        c.risque([ligne("A", 1.0, "etf_actions")], rend)
    with pytest.raises(c.ErreurComposition, match="Pas d'historique"):
        c.risque([ligne("B", 1.0, "etf_actions")], rend)
    with pytest.raises(c.ErreurComposition, match="Aucune ligne"):
        c.risque([ligne("CASH", 1.0, "cash")], rend)


def test_indicateurs_signalent_une_estimation_et_le_hhi_approche(cible):
    ind = c.indicateurs(cible, {})
    assert "non publiées" in ind["note"] and "approximation" in ind["hhi_note"]
    assert ind["risque"] is None and "Pas d'historique" in ind["risque_erreur"]
    assert ind["hhi"] == pytest.approx(0.05395) and ind["exposition_nette"] == pytest.approx(0.815)


# --- Corrélations -------------------------------------------------------------------------------------


def test_matrice_de_correlation_et_alertes():
    base = c.rendements_hebdo(marche(200, 1))
    rend = {"A": base, "B": [None if v is None else v * 2 for v in base],
            "C": c.rendements_hebdo(marche(200, 3)), "D": [None if v is None else -v for v in base]}
    res = c.correlations(rend, ["A", "B", "C", "D"], 52)
    i = {k: n for n, k in enumerate(res["codes"])}
    m = res["matrice"]
    assert m[i["A"]][i["B"]] == pytest.approx(1.0) and m[i["A"]][i["D"]] == pytest.approx(-1.0)
    assert all(m[k][k] == 1.0 for k in range(4))
    assert all(m[a][b] == pytest.approx(m[b][a]) for a in range(4) for b in range(4))
    assert res["semaines"] == 52
    assert [(p["a"], p["b"]) for p in res["alertes"]] == [("A", "B")]
    assert c.correlations(rend, ["A", "B", "C"], 180)["semaines"] == 180


def test_correlations_ecartent_les_lignes_sans_historique():
    rend = {"A": c.rendements_hebdo(marche(200, 1)), "B": c.rendements_hebdo(marche(200, 2)),
            "C": [None] * 190 + [0.01] * 10}
    res = c.correlations(rend, ["A", "B", "C", "Z"], 52)
    assert res["codes"] == ["A", "B"] and set(res["exclus"]) == {"C", "Z"}
    with pytest.raises(c.ErreurComposition, match="52 ou 180"):
        c.correlations(rend, ["A", "B"], 100)


# --- Remplacement d'une ligne --------------------------------------------------------------------------


def monde():
    rend = {k: c.rendements_hebdo(marche(200, i)) for i, k in enumerate(["A", "B", "C", "N"], 1)}
    ref = c.rendements_hebdo(marche(200, 99, 0.012))
    lignes = [ligne("A", 0.4, "etf_actions", secteur="S1", scenario="A"), ligne("B", 0.3, secteur="S2", scenario="B"),
              ligne("C", 0.2, secteur="S3", scenario="C"), ligne("CASH", 0.1, "cash", secteur="Cash", scenario="C")]
    return lignes, rend, ref


def test_remplacer_par_la_meme_ligne_ne_change_rien():
    lignes, rend, ref = monde()
    cand = c.Ligne("N", "N", "Convictions", "action", "N.PA", None, "S2", "B", 0.3)
    rend["N"] = rend["B"]
    res = c.simuler_remplacement(lignes, rend, ref, "B", cand, rend["N"], [])
    assert all(v == pytest.approx(0, abs=1e-12) for v in res["ecarts"].values() if v is not None)
    assert res["changements_de_statut"] == []
    assert res["candidat_correlations"][0]["code"] in {"A", "C"} and res["semaines"] == 180


def test_remplacement_poids_different_passe_par_le_cash():
    lignes, rend, ref = monde()
    cand = c.Ligne("N", "N", "Convictions", "action", "N.PA", None, "S2", "B", 0.1)
    apres = c.remplacer(lignes, "B", cand)
    assert next(l for l in apres if l.type == "cash").poids == pytest.approx(0.3)
    assert sum(l.poids for l in apres) == pytest.approx(1.0)
    gros = c.Ligne("N", "N", "Convictions", "action", "N.PA", None, "S2", "B", 0.45)
    with pytest.raises(c.ErreurComposition, match="cash ne suffit pas"):
        c.remplacer(lignes, "B", gros)
    with pytest.raises(c.ErreurComposition, match="introuvable"):
        c.remplacer(lignes, "ZZZ", cand)
    with pytest.raises(c.ErreurComposition, match="déjà dans le portefeuille"):
        c.remplacer(lignes, "B", c.Ligne("C", "C", "Convictions", "action", "C.PA", None, "S3", "C", 0.1))


def test_simulation_expose_volatilite_et_correlations_sans_rendement():
    lignes, rend, ref = monde()
    cand = c.Ligne("N", "N", "Convictions", "action", "N.PA", None, "S9", "B", 0.3)
    res = c.simuler_remplacement(lignes, rend, ref, "B", cand, rend["N"], [])
    assert res["candidat_vol"] > 0 and {x["code"] for x in res["candidat_correlations"]} == {"A", "C"}
    assert set(res["ecarts"]) == set(c.COLONNES_ECARTS)
    texte = repr(res).lower()
    assert "sharpe" not in texte and "perf" not in texte and "rendement" in texte  # « rendement » n'apparaît que dans la note
    assert "ne recommande aucun achat" in res["note"]


def test_simulation_detecte_changement_de_statut_et_historique_court():
    lignes, rend, ref = monde()
    cand = c.Ligne("N", "N", "Convictions", "action", "SAP.DE", None, "S2", "B", 0.3)
    res = c.simuler_remplacement(lignes, rend, ref, "B", cand, rend["N"], [])
    assert any(x["id"] == "places" and x["apres"] == c.HORS_REGLE for x in res["changements_de_statut"])
    court = [None] * 190 + [0.01] * 10
    with pytest.raises(c.ErreurComposition, match="semaines communes"):
        c.simuler_remplacement(lignes, rend, ref, "B", cand, court, [])


def test_controles_du_candidat():
    ok = {x["id"]: x["statut"] for x in c.controles_candidat("PRY.MI", True, 300, 107.0)}
    assert set(ok.values()) == {c.CONFORME}
    mauvais = {x["id"]: x["statut"] for x in c.controles_candidat("PENNY.PA", True, 30, 0.4)}
    assert mauvais["historique"] == c.HORS_REGLE and mauvais["penny"] == c.HORS_REGLE and mauvais["place"] == c.CONFORME
    assert {x["id"]: x["statut"] for x in c.controles_candidat("SAP.DE", True, 300, 100.0)}["place"] == c.HORS_REGLE
    inconnu = c.controles_candidat("ZZZZ.PA", False, 0, None)
    assert len(inconnu) == 1 and inconnu[0]["statut"] == c.HORS_REGLE


def test_ligne_moteur_suit_la_decision():
    nouvelles = c.portefeuille_cible(["Banques", "Défense", "Santé", "Monétaire n°1"])
    moteur = [l for l in nouvelles if l.poche == "Moteur"]
    assert [l.code for l in moteur] == ["BNK", "DEFS", "HLT", "CSH2"]
    assert moteur[3].type == "etf_monetaire" and moteur[0].scenario == ""  # « à définir » pour Banques
    assert sum(l.poids for l in nouvelles) == pytest.approx(1.0)
    assert c.poids_scenarios(nouvelles)[""] == pytest.approx(0.08 * 3)  # BNK, DEFS, CSH2 sans scénario
    with pytest.raises(c.ErreurComposition):
        c.portefeuille_cible(["Licornes"])


def test_les_symboles_du_moteur_viennent_de_univers():
    par_nom = {n: s for n, s, _, _ in SERIES}
    for l in c.portefeuille_cible():
        if l.poche == "Moteur":
            assert l.symbole == par_nom[l.nom]
