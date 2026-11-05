"""Simulation plus réaliste de la poche dans le portefeuille : dérive, mi-mois, limites UCITS.

Hypothèses (à valider avec le Trader) :
- le moteur pèse 32 % (4 × 8 %), le reste du portefeuille est résumé par 63 % de référence
  STOXX Europe 600 et 5 % de cash, car ses 14 lignes ne sont pas simulées ;
- rééquilibrage complet aux poids cibles le lundi suivant le dernier vendredi du mois ;
- réunion de mi-mois : le vendredi entre le 11 et le 17, décision sur la clôture, exécution
  à l'ouverture du lundi. Une ligne du moteur au-dessus de 9 % revient à 8 %, l'excédent reste en cash ;
- UCITS mesuré chaque vendredi sur les lignes du moteur seulement.
"""
from __future__ import annotations

import datetime as dt

from .moteur import Donnees, Parametres, decider, mesures

POIDS_MOTEUR = 0.32
POIDS_RESTE = 0.63
POIDS_CASH = 0.05
SEUIL_HAUT = 0.09
RETOUR = 0.08
LIMITE_LIGNE = 0.10
LIMITE_GROSSES = 0.40
SEUIL_GROSSE = 0.05


def est_mi_mois(d: dt.date) -> bool:
    return 11 <= d.day <= 17


def simuler(d: Donnees, p: Parametres, debut: dt.date, fin: dt.date, mi_mois: bool = True) -> dict:
    A = len(d.noms)
    poids, reeq = decider(d, p)
    idx = [t for t in range(len(d.dates)) if debut <= d.dates[t] <= fin]
    cible = POIDS_MOTEUR / p.top

    def cibler(t: int, total: float) -> tuple[list, list, float, float]:
        w = poids[t]
        lignes = [total * cible * (1 if w[i] > 0 else 0) for i in range(A)]
        refuges = [total * cible * (1 if w[A + k] > 0 else 0) for k in range(2)]
        poche = sum(lignes) + sum(refuges)
        return lignes, refuges, total * POIDS_RESTE, total * (POIDS_MOTEUR + POIDS_CASH) - poche

    t0 = idx[0]
    lignes, refuges, reste, cash = cibler(t0, 1.0)
    poche_av = sum(lignes) + sum(refuges) + (cash - POIDS_CASH)
    rend_poche, rend_port, coupes, max_ligne = [], [], 0, 0.0
    sem_90, sem_100, max_grosses, sem_40, tot_av = 0, 0, 0.0, 0, 1.0
    for t in idx[1:]:
        # Clôture du vendredi t : elle sert à la décision de mi-mois et aux contrôles UCITS
        val_clo = [lignes[i] * d.cloture[i][t] / d.ouverture[i][t - 1] if lignes[i] else 0.0 for i in range(A)]
        ref_clo = [refuges[k] * d.monetaire_cloture[k][t] / d.monetaire_ouverture[k][t - 1] if refuges[k] else 0.0 for k in range(2)]
        reste_clo = reste * d.reference_cloture[t] / d.reference_ouverture[t - 1]
        tot_clo = sum(val_clo) + sum(ref_clo) + reste_clo + cash
        w_clo = [v / tot_clo for v in val_clo]
        max_ligne = max(max_ligne, max(w_clo))
        sem_90 += any(x > SEUIL_HAUT for x in w_clo)
        sem_100 += any(x > LIMITE_LIGNE for x in w_clo)
        grosses = sum(x for x in w_clo + [v / tot_clo for v in ref_clo] if x > SEUIL_GROSSE)
        max_grosses = max(max_grosses, grosses)
        sem_40 += grosses > LIMITE_GROSSES

        # Ouverture du lundi t : c'est le prix d'exécution
        lignes = [lignes[i] * d.ouverture[i][t] / d.ouverture[i][t - 1] if lignes[i] else 0.0 for i in range(A)]
        refuges = [refuges[k] * d.monetaire_ouverture[k][t] / d.monetaire_ouverture[k][t - 1] if refuges[k] else 0.0 for k in range(2)]
        reste = reste * d.reference_ouverture[t] / d.reference_ouverture[t - 1]
        total = sum(lignes) + sum(refuges) + reste + cash
        poche = sum(lignes) + sum(refuges) + (cash - POIDS_CASH * tot_av)
        rend_poche.append(poche / poche_av - 1)
        rend_port.append(total / tot_av - 1)
        if reeq[t]:
            lignes, refuges, reste, cash = cibler(t, total)
        elif mi_mois and est_mi_mois(d.dates[t]):
            for i in range(A):
                if w_clo[i] > SEUIL_HAUT:
                    excedent = lignes[i] - RETOUR * total
                    if excedent > 0:
                        lignes[i] -= excedent
                        cash += excedent
                        coupes += 1
        tot_av = total
        poche_av = sum(lignes) + sum(refuges) + (cash - POIDS_CASH * total)
    m = mesures(rend_poche, p.taux_sans_risque)
    m.update(portefeuille=mesures(rend_port, p.taux_sans_risque), coupes_mi_mois=coupes, poids_max_ligne=max_ligne,
             semaines_au_dessus_9=sem_90, semaines_au_dessus_10=sem_100, grosses_lignes_max=max_grosses,
             semaines_au_dessus_40=sem_40, semaines=len(rend_poche), rendements=rend_poche)
    return m
