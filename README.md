# Sulfuric Acid Plant — Digital Twin
## Structure du projet

```
sulfuric_plant/
│
├── model/
│   ├── __init__.py
│   ├── four.py            ← Constantes globales + four de combustion
│   ├── chaudiere.py       ← Waste Heat Boiler
│   └── convertisseur.py   ← Convertisseur catalytique (4 lits)
│
├── simulation/
│   ├── __init__.py
│   └── main_simulation.py ← Orchestre Four → Chaudière → Convertisseur
│
├── ui/
│   ├── __init__.py
│   └── app.py             ← Interface Streamlit + dessin flowsheet
│
└── README.md
```

## Lancement
```bash
# Depuis la racine du projet (sulfuric_plant/)
streamlit run ui/app.py
```

## Responsabilité de chaque module

| Fichier | Contient |
|---|---|
| `model/four.py` | Constantes globales (R, P_ABS, COEFFS…), géométrie four, `solve_zones()`, `calcul_U_loss()` |
| `model/chaudiere.py` | Paramètres chaudière, table vapeur, `solve_boiler_and_bypass()` |
| `model/convertisseur.py` | Classe `JumeauNumeriqueConvertisseur` complète |
| `simulation/main_simulation.py` | `simuler_complet()` avec `@st.cache_data` — appelle les 3 modèles dans l'ordre |
| `ui/app.py` | `draw_flowsheet()` + layout Streamlit (sidebar, onglets, CSS) |

## Ajouter un nouvel équipement (exemple : tour d'absorption)
1. Créer `model/absorption.py` avec les paramètres et la fonction de calcul
2. Importer et appeler dans `simulation/main_simulation.py`
3. Ajouter le dessin dans `draw_flowsheet()` dans `ui/app.py`
→ Les autres fichiers ne changent pas.
