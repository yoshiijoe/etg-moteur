# Cahier des charges : site du moteur ETG

Ce document se suffit à lui-même : la personne qui code le site n'a pas d'autre contexte.

## 1. Contexte

- **Projet :** le dépôt `~/PycharmProjects/etg-moteur` (GitHub **public** `yoshiijoe/etg-moteur`) contient le backtest du « moteur » de la stratégie d'un club étudiant à l'Euronext Trading Game 2026-2027.
- **Règle du moteur :**
  - Chaque fin de mois, on classe 10 ETF sectoriels européens selon la moyenne de leur performance sur 13 et 26 semaines.
  - On garde les 4 premiers. Une ligne détenue n'est vendue que si elle sort du top 6.
  - Une ligne retenue dont le signal est négatif est remplacée par un ETF monétaire, puis un second, puis du cash.
- **But du site :** permettre à l'équipe de mettre à jour les prix, lancer le backtest, voir la décision du mois et télécharger un fichier Excel, sans toucher au terminal.
- **Langue :** l'interface est entièrement en français.

## 2. À lire avant de coder

| Fichier | Contenu |
|---|---|
| `README.md` | Utilisation actuelle |
| `src/etg_moteur/moteur.py` | `Parametres`, `Donnees`, `signal`, `rangs`, `selection`, `decider`, `mesures`, `backtest`. **Ne pas modifier la logique.** |
| `src/etg_moteur/application.py` | `dernier_vendredi(annee, mois)`, `decision(d, p, t, detenus)` |
| `src/etg_moteur/donnees.py` | `lire_hebdo(chemin, sans=())` lit `data/prix_hebdo.csv` |
| `src/etg_moteur/univers.py` | Les 13 séries, leurs symboles Yahoo et les fonds utilisés pour prolonger l'historique |
| `scripts/telecharger_prix.py` | Appelle l'API Yahoo et range le JSON brut dans `data/brut/` |
| `scripts/construire_prix.py` | Construit `data/prix_hebdo.csv` : clôture du vendredi et ouverture du lundi ajustées des dividendes, cours manquants, raccord des fonds proches, ouvertures à 0 remplacées par la clôture |
| `scripts/lancer_tests.py` | Variantes et tests de robustesse |
| `scripts/signal_du_mois.py` | Décision du mois |
| `tests/test_moteur.py` | 19 tests, tous verts |

Le modèle pour la mise en page Excel des prix est ce fichier, qui reprend la mise en page attendue par le classeur de backtest de l'équipe : `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/Projets/Euronext Trading Games/Données prix/Prix ETG - a coller dans le backtest.xlsx`.

**État git :** `main` a un commit local non poussé (`4eba924`). Travaille sur une branche `site`. Ne pousse rien et ne fusionne rien dans `main` sans l'accord de l'utilisateur.

## 3. Règles strictes

1. **Mêmes chiffres :** le site doit donner exactement les mêmes résultats que les scripts sur le même CSV.
2. **Pas de logique dupliquée :** l'API appelle le paquet `etg_moteur`. Pour télécharger et construire les prix en mémoire, déplace la logique des deux scripts dans un module `src/etg_moteur/prix.py`, que les scripts et le site utilisent tous les deux. Le CSV produit doit rester identique octet pour octet (à vérifier avec `diff`).
3. **Aucune donnée dans git :** `data/`, `resultats/`, `*.csv`, `*.xlsx` restent ignorés. Aucun secret dans le code : variables d'environnement Vercel uniquement.
4. **Site protégé :** la stratégie et les résultats ne doivent pas être lisibles sans mot de passe.
5. **Avertissements visibles :** chaque page et chaque Excel indiquent que les prix viennent de Yahoo, ne sont pas validés par l'équipe, et que la Défense n'a pas de données avant 07/2023.
6. **Vérifier la documentation :** contrôle dans la documentation Vercel actuelle (outil de recherche de la doc Vercel s'il est disponible) le runtime Python, les limites du plan Hobby, Cron et le stockage, avant de les utiliser. N'invente pas d'API.

## 4. Architecture proposée (à confirmer avec la doc)

- **Un seul projet Vercel à la racine du dépôt :**
  - `public/` contient `index.html`, `styles.css` et `app.js`, en JavaScript simple, sans framework.
  - `api/` contient les fonctions Python, ou une seule application FastAPI dans `api/index.py`, avec une réécriture `/api/(.*)`.
- **Import du paquet :** les fonctions doivent pouvoir importer `src/etg_moteur` (chemin ajouté au démarrage, et `includeFiles` dans `vercel.json` si nécessaire). Vérifie-le sur un déploiement de prévisualisation.
- **Dépendances :** `requirements.txt` ne garde que ce dont le site a besoin (`openpyxl`, et FastAPI si utilisé). `pytest` passe dans `requirements-dev.txt`.
- **Stockage des prix :** stocke le CSV hebdomadaire (environ 250 Ko) et un petit JSON d'état dans un stockage Vercel (Blob ou Redis du Marketplace), en accès non public. Le navigateur ne reçoit jamais l'adresse directe du fichier.
- **Mise à jour automatique :** un Cron Vercel quotidien, après la clôture d'Euronext (17 h 30, heure de Paris), télécharge les prix et reconstruit le CSV.
- **Si Yahoo bloque les serveurs Vercel** (erreurs 429 ou 403, à tester tôt) : ajouter un bouton « Importer un CSV » et un script local `scripts/envoyer_prix.py` qui envoie le `data/prix_hebdo.csv` du Mac au stockage. Le site doit fonctionner sans Yahoo.
- **Mot de passe :**
  - un formulaire compare l'entrée à `SITE_PASSWORD`, puis pose un cookie `HttpOnly`, `Secure`, `SameSite=Strict`, signé par HMAC avec `SESSION_SECRET` et valable 7 jours ;
  - chaque route `/api` le vérifie, sauf la connexion et le Cron, qui est protégé par `CRON_SECRET`.

## 5. Fonctions de l'API

| Route | Entrée | Sortie |
|---|---|---|
| `POST /api/connexion` | mot de passe | cookie de session |
| `GET /api/etat` | — | date de la dernière mise à jour des prix, dernier vendredi disponible, nombre de semaines, source |
| `POST /api/prix` | — | télécharge depuis Yahoo, reconstruit et stocke ; renvoie l'état, ou une erreur lisible |
| `POST /api/backtest` | début, fin, univers (10 ETF ou 9 sans Défense), court, long, avec ou sans court terme, top, tampon, filtre | mesures du moteur et du STOXX 600, séries hebdomadaires (valeur en base 100, perte depuis le sommet), poids, tableau des 5 variantes |
| `POST /api/decision` | vendredi (par défaut le dernier), ETF détenus | lignes de `decision()`, date officielle (`dernier_vendredi`), mention « aperçu » si besoin |
| `POST /api/excel` | mêmes paramètres que le backtest et la décision | fichier `.xlsx` en téléchargement |

**Valeurs par défaut :**
- **Backtest :** du 05/01/2024 au dernier vendredi, 10 ETF, 13 + 26 semaines, top 4, tampon 6, filtre activé.
- **ETF détenus :** Santé, Technologie, Pétrole & gaz, Agroalimentaire.

**Les 5 variantes :**

| Variante | Paramètres |
|---|---|
| Base | Valeurs par défaut |
| 6 mois seuls | `utiliser_court=False` |
| Top 3 | `top=3` |
| Sans filtre | `filtre=False` |
| Sans zone tampon | `tampon=4` |

## 6. Le fichier Excel (bouton « Télécharger l'Excel »)

- **Nom :** `moteur-etg-AAAA-MM-JJ.xlsx`. Il est généré avec openpyxl, sans formule, pour qu'il s'ouvre partout.
- **Mise en forme :** en-têtes en gras, figés, pourcentages formatés, dates au format jj/mm/aaaa.

**Onglets :**

| Onglet | Contenu |
|---|---|
| `Lisez-moi` | date, source, paramètres utilisés, avertissements |
| `Resultats` | mesures du moteur et du STOXX 600 : rendement annualisé, volatilité, Sharpe, perte max, rotation, HHI, bêta, volatilité ex-ante, ratio de diversification |
| `Variantes` | les 5 variantes, sur les mêmes colonnes |
| `Decision` | rang, ETF, 3 mois, 6 mois, signal, détenu, décision |
| `Serie` | date, valeur du moteur, valeur du STOXX 600, perte depuis le sommet |
| `Poids` | date, puis un poids par ETF et par refuge |
| `Prix_cloture` et `Prix_ouverture` | même mise en page que le fichier modèle cité plus haut (titres en lignes 3 à 5, données dès la ligne 6, colonnes A à N, 520 dernières semaines), pour pouvoir les coller dans le classeur de l'équipe |

## 7. Interface

**Direction :** un site épuré en noir, blanc et orange, qui fasse penser à un terminal de marché sobre.

**Couleurs :**
- **Thème clair :** fond blanc `#FFFFFF`, texte `#0A0A0A`, gris pour les traits et le texte secondaire.
- **Thème sombre :** fond `#0A0A0A`, texte `#FFFFFF`.
- **Orange `#FF5B00` :** seulement pour l'action principale, la courbe du moteur et l'état actif. La courbe du STOXX 600 est en gris.
- **Implémentation :** toutes les couleurs sont des variables CSS. Le thème suit `prefers-color-scheme` et offre un bouton clair / sombre.

**Typographie et mise en page :**
- **Polices :** Geist pour le texte, Geist Mono pour tous les chiffres, avec `font-variant-numeric: tabular-nums`, chargées depuis Google Fonts avec une police de secours.
- **Mise en page :** une seule colonne de 1 100 px au maximum, beaucoup d'air, des traits fins de 1 px. Pas d'ombres, pas de dégradés, pas d'emojis, coins à 2 px au maximum.
- **Écrans :** le site doit rester lisible sur téléphone, à 375 px. Les tableaux défilent horizontalement dans leur propre conteneur.

**Structure de la page :**
1. **Barre du haut :**
   - à gauche : « Moteur ETG » ;
   - à droite : « Prix au 06/11/2026 · Yahoo · non validés » et le bouton de thème.
2. **Barre d'actions :**
   - « Mettre à jour les prix » (secondaire) ;
   - « Lancer le backtest » (principal, en orange) ;
   - « Télécharger l'Excel » (secondaire).
   Chaque bouton affiche un état de chargement, puis un message court comme « Prix mis à jour au 06/11/2026 » ou l'erreur exacte.
3. **Décision du mois :**
   - le tableau rang, ETF, 3 mois, 6 mois, signal, détenu, décision ;
   - des cases à cocher pour les ETF détenus ;
   - une mention « Aperçu : décision officielle le 27/11/2026 » quand le vendredi utilisé n'est pas le dernier du mois.
   La décision est le contenu principal : place-la en premier.
4. **Backtest :**
   - les paramètres repliables ;
   - 4 chiffres clés (rendement par an, Sharpe, perte max, rotation) comparés au STOXX 600 ;
   - un graphique en base 100 (moteur en orange, STOXX 600 en gris) ;
   - un graphique de la perte depuis le sommet ;
   - le tableau des 5 variantes.
5. **Pied de page :** source, date, avertissements et lien vers le dépôt GitHub.

**Graphiques :** Chart.js 4 en version fixe depuis cdnjs, ou des SVG écrits à la main. Axes discrets, sans légende décorative.

## 8. Ordre de travail

1. **Préparation :**
   - lire les fichiers de la section 2 ;
   - créer `.venv` ;
   - lancer `pytest` (19 verts attendus) ;
   - créer la branche `site`.
2. **Module `prix.py` :**
   - extraire `src/etg_moteur/prix.py` ;
   - garder les scripts identiques en sortie (`diff` sur `data/prix_hebdo.csv`) ;
   - ajouter des tests.
3. **API en local :**
   - écrire l'API et les tests de l'API (connexion, backtest, décision, contenu de l'Excel) ;
   - vérifier les chiffres de référence de la section 9.
4. **Interface :** écrire l'interface et la tester en local avec `vercel dev`.
5. **Compte Vercel :** demander à l'utilisateur de se connecter (`vercel login`), de choisir le mot de passe du site et d'approuver la création du projet et du stockage. Ne crée rien de payant.
6. **Prévisualisation :**
   - déployer en prévisualisation ;
   - tester le téléchargement Yahoo depuis Vercel dès cette étape ;
   - mettre en place le repli de la section 4 si Yahoo bloque.
7. **Vérification sur la prévisualisation :**
   - connexion ;
   - mise à jour des prix ;
   - chiffres identiques à ceux en local ;
   - Excel qui s'ouvre ;
   - affichage sur téléphone et en thème sombre.
8. **Mise en production :** seulement avec l'accord de l'utilisateur. Commits sur la branche `site` ; pas de push sur `main` sans accord.
9. **Compte rendu :**
   - adresse du site ;
   - ce qui marche ;
   - ce qui n'a pas pu être testé ;
   - comment changer le mot de passe.

## 9. Chiffres de référence pour vérifier

Sur la copie actuelle de `data/prix_hebdo.csv` (prix Yahoo téléchargés le 09/11/2026, dernière ligne au 06/11/2026), avec 10 ETF, du 05/01/2024 au 30/10/2026 et les paramètres par défaut :

| Mesure | Valeur attendue |
|---|---|
| Rendement annualisé | 21,62 % |
| Sharpe | 1,0209 |
| Perte max | −17,69 % |
| Rotation | 1,592 |
| STOXX 600 | 14,56 % par an |

La rotation tombe à 1,415 si le CSV s'arrête au 30/10. C'est normal : le rééquilibrage du dernier vendredi n'est compté que s'il existe une semaine après lui.

Pour la décision du 30/10/2026 avec les ETF détenus Banques, Pétrole & gaz, Technologie et Matières premières, le résultat attendu est :
- acheter Santé et Agroalimentaire ;
- garder Technologie et Pétrole & gaz ;
- vendre Banques et Matières premières.

Si Yahoo révise ses historiques, ces chiffres peuvent bouger un peu. Dans ce cas, compare avec `scripts/lancer_tests.py` et `scripts/signal_du_mois.py` sur le même CSV.
