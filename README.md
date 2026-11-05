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

`lancer_tests.py` écrit ses résultats dans `resultats/rapport.json`. Pour comparer le moteur au classeur Excel de l'équipe, enregistré par Excel :

```bash
.venv/bin/python scripts/verifier_excel.py "classeur.xlsx"
```

## Contenu

| Fichier | Rôle |
|---|---|
| `src/etg_moteur/moteur.py` | Règles du moteur et mesures |
| `src/etg_moteur/portefeuille.py` | Dérive des poids, règle de mi-mois, contrôles UCITS |
| `src/etg_moteur/robustesse.py` | Sensibilité, hors échantillon, sélection glissante, bootstrap |
| `tests/test_moteur.py` | Tests des règles sur des prix synthétiques |
| `docs/protocole.md` | Brouillon du protocole de backtest |

## Limites

- Les prix (Yahoo Finance) ne sont pas dans le dépôt et n'ont pas encore été validés par l'équipe.
- Avant le lancement de chaque ETF, l'historique est prolongé par un fonds proche.
- L'historique complet de l'indice défense (SXDCR) manque : avant 07/2023, la Défense est absente.
- Aucun résultat n'est publié ici tant que ces points ne sont pas réglés.
- En cas de signaux strictement égaux, plusieurs lignes peuvent partager un rang, comme dans le classeur Excel.
