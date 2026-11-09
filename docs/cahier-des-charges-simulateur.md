# Cahier des charges : simulateur du portefeuille complet

Ce document se suffit à lui-même. Lis aussi `docs/cahier-des-charges-site.md` et `README.md` : le site existe déjà et fonctionne. On le complète, on ne le refait pas.

## 1. Pourquoi

- **Limite actuelle :** le site ne couvre que le « moteur », soit 4 ETF et 32 % du portefeuille, et il le compare au STOXX 600.
- **Ce qui compte dans le jeu :** le classement de l'Euronext Trading Game ne récompense pas le seul fait de battre le STOXX 600. Il note :
  - la performance brute ;
  - la performance ajustée du risque (performance / volatilité ex-ante sur 180 semaines) ;
  - le HHI ;
  - le nombre de secteurs ;
  - le ratio de diversification ;
  - le respect des règles UCITS.

  Les pondérations ne sont pas publiées.
- **But :** aider l'équipe à choisir et remplacer des lignes en mesurant leur effet sur le risque, la diversification et les règles. **Le simulateur ne prévoit aucun cours** et ne doit jamais afficher de prévision de rendement.

## 2. Ce qui existe déjà (à réutiliser, pas à réécrire)

| Élément | Où |
|---|---|
| Règles du moteur, mesures, backtest | `src/etg_moteur/moteur.py`. **Ne pas modifier la logique.** |
| Décision du mois | `src/etg_moteur/application.py`, `service.lancer_decision` |
| Téléchargement Yahoo et construction des prix hebdomadaires | `src/etg_moteur/prix.py` |
| Stockage privé (Vercel Blob en production, dossier local en test) | `src/etg_moteur/stockage.py` |
| API FastAPI, connexion par mot de passe, Cron | `api/index.py`, `src/etg_moteur/session.py` |
| Calculs du site | `src/etg_moteur/service.py` |
| Export Excel (tableau de bord, graphiques natifs) | `src/etg_moteur/excel.py` |
| Interface noir, blanc et orange, sans framework | `public/` |
| Tests (59 verts) | `tests/` |

`src/etg_moteur/portefeuille.py` existe déjà : il simule la dérive de la poche moteur. Place le nouveau code dans un nouveau module, par exemple `src/etg_moteur/composition.py`.

Le site est en production sur https://etg-moteur.vercel.app (projet Vercel `etg-moteur`, équipe `yoshis-projects-c446e364`). Le dépôt GitHub `yoshiijoe/etg-moteur` est **public**.

## 3. Le portefeuille de référence

Source : page « Stratégie » du Notion de l'équipe, lue le 04/11/2026. Ordres du 01/11, exécutés le 02/11. Base de 200 000 €.

| Poche | Code | Nom | Place | ISIN connu | Poids cible | Scénario |
|---|---|---|---|---|---|---|
| Moteur | HLT | Amundi STOXX Europe 600 Healthcare | Paris | LU1834986900 | 8 % | C |
| Moteur | TNO | Amundi STOXX Europe 600 Technology | Paris | LU1834988518 | 8 % | B |
| Moteur | ENRG | Amundi STOXX Europe 600 Energy | Paris | LU1834988278 | 8 % | A |
| Moteur | FOO | Amundi STOXX Europe 600 Consumer Staples | Paris | LU1834985845 | 8 % | C |
| Socle | 500 | Amundi S&P 500 | Paris | LU1681048804 | 4,5 % | B |
| Socle | AEEM | Amundi MSCI Emerging Markets | Paris | LU1681045370 | 4,5 % | B |
| Socle | EJAP | BNP Paribas Easy MSCI Japan | Paris | LU1291102447 | 4,5 % | B |
| Socle | EVOE | BNP Paribas Easy Low Volatility Europe | Paris | à trouver | 4,5 % | C |
| Socle | MTA | Amundi Euro Government Bond 1-3Y | Paris | LU1650487413 | 4,5 % | C |
| Socle | SHC | Amundi CAC 40 Daily (−1x) Inverse | Paris | FR0010591362 | 4,5 % | C |
| Convictions | ENX | Euronext | Paris | — | 4,5 % | A (et C) |
| Convictions | GALP | Galp | Lisbonne | — | 4,5 % | A |
| Convictions | NN | NN Group | Amsterdam | — | 4,5 % | A (et C) |
| Convictions | PRY | Prysmian | Milan | — | 4,5 % | B |
| Convictions | KRX | Kingspan | Dublin | — | 4,5 % | B (et A) |
| Convictions | LDO | Leonardo | Milan | — | 4,5 % | A |
| Convictions | UCB | UCB | Bruxelles | — | 4,5 % | C |
| Convictions | MOWI | Mowi | Oslo (NOK) | — | 4,5 % | C |
| Cash | — | Cash | — | — | 5 % | C |

**Ce que le simulateur doit prendre en compte :**

- **Poche moteur :** elle suit la décision du mois du site. Si le moteur change d'ETF, les lignes du moteur changent.
- **Scénarios :**
  - Le scénario d'une ligne, c'est sa **première lettre**, comme dans le Notion.
  - Les autres ETF du moteur n'ont pas encore de scénario défini (Banques, Défense, Industrie, Matières premières, Télécoms, Services publics). Affiche-les comme « à définir », modifiables dans le site.
- **À rendre modifiable dans le site :** les symboles, ISIN, secteurs et scénarios.
- **À ne pas inventer :** les symboles Yahoo sont à vérifier un par un, par ISIN et par nom. Propositions à contrôler : `ENX.PA`, `GALP.LS`, `NN.AS`, `PRY.MI`, `KRX.IR`, `LDO.MI`, `UCB.BR`, `MOWI.OL`, `500.PA`, `AEEM.PA`, `EJAP.PA`, `EVOE.PA`, `MTA.PA`, `SHC.PA`.
- **Mowi :** convertir son cours en euros avec `EURNOK=X`.

## 4. Règles du jeu et de l'équipe à contrôler

| Règle | Source | Seuil |
|---|---|---|
| Une ligne | UCITS, règlement ETG | ≤ 10 % |
| Somme des lignes au-dessus de 5 % | UCITS, règlement ETG | ≤ 40 % |
| Un refuge monétaire | Stratégie | ≤ 8 % |
| Un secteur, ETF et action cumulés | Stratégie | ≤ 15 % |
| Actions par secteur | Stratégie | 1 au maximum |
| Poids de chaque scénario A, B, C | Stratégie | entre 25 % et 45 % |
| Places autorisées | Règlement | Paris, Amsterdam, Bruxelles, Lisbonne, Milan, Oslo, Dublin (suffixes `.PA .AS .BR .LS .MI .OL .IR`) |
| Penny stocks | Règlement | exclus : alerter si le cours est sous 1 € (seuil indicatif, définition officielle non publiée) |

**Secteurs :**
- Le jeu compte les secteurs selon la classification ICB.
- Mets un secteur par défaut à chaque ligne, avec la mention « à vérifier », et laisse l'utilisateur le corriger.
- Pour le HHI, le jeu regarde à l'intérieur des ETF. Le simulateur compte un ETF comme une ligne : c'est une **approximation**, à écrire à côté du chiffre.

## 5. Fonctions à ajouter

### 5.1 Positions réelles

- **Saisie :** un tableau où l'on saisit, pour chaque ligne, le nombre de titres détenus, plus le cash restant. Les poids actuels sont calculés avec les derniers cours.
- **Stockage :** enregistré dans le stockage privé existant, dans un JSON séparé des prix.
- **Si rien n'est saisi :** utiliser les poids cibles de la section 3, avec la mention « poids cibles ».
- **Sauvegardes :** garder un historique des 10 dernières versions.

### 5.2 Indicateurs du portefeuille

Chaque indicateur affiche un état clair : conforme, attention ou hors règle.

**Estimations du classement :**
- **Volatilité ex-ante sur 180 semaines :** poids actuels appliqués aux rendements hebdomadaires passés de chaque ligne.
- **Performance ajustée :** la performance du portefeuille réel depuis le 02/11/2026, si les positions sont saisies, divisée par la volatilité ex-ante.
- **Concentration et diversification :** HHI (cash exclu, ETF comptés comme une ligne), nombre de secteurs, ratio de diversification (somme des poids × volatilités / volatilité du portefeuille).

**Exposition :**
- **Bêta et exposition nette :** le bêta par rapport au STOXX 600, et l'exposition nette aux actions, c'est-à-dire les actions et ETF actions moins l'ETF inverse, hors obligations et cash.
- **Contribution au risque de chaque ligne :** sa part dans la volatilité totale, présentée sous forme de barres.
- **Scénarios A, B et C :** le poids de chacun, comparé à la fourchette de 25 à 45 %.

**Règles :** tous les contrôles de la section 4.

Écrire à côté des estimations : « estimation : formules et pondérations du jeu non publiées ».

### 5.3 Corrélations

- **Contenu :** une matrice de corrélation des rendements hebdomadaires entre toutes les lignes, sur 52 ou 180 semaines au choix.
- **Couleurs :** une échelle du blanc à l'orange, ou du noir à l'orange en thème sombre.
- **Alertes :** la liste des paires au-dessus de 0,7, par exemple l'ETF Technologie avec une action tech.

### 5.4 « Et si je remplace… »

- **Saisie :** une ligne à remplacer, un symbole candidat et un poids, par défaut celui de la ligne remplacée.
- **Contrôles du candidat :**
  - le symbole existe ;
  - il est coté sur une place autorisée ;
  - il a assez d'historique, au moins 52 semaines ;
  - son cours n'est pas sous 1 €.
- **Affichage :** un tableau avant / après avec les écarts de tous les indicateurs de 5.2, ainsi que la volatilité du candidat et sa corrélation avec chaque ligne restante.
- **Ce qui est interdit :** aucun rendement passé ou futur présenté comme argument de choix. On compare le risque et la diversification, pas la performance.
- **Plusieurs candidats :** permettre d'en comparer jusqu'à 3 côte à côte.

### 5.5 Deuxième référence du backtest

- **Ajout :** une référence « 10 ETF à parts égales », rééquilibrée chaque mois avec les mêmes dates et le même prix d'exécution que le moteur. Elle répond à la question : « Choisir 4 ETF rapporte-t-il plus que de garder les 10 ? »
- **Règle de calcul :**
  - Avant juillet 2023, la Défense n'a pas de prix : on répartit à parts égales entre les ETF disponibles.
  - Code : écris la fonction dans un nouveau module ou dans `service.py`, sans toucher à `moteur.py`.
- **Affichage :** une troisième courbe sur le site, en pointillés gris clair, une ligne dans le tableau des variantes et les mêmes ajouts dans l'Excel.

### 5.6 Interface

- **Accès :** ajoute une navigation en haut, « Moteur » et « Portefeuille », avec des adresses `#moteur` et `#portefeuille`.
- **Page Portefeuille :** positions, indicateurs, corrélations, puis simulation de remplacement.
- **Style :** garde exactement celui du site (variables CSS, polices, orange réservé aux éléments actifs).
- **Téléphone :** les tableaux défilent horizontalement dans leur conteneur.

### 5.7 Excel

Ajoute les onglets suivants, avec les mêmes chiffres que la page :
- `Portefeuille` : lignes, poids, secteur, scénario, contrôles ;
- `Indicateurs` ;
- `Correlations` : une mise en forme conditionnelle orange ;
- `Simulation` : la dernière simulation affichée.

Le tableau de bord garde sa place en premier onglet.

## 6. Chiffres de contrôle (poids cibles de la section 3)

| Mesure | Attendu |
|---|---|
| Total des poids | 100 % |
| Scénario A / B / C | 26,0 % / 30,5 % / 43,5 % |
| Lignes au-dessus de 5 % | 32 % (les 4 ETF du moteur) |
| HHI, cash exclu | 0,05395 |
| Exposition nette aux actions | 81,5 % |
| Ligne la plus lourde | 8 % |

Ces chiffres correspondent à ceux de la page « Stratégie » du Notion. Ajoute-les en tests automatiques.

## 7. Ordre de travail

1. **Préparation :**
   - lire les fichiers de la section 2 ;
   - lancer `pytest` (59 tests verts attendus) ;
   - créer une branche `simulateur` à partir de `main`.
2. **Symboles :** vérifier les symboles Yahoo de la section 3, par ISIN et par nom, et me présenter la liste avant d'aller plus loin. Signaler toute ligne introuvable.
3. **Module `composition.py` et ses tests :** indicateurs, contrôles, corrélations, simulation et chiffres de la section 6.
4. **Prix :** étendre le téléchargement et le stockage des prix aux 14 nouvelles lignes, sans changer le CSV du moteur.
5. **API :** routes `/api/portefeuille` (lecture et enregistrement des positions), `/api/indicateurs`, `/api/correlations`, `/api/simulation`, toutes protégées par la connexion.
6. **Référence à parts égales :** l'ajouter (section 5.5) et la tester.
7. **Interface :** page Portefeuille, puis vérification en local.
8. **Excel :** onglets supplémentaires, puis vérification en ouvrant le fichier dans Excel.
9. **Prévisualisation :** déployer avec `vercel deploy`, sans `--prod`, et me donner l'adresse pour tester.
10. **Production et GitHub :** seulement avec mon accord.

## 8. Règles strictes

- **Calculs existants :** ne modifie pas la logique de `moteur.py`, et ne change aucun chiffre déjà affiché par le site.
- **Ce qui ne va jamais dans git :** prix, positions, résultats, secrets. Le dépôt est public.
- **Avant toute action irréversible :** demande-moi avant la mise en production, avant un push sur `main`, ou avant de créer un service Vercel payant.
- **Formulation :** pas de « recommandation d'achat ». Le simulateur mesure, l'équipe décide.
- **Compte rendu final :**
  - adresse de la prévisualisation ;
  - ce qui marche ;
  - ce qui n'a pas pu être vérifié, en particulier les symboles et les secteurs ;
  - chiffres de contrôle obtenus.
