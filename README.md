# Standardisation de partie expérimentale (chimie organique)

Outil pour standardiser le formatage d'une partie expérimentale contenue dans
un fichier Word (`.docx`). On charge un `.docx` mal formaté et on récupère un
`.docx` corrigé, accompagné d'un rapport des corrections.

La première règle traite les paragraphes commençant par `1H NMR`. D'autres
règles (13C NMR, HRMS…) peuvent être ajoutées facilement grâce à l'architecture
modulaire (voir plus bas).

## Format cible `1H NMR`

```
1H NMR (<fréquence> MHz, <solvant>, <température> K) …
```

La parenthèse qui suit immédiatement `1H NMR` doit contenir exactement trois
éléments séparés par deux virgules, dans l'ordre :

1. la **fréquence** en MHz (ex. `400.18 MHz`) ;
2. le **solvant** (ex. `CDCl3`, `DMF-d7`) ;
3. la **température** en Kelvin (ex. `298 K`).

Corrections automatiques appliquées :

- espace manquant entre le nombre et `MHz` (`400.18MHz` → `400.18 MHz`) ;
- unité `MHz` ajoutée si le premier élément est un simple nombre ;
- unité `K` ajoutée sur la température (`298` → `298 K`) ;
- fréquence écrite hors de la parenthèse, déplacée à l'intérieur.

Si une température est **absente** ou illisible, un marqueur visible `[??? K]`
est inséré pour correction manuelle. Si la parenthèse est absente ou trop
incomplète, le paragraphe est **signalé** sans correction.

## Installation

Python 3.10+ requis.

```powershell
python -m pip install -r requirements.txt
```

Dépendances : `python-docx` (lecture/écriture docx), `PySide6` (interface),
`pytest` (tests).

## Utilisation

### Interface graphique

```powershell
python app.py
```

1. Cliquer sur **Charger…** et choisir le `.docx` à standardiser.
2. Le fichier de sortie est proposé automatiquement (suffixe `_standardise`),
   modifiable via **Parcourir…**.
3. Cliquer sur **Standardiser**.
4. Lire le rapport des corrections dans la fenêtre ; le `.docx` corrigé est
   écrit à l'emplacement de sortie.

### Ligne de commande

```powershell
python cli.py "partie exp.docx"
# ou en précisant la sortie :
python cli.py "partie exp.docx" "resultat.docx"
```

## Tests

```powershell
python -m pytest
```

## Architecture

```
core/
  docx_io.py        Lecture / écriture .docx, accès au texte des paragraphes
  processor.py      Applique les règles à un document, produit le rapport
  rules/
    base.py         Interface Rule + types Action / RuleResult
    registry.py     Registre ordonné des règles
    nmr_1h.py       Règle 1H NMR
ui/
  controller.py     Logique applicative (sans Qt, testable)
  main_window.py    Fenêtre PySide6
app.py              Point d'entrée de l'interface graphique
cli.py              Interface en ligne de commande
tests/              Tests pytest
```

Le cœur de traitement (`core`) est totalement indépendant de l'interface, ce
qui permet de changer d'UI ou d'ajouter un CLI sans toucher à la logique
métier.

## Ajouter une nouvelle règle

Chaque type de paragraphe à standardiser est une règle indépendante. Pour en
ajouter une (exemple : `13C NMR`) :

1. **Créer le module de la règle** dans `core/rules/`, par exemple
   `core/rules/nmr_13c.py`, en héritant de `Rule` :

   ```python
   from core.rules.base import Action, ActionKind, Rule, RuleResult


   class ThirteenCNmrRule(Rule):
       name = "13C NMR"

       def applies(self, paragraph_text: str) -> bool:
           return paragraph_text.strip().startswith("13C NMR")

       def apply(self, paragraph_text: str) -> RuleResult:
           # … logique de validation / correction …
           return RuleResult(
               new_text=paragraph_text,
               actions=[Action(ActionKind.UNCHANGED, "à implémenter", self.name)],
           )
   ```

2. **Enregistrer la règle** dans `core/processor.py`, fonction
   `build_default_registry` :

   ```python
   from core.rules.nmr_13c import ThirteenCNmrRule

   registry.register(ThirteenCNmrRule())
   ```

3. **Ajouter des tests** dans `tests/` (voir `tests/test_rule_1h_nmr.py` comme
   modèle), en TDD de préférence.

La règle sera automatiquement prise en compte par le CLI et l'interface
graphique, sans autre modification.
