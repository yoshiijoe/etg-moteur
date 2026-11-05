"""Univers du moteur (page Stratégie de l'équipe) et fonds utilisés pour prolonger l'historique."""
# nom, symbole Yahoo de l'ETF, fonds proche pour la période antérieure, code
SERIES = [
    ("Banques", "BNK.PA", "EXV1.DE", "BNK"),
    ("Pétrole & gaz", "ENRG.PA", "EXH1.DE", "ENRG"),
    ("Défense", "DEFS.PA", "ASWC.DE", "DEFS"),
    ("Technologie", "TNO.PA", "EXV3.DE", "TNO"),
    ("Industrie", "IND.PA", "EXH4.DE", "IND"),
    ("Matières premières", "BRES.PA", "EXV6.DE", "BRES"),
    ("Santé", "HLT.PA", "EXV4.DE", "HLT"),
    ("Télécoms", "TELE.PA", "EXV2.DE", "TELE"),
    ("Services publics", "UTI.PA", "EXH9.DE", "UTI"),
    ("Agroalimentaire", "FOO.PA", "EXH3.DE", "FOO"),
    ("Monétaire n°1", "CSH2.PA", "CSH.PA", "CSH2"),
    ("Monétaire n°2", "CASHE.PA", "CSH.PA", "CASHE"),
    ("STOXX Europe 600", None, "EXSA.DE", "EXSA"),
]
ETF = [s[0] for s in SERIES[:10]]
MONETAIRES = ["Monétaire n°1", "Monétaire n°2"]
REFERENCE = "STOXX Europe 600"
SYMBOLES = sorted({x for s in SERIES for x in s[1:3] if x})
