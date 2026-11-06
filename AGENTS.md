# Guide de l'application et règles de contribution

Ce fichier explique l'application et fixe les règles à respecter pour toute
modification du code (humaine ou assistée par IA, par exemple avec Mistral).
Il est écrit pour servir de contexte autonome : un assistant qui le lit doit
pouvoir comprendre l'architecture et contribuer sans introduire de régression.

---

## 1. Ce que fait l'application

Outil de **standardisation du formatage d'une partie expérimentale** de chimie
organique contenue dans un fichier Word (`.docx`).

- Entrée : un `.docx` mal formaté.
- Sortie : un `.docx` corrigé + un **rapport des corrections**.
- Deux règles RMN sont implémentées : `1H NMR` et `13C NMR`, avec une sortie
  **stylisée** (gras, italique, exposants et indices en caractères Unicode).

L'architecture est modulaire : chaque type de paragraphe à standardiser (RMN,
et plus tard HRMS, IR…) est une **règle** indépendante.

Trois façons de lancer :

- interface graphique : `python app.py` (PySide6) ;
- ligne de commande : `python cli.py [--sans-commentaires] <entrée.docx> [sortie.docx]` ;
- en bibliothèque : `core.processor.standardize_file(...)`.

---

## 2. Architecture

```
core/                   Cœur de traitement, SANS aucune dépendance à Qt
  config.py             Dataclass RmnConfig + persistance JSON (rules_config.json)
  docx_io.py            Lecture/écriture .docx ; édition qui préserve les styles
  processor.py          Applique les règles à un document, produit le rapport
  rules/
    base.py             Interface Rule + Action / RuleResult / StyledSegment
    registry.py         Registre ordonné des règles
    nmr_common.py       Helpers RMN partagés (Unicode, parenthèse, signaux, tri)
    nmr_section.py      Base NmrSectionRule (localisation, parenthèse, δ, signaux)
    nmr_1h.py           Règle 1H NMR (noyau + formatage d'un signal)
    nmr_13c.py          Règle 13C NMR (noyau + formatage d'un signal)
ui/                     Interface, SEULE couche qui importe PySide6
  controller.py         Logique applicative testable (sans Qt)
  main_window.py        Fenêtre principale
  settings_dialog.py    Dialogue des paramètres des règles RMN
app.py                  Point d'entrée GUI
cli.py                  Point d'entrée CLI
tests/                  Tests pytest
conftest.py             Rend la racine du projet importable par pytest
```

### Flux de traitement

1. `docx_io.load` ouvre le document.
2. `processor.build_registry` construit un `RuleRegistry` à partir de
   `available_rules()` (filtré par les règles activées).
3. `processor.process_document` parcourt chaque paragraphe du document via
   `docx_io.iter_paragraphs` (corps, tableaux imbriqués, en-têtes / pieds de
   page ; chacun une seule fois, cellules fusionnées et en-têtes liés ignorés).
   `ParagraphReport.location` libelle les paragraphes hors corps ; `index` reste
   la position dans le corps pour ceux du corps. Pour chaque paragraphe :
   - demande au registre les règles qui s'appliquent (`rules_for`) ;
   - applique les règles **en chaîne** (le `new_text` d'une règle alimente la
     suivante) ; chaque règle écrit son édition dans le paragraphe AVANT que la
     suivante ne s'applique, de sorte que texte du document et texte chaîné
     restent identiques ;
   - si une règle renvoie une sortie **stylisée** (`segments`), l'édition passe
     par `docx_io.apply_styled_edit` ; sinon par `docx_io.apply_text_edit`
     (édition par diff qui préserve la mise en forme voisine) ;
   - les deux renvoient `False` sans rien modifier si le texte n'est pas
     entièrement porté par des runs directs (lien hypertexte, champ…) : le
     processor ajoute alors un `FLAGGED` et arrête la chaîne pour ce paragraphe.
   - `apply_styled_edit` copie le `rPr` des runs conservés et donne aux segments
     le `rPr` du run dominant de la portion remplacée (sans gras / italique /
     `vertAlign`). Son repli ne supprime jamais de texte.
4. Avec `annotate` (défaut de `standardize_file`, du CLI et de l'UI ;
   défaut `False` pour `process_document`), chaque paragraphe du corps qui
   porte une action `FLAGGED` / `PLACEHOLDER` reçoit un commentaire Word
   (`docx_io.add_paragraph_comment`, auteur `processor.COMMENT_AUTHOR`).
   Ignorés : en-têtes / pieds de page (refusés par Word), paragraphe sans run
   textuel, paragraphe portant déjà un commentaire de cet auteur (pas de
   doublon au retraitement). `ProcessingReport.comment_count` les compte.
   Invariant d'édition : les runs SANS texte (référence de commentaire, appel
   de note, image) ne sont jamais supprimés ni réécrits par `docx_io`.
5. `docx_io.save` écrit le résultat ; un `ProcessingReport` est retourné.
   `standardize_file` lève `ValueError` si la sortie est le fichier d'entrée
   (`processor.same_file`) : l'original n'est jamais écrasé.

`process_texts` fait la même chaîne **sans docx** (utile en test) : il n'applique
pas les styles mais s'appuie sur `new_text`, qui est toujours le texte final
complet du paragraphe.

---

## 3. Contrat des règles (à respecter impérativement)

Une règle hérite de `core.rules.base.Rule` et implémente :

- `name: str` et `description: str` (affichés dans l'UI et le rapport) ;
- `applies(paragraph_text) -> bool` : vrai si la règle traite ce paragraphe ;
- `apply(paragraph_text) -> RuleResult`.

### `RuleResult`

- `new_text` : **toujours** le texte final COMPLET du paragraphe (même pour une
  sortie stylisée). C'est la vérité textuelle utilisée par le chaînage et les
  rapports. Ne jamais y mettre seulement un fragment.
- `actions` : liste d'`Action(kind, message, rule_name)`. `kind` ∈
  `CORRECTED` / `FLAGGED` / `PLACEHOLDER` / `UNCHANGED`.
- `segments` (optionnel) : la sous-chaîne de remplacement découpée en
  `StyledSegment(text, bold, italic)`. Si fourni → sortie stylisée.
- `replaced_text` (optionnel) : la sous-chaîne **exacte** de l'ancien texte que
  `segments` remplace. Si `segments` est fourni mais `replaced_text` vaut
  `None`, les segments remplacent **tout** le paragraphe.

### Invariants

- Cohérence : la concaténation du texte des `segments`, réinsérée à la place de
  `replaced_text`, doit être égale à `new_text`.
- Idempotence : réappliquer une règle à sa propre sortie ne doit rien changer
  (retourner `UNCHANGED`). Les règles RMN le garantissent déjà.
- Traitement **par segment de section** : un paragraphe peut contenir plusieurs
  sections RMN collées (`1H NMR … 13C NMR …`). Une règle ne reformate QUE son
  segment (voir `nmr_common.section_span`) et laisse le reste intact. Elle
  trouve son label n'importe où dans le paragraphe (`NmrSectionRule._find_label`) :
  hors tête de paragraphe, le label doit être suivi d'une parenthèse avec
  seulement ponctuation/fréquence entre les deux. Préfixe, suffixe et
  `replaced_text` sont pris dans le texte ORIGINAL (espaces insécables compris).

---

## 4. Règles métier RMN (ne pas casser)

Ces comportements sont voulus et couverts par les tests. Toute modification qui
les change doit être explicitement demandée et accompagnée de la mise à jour des
tests.

- **Mot d'entrée conservé** : `NMR` reste `NMR`, `RMN` reste `RMN`. On ajoute
  seulement l'exposant Unicode au nombre de masse (`1H` → `¹H`, `13C` → `¹³C`,
  `19F{1H}` → `¹⁹F{¹H}`). La règle `13C` reconnaît `13C NMR` et `13C RMN`.
- **Exposants et indices en Unicode uniquement**, jamais en superscript/subscript
  Word (`¹`, `²`, `₂`, `₃`…). Indices appliqués seulement aux chiffres qui
  suivent une lettre (`CDCl3` → `CDCl₃`), pour ne pas toucher aux déplacements
  ou intégrations.
- **Parenthèse à trois éléments** : `fréquence MHz, solvant, température K`.
  Corrections : espace avant `MHz`, unité `MHz`/`K` ajoutée, indices sur le
  solvant, fréquence écrite hors parenthèse déplacée à l'intérieur. Température
  absente/illisible → marqueur `[??? K]` (configurable). Parenthèse trop
  incomplète → `FLAGGED` sans correction. Température écrite dans une unité
  différente de l'unité configurée → laissée telle quelle + `FLAGGED` (jamais
  réétiquetée ni convertie).
- **δ en italique** ; variantes d'entrée (`δ`, `ẟ`, `(ppm) =`) normalisées.
- **Label + parenthèse en gras** (configurable).
- **Tri des signaux** du plus grand au plus petit (configurable : `desc` /
  `asc` / `none`), **mais règle de sûreté** : si un seul signal n'est pas
  parsable, la liste des signaux est conservée TELLE QUELLE (ni tri ni
  reformatage) et une action `FLAGGED` est émise. On ne réécrit jamais une
  chimie qu'on n'a pas comprise, et on n'invente aucune donnée.
- **Parsable = reconstructible sans perte** : déplacement suivi au plus d'une
  parenthèse simple. Texte hors parenthèse, parenthèse imbriquée ou virgule
  décimale (`\d,\d`) rendent la liste non parsable. La ponctuation finale
  (`.`/`;`) est retirée avant analyse puis réinsérée. Couverts par
  `tests/test_data_safety.py`.
- **13C** : la multiplicité (ex. `d` d'un couplage C–F) est conservée en sortie.
- Multiplicités `1H` autorisées : `s, d, t, q, quint, septic, m, dd, br s` ;
  `bs` en entrée → `br s` (table configurable). Une multiplicité hors table
  (`td`, `dt`…) ou un champ inconnu AVANT un champ reconnu → signal non
  parsable. `J = 8.4, 2.1 Hz` et `J = 8.4 Hz, J = 2.1 Hz` sont reconnus.
- **Aucun texte supprimé autour de la section** : texte inconnu entre label et
  parenthèse → `FLAGGED` sans modification ; δ absent ou précédé d'un texte
  inconnu → parenthèse normalisée, suite conservée telle quelle, `FLAGGED`
  (aucun δ ajouté). Couvert par `tests/test_sections_and_formatting.py`.

---

## 5. Configuration (`core/config.py`)

- `RmnConfig` centralise les paramètres éditables ; ses **défauts reproduisent
  exactement** le comportement historique (les tests existants doivent rester
  verts sans fichier de préférences).
- Persistance dans `rules_config.json` à la racine (UTF-8, indenté).
- **Non versionné** (présent dans `.gitignore`) et recréé/relu sans exception
  s'il est absent ou corrompu. `config_from_dict` est tolérante champ par champ.
- État de processus via `get_config` / `set_config` / `reset_config`. Les règles
  lisent la config au moment de `apply`.

Pour ajouter un paramètre : l'ajouter à la dataclass avec un défaut qui préserve
le comportement actuel, l'intégrer à `config_to_dict` / `config_from_dict`
(avec validation), puis l'exposer dans `ui/settings_dialog.py`.

---

## 6. Séparation des couches

- `core/` ne doit **jamais** importer PySide6 ni quoi que ce soit de `ui/`.
  Il doit rester testable sans interface graphique.
- La logique applicative testable vit dans `ui/controller.py` (sans Qt) ;
  `main_window.py` et `settings_dialog.py` sont les seuls à importer PySide6 et
  ne contiennent que du câblage d'interface.
- Toute nouvelle logique métier va dans `core/`, pas dans l'UI.

---

## 7. Ajouter une nouvelle règle (ex. HRMS)

1. Créer `core/rules/hrms.py` héritant de `Rule` (`name`, `description`,
   `applies`, `apply`). Pour une sortie stylisée, renseigner `segments` et
   `replaced_text` dans le `RuleResult` (voir `nmr_section.py`). Pour une
   nouvelle section RMN (ex. `19F NMR`), hériter de `NmrSectionRule` et fixer
   seulement `name`, `description`, `nucleus` et `format_signal`.
2. L'ajouter à `available_rules()` dans `core/processor.py`. C'est le **catalogue
   central** : toute règle qui y figure apparaît automatiquement dans le CLI et
   l'UI, sans autre modification.
3. Ajouter des tests dans `tests/` (modèles : `test_rule_1h_nmr.py`,
   `test_rule_13c_nmr.py`), en TDD de préférence.

Factoriser dans `nmr_common.py` (ou un module partagé équivalent) tout helper
réutilisable plutôt que de dupliquer.

---

## 8. Tests et vérification

- Lancer la suite : `python -m pytest` (depuis la racine).
- `conftest.py` isole la configuration RMN (fixture `autouse`) : chaque test
  part des défauts et `DEFAULT_CONFIG_PATH` pointe vers un dossier temporaire.
  Le `rules_config.json` local n'est donc jamais lu ni écrit par les tests.
  `load_config` / `save_config` résolvent ce chemin à l'appel : ne pas le figer
  en argument par défaut.
- Toute modification doit **garder la suite verte**. Ajouter des tests pour
  chaque nouveau comportement ou correction de bug.
- Ne pas ajouter de tests qui dépendent d'un vrai fichier `.docx` externe :
  privilégier `process_texts` et les tests par texte quand le docx n'est pas
  nécessaire ; utiliser des documents construits en mémoire sinon. Seule
  exception : `partie exp.docx`, document de démonstration **versionné**
  volontairement à la racine, utilisé par quelques tests de bout en bout
  (`test_docx_io`, `test_processor`, `test_ui_controller`). Ne pas le
  supprimer ni le modifier ; ne pas en ajouter d'autre.
- Les fichiers de sortie temporaires (`_tmp_*.docx`, `*_standardise.docx`) et
  `rules_config.json` sont ignorés par git : ne pas les committer.

---

## 9. Conventions de code

- Python 3.10+ ; `from __future__ import annotations` en tête de module.
- Docstrings et commentaires **en français**, comme le reste du projet.
- Suivre le style existant (dataclasses, type hints, regex nommées et
  commentées). Ne pas introduire de nouvelle dépendance sans raison ;
  dépendances actuelles : `python-docx`, `PySide6`, `pytest`.
- Préférer des fonctions pures et testables dans `core/` ; isoler les effets de
  bord (I/O fichier, Qt).

---

## 10. Garde-fous pour une modification assistée par IA

- Lire le code concerné **avant** de proposer un changement ; ne pas supposer un
  comportement non vérifié.
- Respecter les invariants des sections 3 et 4 : ils sont la raison d'être de
  l'outil (ne jamais inventer de chimie, ne jamais réordonner des signaux non
  parsables, conserver le mot d'entrée, Unicode plutôt que superscript Word).
- Après toute modification de code, exécuter `python -m pytest` et corriger les
  régressions avant de conclure.
- Garder `core/` libre de Qt.
- Mettre à jour `README.md` et ce fichier si un comportement visible ou une
  règle métier change.
