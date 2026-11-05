# Protocole de backtest : brouillon du 05/11/2026

À valider par le Portfolio Manager. Les choix ci-dessous sont des propositions.

## Protocole de test

| Rubrique | Proposition |
|---|---|
| Période d'entraînement | 02/01/2009 au 29/12/2017 |
| Hors échantillon | 05/01/2018 au dernier vendredi disponible. Ces années ont déjà été regardées : le test n'est pas à l'aveugle |
| Vrai hors échantillon | Les semaines à partir du 02/11/2026, début du déploiement |
| Rééquilibrage | Mensuel : signal à la clôture du dernier vendredi, exécution à l'ouverture du lundi |
| Mi-mois | Une ligne du moteur au-dessus de 9 % revient à 8 % ; excédent en cash |
| Coûts | 0, selon le règlement noté. À confirmer par le Trader |
| Contraintes | Ligne ≤ 10 %, lignes > 5 % ≤ 40 %, refuge ≤ 8 %. Le secteur ≤ 15 % n'est pas testable sur la poche seule |
| Référence | ETF iShares STOXX Europe 600, dividendes réinvestis |
| Taux sans risque | 2,5 %, constant sur toute la période (simplification) |

## Règle de décision, à fixer avant de relancer sur les prix validés

Une variante ne remplace la base que si toutes ces conditions sont réunies :

1. Elle fait mieux sur l'entraînement et sur le hors échantillon.
2. Elle reste meilleure quand on fait varier ses voisins dans la grille de paramètres.
3. Sa perte maximale n'est pas plus de 5 points pire que celle de la base.
4. L'équipe sait expliquer pourquoi elle marcherait, en plus du résultat chiffré.

## Métriques

Rendement annualisé, volatilité, Sharpe, perte max, rotation, HHI, bêta, volatilité ex-ante, performance sur volatilité ex-ante, ratio de diversification.

## Pièges

| Piège | Ce qu'on fait | Ce qui reste |
|---|---|---|
| Regard vers le futur | Décision à la clôture du vendredi, exécution le lundi ; test automatique | Univers choisi en 2026 |
| Survivant | Indices sectoriels larges, pas d'actions choisies | La Défense a été ajoutée après sa forte hausse |
| Sur-ajustement | Variantes une par une, grille complète publiée, règle de décision fixée d'avance | Plus on teste de combinaisons, plus la meilleure est flatteuse |
| Données | Fonds proches signalés, cours contrôlés | Énergie et Agroalimentaire moins bien représentés ; Défense incomplète |

## Questions pour le Portfolio Manager

1. Faut-il compter 13 et 26 semaines, ou 3 et 6 mois calendaires ?
2. Ces périodes et cette règle de décision conviennent-elles ?
3. Les stress tests du portefeuille entier sont-ils à faire ?
4. Faut-il rendre quelque chose de précis, et sous quel format ?
