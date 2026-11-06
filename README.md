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
reste du paragraphe intact. Chaque section est traitée par sa règle, même si
elle n'est pas en tête du paragraphe : dans `1H NMR … 13C NMR …`, les deux
sections sont reformatées, et `Composé 3 : 1H NMR (…)` l'est aussi (le préfixe
est conservé à l'identique).

Pour ne jamais toucher à une phrase qui mentionne simplement « 1H NMR », une
section hors tête de paragraphe n'est reconnue que si son label est suivi d'une
parenthèse, avec seulement une ponctuation ou une fréquence (`400 MHz`) entre
les deux. Aucun texte n'est supprimé :

- texte inconnu entre le label et la parenthèse → section signalée, non modifiée ;
- delta absent, ou précédé d'un texte inconnu → parenthèse normalisée, mais la
  suite est conservée telle quelle (aucun `δ` ajouté) et signalée.

### Tri des signaux et règle de sûreté

Les signaux sont triés du déplacement chimique **le plus grand au plus petit**
(champs faibles vers champs forts), mais **uniquement si tous les signaux sont
parsables**. Dès qu'un signal ne peut pas être analysé, la liste des signaux est
**laissée telle quelle** (ni réordonnée, ni reformatée : on ne réécrit jamais une
chimie incomprise) et une action « à vérifier » (FLAGGED) est émise.

Un signal n'est considéré comme parsable que s'il peut être reconstruit **sans
perte** : un déplacement suivi, au plus, d'une parenthèse simple. Sont donc
signalés sans réécriture : un texte hors parenthèse (`3.50 (br s, 1H)
overlapped`), une parenthèse imbriquée (`25.1 (CH(CH3)2)`) ou une virgule
décimale (`7,26`). Un point ou point-virgule final après la liste est conservé.

## Format cible `1H NMR`

```
¹H NMR (<fréquence> MHz, <solvant>, <température> K) δ <signaux>
```

Pour chaque signal, l'ordre est : déplacement chimique (valeur unique ou plage
`a–b`) → multiplicité → `J = x.x Hz` (une décimale, si présente) → intégration →
attribution (optionnelle). Multiplicités autorisées : `s`, `d`, `t`, `q`,
`quint`, `septic`, `m`, `dd`, `br s` ; `bs` en entrée est normalisé en `br s`.
Une multiplicité hors table (`td`, `dt`, `ddd`…) ou un champ inconnu placé avant
un champ reconnu rendent le signal non parsable (liste laissée telle quelle et
signalée) ; ajoutez la multiplicité dans les paramètres pour qu'elle soit
reconnue. Plusieurs constantes sont acceptées : `J = 8.4, 2.1 Hz` ou
`J = 8.4 Hz, J = 2.1 Hz` (forme d'entrée conservée).

La mise en forme Word du paragraphe est conservée : le texte hors section garde
toutes ses propriétés (police, taille, couleur…), et la section reformatée
reprend la police de son texte d'origine, sans exposant/indice Word. Un
paragraphe dont le texte n'est pas entièrement porté par des runs simples (lien
hypertexte, champ…) n'est pas modifié et est signalé.

## Format cible `13C NMR`

```
¹³C NMR (<fréquence> MHz, <solvant>, <température> K) δ <signaux>
```

La règle reconnaît en entrée aussi bien `13C NMR` que `13C RMN`. Les signaux
découplés sont donnés par leur déplacement chimique (une décimale) suivi d'une
attribution optionnelle entre parenthèses (`Cq`, `CH`, `CH₂`, `CH₃`, `C=O`…).
La multiplicité et la constante de couplage `J` sont conservées lorsqu'un
couplage est présent (ex. `162.3 (d, J = 245 Hz)` pour un couplage C–F).

## Installation

Python 3.10+ requis.

Pour utiliser l'outil :

```powershell
python -m pip install -r requirements.txt
```

Pour développer (ajoute `pytest`) :

```powershell
python -m pip install -r requirements-dev.txt
```

Dépendances : `python-docx` (lecture/écriture docx) et `pywebview` (fenêtre de
l'interface, qui utilise le moteur WebView2 déjà présent sur Windows 10/11) ;
`pytest` pour les tests uniquement.

Le projet est aussi installable comme paquet (`pyproject.toml`), ce qui crée
deux commandes : `standardisation-rmn` (ligne de commande) et
`standardisation-rmn-gui` (interface graphique).

```powershell
python -m pip install .          # ou : python -m pip install -e ".[dev]"
```

## Utilisation

### Interface graphique

```powershell
python app.py
```

1. Déposer le `.docx` sur la fenêtre, ou cliquer sur **Choisir un document…**.
2. Le fichier de sortie est proposé automatiquement (suffixe `_standardise`),
   modifiable via **Changer l'emplacement…**. Choisir un autre document remet la
   sortie proposée pour ce nouveau fichier, pour ne jamais écraser le résultat
   du précédent.
3. Cliquer sur **Standardiser**.
4. Le résultat s'affiche à droite : chaque ligne RMN telle qu'elle est écrite
   dans le document, avec les signalements en marge. Le filtre **À vérifier**
   (actif par défaut quand il y a des signalements) ne montre que ce qui demande
   une intervention ; **Tous** montre aussi les lignes corrigées
   automatiquement. **Ouvrir dans Word** ouvre le fichier produit.

L'interface suit le thème clair ou sombre de Windows.

Tout le document est traité : corps du texte, tableaux (imbriqués compris),
en-têtes et pieds de page. Le rapport indique l'emplacement de chaque
paragraphe (`Paragraphe 3`, `Tableau 1, ligne 2, cellule 1, paragraphe 1`,
`En-tête (section 1), paragraphe 1`…). Les notes de bas de page ne sont pas
traitées (non exposées par `python-docx`).

Le fichier d'entrée n'est jamais écrasé : une sortie qui désigne le même
fichier (y compris avec une autre casse sous Windows) est refusée, dans l'UI
comme dans le CLI.

### Commentaires Word sur les points à vérifier

Par défaut, chaque paragraphe qui porte un signalement « à vérifier » ou un
marqueur inséré (`[??? K]`…) reçoit un **commentaire Word** dans le fichier de
sortie (auteur « Standardisation RMN »), qui liste ces signalements. On les
traite donc directement dans Word, au bon endroit ; les corrections sûres ne
génèrent pas de commentaire. La case **Commenter dans Word les paragraphes à
vérifier** de la fenêtre (cochée par défaut) ou l'option
`--sans-commentaires` du CLI les désactivent.

- Les commentaires déjà présents dans le document (relecteurs) sont conservés,
  y compris sur les paragraphes corrigés.
- Retraiter un document déjà annoté n'ajoute pas de doublon.
- Word n'accepte pas de commentaire dans un en-tête ou un pied de page : ces
  signalements restent visibles dans le rapport seulement.

### Paramètres

Le bouton **Paramètres** ouvre un dialogue pour ajuster le comportement des
règles RMN. Paramètres éditables :

- **Multiplicités reconnues** : table « écrit dans le document » → « devient »
  (par exemple `bs` → `br s`). **Ajouter une multiplicité** et **Retirer**
  gèrent les lignes ; une ligne dont l'entrée est vide est ignorée, et une
  valeur « devient » vide reprend l'entrée. L'entrée est insensible à la casse
  et aux espaces multiples (`Td` et `td` sont équivalents).
- **Marqueur de température manquante** : texte inséré lorsqu'une température
  est absente ou illisible (défaut `[??? K]`). Tant qu'il garde sa forme par
  défaut, il suit l'unité choisie (`[??? °C]`).
- **Ordre des signaux** : décroissant (défaut), croissant ou ordre du document.
- **Label et parenthèse en gras** et **symbole δ en italique** : activent ou
  désactivent ces styles.
- **Unité de température** : `K` ou `°C`. Elle est ajoutée aux températures
  écrites sans unité (`298` → `298 °C`), sans conversion. Une température déjà
  écrite dans l'autre unité (`298 K` alors que `°C` est configuré, ou `25 °C`
  avec `K`) n'est jamais réétiquetée : elle est laissée telle quelle et signalée.

Les boutons :

- **Enregistrer** écrit les paramètres dans `rules_config.json` et les applique
  immédiatement ;
- **Annuler** ferme le dialogue sans rien écrire ni modifier ;
- **Rétablir les valeurs par défaut** remet les champs aux valeurs par défaut
  dans le dialogue, sans rien écrire tant qu'**Enregistrer** n'est pas cliqué.

Les préférences sont enregistrées dans le dossier de l'utilisateur, jamais
dans le dossier de l'application (qui peut être en lecture seule une fois
installée) :

- Windows : `%APPDATA%\StandardisationRMN\rules_config.json` ;
- macOS / Linux : `~/.config/standardisation-rmn/rules_config.json` (ou
  `$XDG_CONFIG_HOME`) ;
- la variable d'environnement `STANDARDISATION_RMN_CONFIG` impose un autre
  chemin (installation portable).

Le fichier est recréé aux valeurs par défaut s'il est absent ou corrompu. Un
ancien `rules_config.json` resté à la racine du projet (versions précédentes)
est encore lu tant que le nouveau fichier n'existe pas ; le premier
enregistrement via **Enregistrer** écrit dans le nouvel emplacement.

### Ligne de commande

```powershell
python cli.py "partie exp.docx"
# ou en précisant la sortie :
python cli.py "partie exp.docx" "resultat.docx"
# sans commentaires Word :
python cli.py --sans-commentaires "partie exp.docx"
```

## Exécutable Windows

Pour distribuer l'outil à des utilisateurs sans Python, construire les
exécutables avec PyInstaller (installé par `requirements-dev.txt`) :

```powershell
.venv\Scripts\python -m PyInstaller standardisation_rmn.spec --noconfirm
```

Le dossier `dist\` contient alors deux fichiers autonomes, à copier tels quels :

- `StandardisationRMN.exe` (environ 18 Mo) : l'interface graphique ;
- `StandardisationRMN-cli.exe` (environ 15 Mo) : la ligne de commande, mêmes
  options que `cli.py`, sans interface.

À savoir :

- chaque exécutable est un fichier unique qui se décompresse au lancement :
  l'interface met quelques secondes à s'ouvrir ;
- l'interface utilise WebView2, présent par défaut sur Windows 10 et 11 ;
- l'exécutable n'est pas signé : au premier lancement, Windows SmartScreen
  peut afficher un avertissement (« Informations complémentaires » →
  « Exécuter quand même ») ;
- les préférences sont enregistrées dans `%APPDATA%\StandardisationRMN`,
  comme pour la version Python ;
- `build\` et `dist\` sont ignorés par git.

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
    nmr_section.py  Base commune des règles de section RMN (localisation,
                    parenthèse, delta, signaux, sortie stylisée)
    nmr_1h.py       Règle 1H NMR (noyau + formatage d'un signal)
    nmr_13c.py      Règle 13C NMR (noyau + formatage d'un signal)
ui/
  controller.py     Logique applicative (sans interface, testable)
  web_api.py        API Python appelée par l'interface (pywebview)
  web/              Interface : index.html, app.css, app.js (sans build)
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
   `RuleResult` : voir `core/rules/nmr_section.py` et les helpers de
   `core/rules/nmr_common.py`. Une nouvelle section RMN (ex. `19F NMR`) n'a
   qu'à hériter de `NmrSectionRule` en fixant `nucleus` et `format_signal`.

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
