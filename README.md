# etg-moteur

Backtest du moteur momentum de la stratégie « Socle & Moteur » v0.1, pour l'Euronext Trading Game 2026-2027.

## Règles testées

- Univers : 10 ETF sectoriels européens capitalisants.
- Signal : moyenne des performances sur 13 et 26 semaines, à la clôture du vendredi.
- Sélection : les 4 meilleurs à poids égaux. Une ligne détenue n'est vendue que si elle sort du top 6.
- Filtre : une ligne retenue dont le signal est négatif est remplacée par un ETF monétaire, puis un second, puis du cash.
- Rééquilibrage : dernier vendredi du mois, exécution à l'ouverture du lundi suivant.

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Utilisation

```bash
.venv/bin/python scripts/telecharger_prix.py
.venv/bin/python scripts/construire_prix.py
.venv/bin/python scripts/lancer_tests.py
.venv/bin/python -m pytest
```

Pour savoir ce que la règle demande ce mois-ci, à partir des détentions actuelles :

```bash
.venv/bin/python scripts/construire_prix.py 2026-11-27
.venv/bin/python scripts/signal_du_mois.py --detenus "Santé,Technologie,Pétrole & gaz,Agroalimentaire"
```

Avant le dernier vendredi du mois, le résultat n'est qu'un aperçu.

`lancer_tests.py` écrit ses résultats dans `resultats/rapport.json`. Pour comparer le moteur au classeur Excel de l'équipe, enregistré par Excel :

```bash
.venv/bin/python scripts/verifier_excel.py "classeur.xlsx"
```

## Site (Vercel)

Un site protégé par mot de passe permet de mettre à jour les prix, lancer le backtest, voir la décision du mois et télécharger un Excel. Le cahier des charges est dans `docs/cahier-des-charges-site.md`.

- `public/` : page unique (HTML, CSS, JavaScript simples, graphiques SVG).
- `api/index.py` : API FastAPI (connexion, état, prix, Cron, import CSV, backtest, décision, Excel) qui appelle le paquet `etg_moteur`.
- `src/etg_moteur/prix.py` : téléchargement Yahoo et construction du CSV hebdomadaire (les scripts `telecharger_prix.py` et `construire_prix.py` l'utilisent aussi).
- Les prix sont rangés dans un Vercel Blob **privé** (`prix/AAAAMMJJTHHMMSSZ_yahoo.csv` ou `_import.csv`, les 3 dernières versions). Rien n'est dans git.

Variables d'environnement Vercel (jamais dans le code) : `SITE_PASSWORD`, `SESSION_SECRET`, `CRON_SECRET`, et `BLOB_READ_WRITE_TOKEN` (posée par Vercel quand le Blob est relié au projet).

Essayer en local :

```bash
.venv/bin/pip install -r requirements-dev.txt
cp data/prix_hebdo.csv .dev-stockage/prix/20261109T000000Z_import.csv   # optionnel : ou « Importer un CSV » dans la page
.venv/bin/python scripts/serveur_local.py   # http://localhost:8765, mot de passe local : « local » (ETG_DEV_PASSWORD)
```

Changer le mot de passe du site : `vercel env rm SITE_PASSWORD production`, puis `vercel env add SITE_PASSWORD production --sensitive` et redéployer (`vercel deploy --prod`). Changer `SESSION_SECRET` déconnecte tout le monde.

Si Yahoo bloque les serveurs Vercel (erreurs 403 ou 429), importer le CSV depuis le Mac, avec le bouton « Importer un CSV » ou :

```bash
ETG_SITE_URL=https://mon-site.vercel.app .venv/bin/python scripts/envoyer_prix.py
```

Le Cron Vercel met les prix à jour en semaine à 17 h UTC (après la clôture d'Euronext, 18 h ou 19 h à Paris).

## Contenu

| Fichier | Rôle |
|---|---|
| `src/etg_moteur/moteur.py` | Règles du moteur et mesures |
| `src/etg_moteur/portefeuille.py` | Dérive des poids, règle de mi-mois, contrôles UCITS |
| `src/etg_moteur/application.py` | Décision du mois à partir des détentions |
| `src/etg_moteur/robustesse.py` | Sensibilité, hors échantillon, sélection glissante, bootstrap |
| `tests/test_moteur.py` | Tests des règles sur des prix synthétiques |
| `docs/protocole.md` | Brouillon du protocole de backtest |

## Limites

- Les prix (Yahoo Finance) ne sont pas dans le dépôt et n'ont pas encore été validés par l'équipe.
- Avant le lancement de chaque ETF, l'historique est prolongé par un fonds proche.
- L'historique complet de l'indice défense (SXDCR) manque : avant 07/2023, la Défense est absente.
- Aucun résultat n'est publié ici tant que ces points ne sont pas réglés.
- En cas de signaux strictement égaux, plusieurs lignes peuvent partager un rang, comme dans le classeur Excel.
