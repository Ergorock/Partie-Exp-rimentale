# Standardisation de partie expérimentale (chimie organique)

Outil pour standardiser le formatage d'une partie expérimentale contenue dans
un fichier Word (`.docx`). On charge un `.docx` mal formaté et on récupère un
`.docx` corrigé, accompagné d'un rapport des corrections.

Deux règles RMN sont disponibles : `1H NMR` et `13C NMR`, qui produisent une
sortie **stylisée** (gras / italique, exposants et indices Unicode). D'autres
règles (HRMS, IR…) peuvent être ajoutées facilement grâce à l'architecture
modulaire (voir plus bas).

## Conventions communes aux règles RMN

Les deux règles RMN partagent la logique du module `core/rules/nmr_common.py`
et appliquent les conventions suivantes.

### Label et parenthèse (en gras)

Le label et la parenthèse qui le suit sont écrits **en gras**. Le mot d'entrée
est **conservé tel quel** : `1H NMR` reste `NMR`, `1H RMN` reste `RMN` ; on
ajoute seulement l'exposant Unicode au nombre de masse (`1H` → `¹H`,
`13C` → `¹³C`, `19F{1H}` → `¹⁹F{¹H}`).

La parenthèse contient exactement **trois éléments** séparés par deux virgules :

1. la **fréquence** en MHz (ex. `400.18 MHz`) ;
2. le **solvant**, avec indices en Unicode (ex. `CDCl3` → `CDCl₃`,
   `DMF-d7` → `DMF-d₇`) ;
3. la **température** en Kelvin (ex. `298 K`).

Corrections automatiques appliquées sur la parenthèse :

- espace manquant entre le nombre et `MHz` (`400.18MHz` → `400.18 MHz`) ;
- unité `MHz` ajoutée si le premier élément est un simple nombre ;
- indices Unicode appliqués au solvant ;
- unité `K` ajoutée sur la température (`298` → `298 K`) ;
- fréquence écrite hors de la parenthèse, déplacée à l'intérieur.

Si la température est **absente** ou illisible, un marqueur visible `[??? K]`
est inséré. Si la parenthèse est absente ou trop incomplète, le paragraphe est
**signalé** sans correction.

### Symbole δ (en italique)

Le symbole δ qui précède la liste des signaux est écrit **en italique**. Les
variantes d'entrée (`δ`, `ẟ`, éventuellement suivies de `(ppm) =`) sont
normalisées en un `δ` italique standard.

### Exposants et indices Unicode

Les exposants (nombres de masse) et les indices (stœchiométrie des solvants et
attributions) sont écrits en **caractères Unicode** (`¹`, `²`, `₂`, `₃`…), jamais
en superscript/subscript Word.

### Traitement par segment de section

Un paragraphe peut contenir plusieurs sections RMN collées
(`1H NMR … 13C NMR … 19F{1H} NMR …`). Chaque règle ne reformate **que son
propre segment** (du label jusqu'au prochain label de section RMN) et laisse le
reste du paragraphe intact.

### Tri des signaux et règle de sûreté

Les signaux sont triés du déplacement chimique **le plus grand au plus petit**
(champs faibles vers champs forts), mais **uniquement si tous les signaux sont
parsables**. Dès qu'un signal ne peut pas être analysé, aucun réordonnancement
n'est effectué (on ne réécrit jamais une chimie incomprise) et une action
« à vérifier » (FLAGGED) est émise.

## Format cible `1H NMR`

```
¹H NMR (<fréquence> MHz, <solvant>, <température> K) δ <signaux>
```

Pour chaque signal, l'ordre est : déplacement chimique (valeur unique ou plage
`a–b`) → multiplicité → `J = x.x Hz` (une décimale, si présente) → intégration →
attribution (optionnelle). Multiplicités autorisées : `s`, `d`, `t`, `q`,
`quint`, `septic`, `m`, `dd`, `br s` ; `bs` en entrée est normalisé en `br s`.

## Format cible `13C NMR`

```
¹³C NMR (<fréquence> MHz, <solvant>, <température> K) δ <signaux>
```

La règle reconnaît en entrée aussi bien `13C NMR` que `13C RMN`. Les signaux
découplés sont donnés par leur déplacement chimique (une décimale) suivi d'une
attribution optionnelle entre parenthèses (`Cq`, `CH`, `CH₂`, `CH₃`, `C=O`…).
La constante de couplage `J` est conservée lorsqu'un couplage est présent
(ex. couplage F/P).

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
    base.py         Interface Rule + types Action / RuleResult / StyledSegment
    registry.py     Registre ordonné des règles
    nmr_common.py   Helpers partagés RMN (exposants/indices Unicode, parenthèse,
                    segment de section, parsing/tri/formatage des signaux)
    nmr_1h.py       Règle 1H NMR (sortie stylisée)
    nmr_13c.py      Règle 13C NMR (sortie stylisée)
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

## Règles disponibles

- `1H NMR` — `core/rules/nmr_1h.py` (sortie stylisée, voir ci-dessus) ;
- `13C NMR` — `core/rules/nmr_13c.py` (sortie stylisée, implémentée).

Le catalogue central des règles est la fonction `available_rules()` de
`core/processor.py` : toute règle qui y figure est automatiquement proposée dans
le CLI et dans l'interface graphique.

## Ajouter une nouvelle règle

Chaque type de paragraphe à standardiser est une règle indépendante. Pour en
ajouter une (exemple : `HRMS`) :

1. **Créer le module de la règle** dans `core/rules/`, par exemple
   `core/rules/hrms.py`, en héritant de `Rule` :

   ```python
   from core.rules.base import Action, ActionKind, Rule, RuleResult


   class HrmsRule(Rule):
       name = "HRMS"

       def applies(self, paragraph_text: str) -> bool:
           return paragraph_text.strip().startswith("HRMS")

       def apply(self, paragraph_text: str) -> RuleResult:
           # … logique de validation / correction …
           return RuleResult(
               new_text=paragraph_text,
               actions=[Action(ActionKind.UNCHANGED, "à implémenter", self.name)],
           )
   ```

   Pour produire une sortie **stylisée** (gras / italique), renseigner en plus
   `segments` (liste de `StyledSegment`) et `replaced_text` dans le
   `RuleResult` : voir `core/rules/nmr_1h.py` et les helpers de
   `core/rules/nmr_common.py`.

2. **Enregistrer la règle** dans `core/processor.py`, fonction
   `available_rules()` :

   ```python
   from core.rules.hrms import HrmsRule

   return [OneHNmrRule(), ThirteenCNmrRule(), HrmsRule()]
   ```

3. **Ajouter des tests** dans `tests/` (voir `tests/test_rule_1h_nmr.py` et
   `tests/test_rule_13c_nmr.py` comme modèles), en TDD de préférence.

La règle sera automatiquement prise en compte par le CLI et l'interface
graphique, sans autre modification.
