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
- Six règles RMN (`1H NMR`, `13C NMR`, `19F NMR`, `31P NMR`, `11B NMR`, `29Si NMR`) et les règles
  `HRMS`, `IR`, `Rf`, `m.p. / b.p.`, `Unités` et `Ordre des analyses` sont implémentées, avec une sortie
  **stylisée** (gras, italique, exposants et indices en caractères Unicode).

L'architecture est modulaire : chaque type de paragraphe à standardiser (RMN,
et plus tard HRMS, IR…) est une **règle** indépendante.

Trois façons de lancer :

- interface graphique : `python app.py` (HTML/CSS/JS dans une fenêtre pywebview) ;
- ligne de commande : `python cli.py [--sans-commentaires] <entrée.docx> [sortie.docx]`,
  ou `python cli.py --evaluer <entrée.docx>` (évaluation seule, rien n'est écrit) ;
- en bibliothèque : `core.processor.standardize_file(...)`.

---

## 2. Architecture

```
core/                   Cœur de traitement, SANS aucune dépendance d'interface
  config.py             Dataclass RmnConfig + persistance JSON (rules_config.json)
  docx_io.py            Lecture/écriture .docx ; édition qui préserve les styles
  processor.py          Applique les règles à un document, produit le rapport
  evaluation.py         Mode évaluation : score, note, écarts (n'écrit rien)
  rules/
    base.py             Interface Rule + Action / RuleResult / StyledSegment
    registry.py         Registre ordonné des règles
    nmr_common.py       Helpers RMN partagés (Unicode, parenthèse, signaux, tri)
    nmr_section.py      Base NmrSectionRule (localisation, parenthèse, δ, signaux)
    nmr_1h.py           Règle 1H NMR (noyau + formatage d'un signal)
    nmr_13c.py          Règle 13C NMR (noyau + formatage d'un signal)
    nmr_hetero.py       Règles 19F, 31P, 11B et 29Si NMR (même base)
    units.py            Règle Unités (espace insécable nombre-unité, procédure)
    analysis_order.py   Règle Ordre des analyses (contrôle intra-paragraphe, sans édition)
    punctuation.py      Règle Ponctuation (espace avant : ou ;, ponctuation doublée)
    hrms.py             Règle HRMS (format ACS + vérification des masses)
    ir.py               Règle IR (méthode, bandes entières triées, cm⁻¹)
    rf.py               Règle Rf (f en indice Word, phase stationnaire, éluant)
    melting_point.py    Règle m.p. / b.p. (plage, °C, solvant, pression, dec., lit.)
    mass.py             Masses monoisotopiques, formule brute, m/z d'un ion
  highlights.py         Surlignage : empans (début, fin, cas) du texte final, pour l'UI
ui/                     Interface, SEULE couche qui importe pywebview
  controller.py         Logique applicative testable (sans interface)
  web_api.py            API exposée au JavaScript (window.pywebview.api)
  web/                  index.html, app.css, app.js : affichage seulement
app.py                  Point d'entrée GUI
cli.py                  Point d'entrée CLI
tests/                  Tests pytest
conftest.py             Racine importable + isolation de la config RMN
pyproject.toml          Paquet installable (commandes standardisation-rmn[-gui])
requirements.txt        Dépendances d'exécution ; requirements-dev.txt ajoute pytest, pyinstaller
standardisation_rmn.spec  Build PyInstaller : StandardisationRMN.exe (+ -cli.exe)
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
     `vertAlign`). L'italique, l'exposant et l'indice Word des caractères
     CONSERVÉS (diff ancien / nouveau texte de la portion) sont reportés sur les
     segments (`J`, `³` de `³J`, `H–H` en indice…) ; le gras n'est pas reporté.
     Son repli ne supprime jamais de texte.
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
- **Forme déjà conforme reconnue** : `applies` doit être vrai aussi sur la
  sortie de la règle (`¹H NMR`, `¹⁹F{¹H} NMR`, `[M + H]⁺`…), sinon le mode
  évaluation ignore les sections conformes. Texte inchangé → les `FLAGGED` /
  `PLACEHOLDER` sont CONSERVÉS (pas remplacés par `UNCHANGED`) : une section
  conforme en apparence mais incomplète reste « à vérifier ».

### Surlignage dans l'interface (`core/highlights.py`, `tests/test_highlights.py`)

- `Action.highlights` : extraits EXACTS du texte final à surligner pour un
  signalement `FLAGGED` (la valeur en cause, l'entrée concernée…). Affichage
  seulement, jamais de logique : un extrait introuvable est ignoré. Une nouvelle
  règle SHOULD renseigner `highlights` sur ses `FLAGGED` ; sans extrait, le
  signalement reste visible en marge mais n'est pas surligné dans le texte.
- `compute_spans(before, after, actions, changed)` (pur, dans `core`) renvoie
  des empans `{start, end, kind}` sur le texte FINAL : `flagged` (extraits des
  règles) > `placeholder` (marqueur `[??? K]` / valeur de `temperature_placeholder`) >
  `corrected` (différence mot à mot avec l'original, espaces insécables
  comprises). `ui/controller.py` les expose (`spans`), `ui/web/app.js` les pose
  sur le texte déjà mis en forme (DOM, noeuds texte découpés) : aucune logique
  métier en JavaScript. Pas de surlignage en mode évaluation (le texte affiché
  est l'original).

### Mode évaluation (`core/evaluation.py`, `tests/test_evaluation.py`)

- N'écrit jamais le document : règles appliquées en chaîne sur le texte seul.
- Un élément = une règle appliquée à un paragraphe. Statut : `conforme`
  (aucune action hors `UNCHANGED`), `corrigé` (texte modifié / `CORRECTED`),
  `à vérifier` (au moins un `FLAGGED` / `PLACEHOLDER`).
- Score = % d'éléments conformes ; note selon `config.evaluation_thresholds`
  (`parfait`, `tres_bon`, `bon`, `correct`, sinon « Mauvais » ; aucun
  élément → « Non évaluable »).
- Écarts regroupés par (règle, type d'action, **partie fixe du message avant
  `' : '`**). Tout nouveau message d'action doit donc mettre ses valeurs
  variables APRÈS `' : '` (voir 7.1, point 7).
- Traitement **par segment de section** : un paragraphe peut contenir plusieurs
  sections RMN collées (`1H NMR … 13C NMR …`). Une règle ne reformate QUE son
  segment (voir `nmr_common.section_span`) et laisse le reste intact. Elle
  trouve son label n'importe où dans le paragraphe (`NmrSectionRule._find_label`) :
  hors tête de paragraphe, le label doit être suivi d'une parenthèse avec
  seulement ponctuation/fréquence entre les deux. Préfixe, suffixe et
  `replaced_text` sont pris dans le texte ORIGINAL (espaces insécables compris).

---

## 4. Règles métier RMN et HRMS (ne pas casser)

Ces comportements sont voulus et couverts par les tests. Toute modification qui
les change doit être explicitement demandée et accompagnée de la mise à jour des
tests.

- **Mot d'entrée conservé** : `NMR` reste `NMR`, `RMN` reste `RMN`. On ajoute
  seulement l'exposant Unicode au nombre de masse (`1H` → `¹H`, `13C` → `¹³C`,
  `19F{1H}` → `¹⁹F{¹H}`). La règle `13C` reconnaît `13C NMR` et `13C RMN`.
  Toutes les règles de section acceptent un découplage `{1H}` (`13C{1H} NMR`)
  et un tiret avant le mot (`1H-NMR` → `¹H NMR`, séparateur normalisé).
- **Exposants et indices en Unicode uniquement**, jamais en superscript/subscript
  Word (`¹`, `²`, `₂`, `₃`…). **Seule exception** (décision du 2026-11-08) :
  les lettres sans indice Unicode des symboles `[α]D` (D), `Rf` (f) et `tR`
  (R) sont mises en indice Word, et rien d'autre. Indices appliqués seulement aux chiffres qui
  suivent une lettre (`CDCl3` → `CDCl₃`), pour ne pas toucher aux déplacements
  ou intégrations. Après une parenthèse fermante aussi (`(CD3)2SO` →
  `(CD₃)₂SO`). Dans l'attribution, les numéros de position (`H4`, `C3`, `C4'` :
  un symbole d'élément + numéro) ne sont JAMAIS mis en indice
  (`nmr_common.subscript_attribution`).
- **Parenthèse à trois éléments** : `fréquence MHz, solvant, température K`.
  Corrections : espace avant `MHz`, unité `MHz`/`K` ajoutée, indices sur le
  solvant, fréquence écrite hors parenthèse déplacée à l'intérieur. Température
  absente/illisible → marqueur `[??? K]` (configurable). Parenthèse trop
  incomplète → `FLAGGED` sans correction. Température écrite dans une unité
  différente de l'unité configurée → laissée telle quelle + `FLAGGED` (jamais
  réétiquetée ni convertie).
- **δ en italique, suivi de `(ppm) =`** (décision du 2026-11-12, guide LCMCE) :
  sortie `δ (ppm) = 7.26 (s, 1 H)` ; variantes d'entrée (`δ`, `ẟ`, avec ou sans
  `(ppm) =`) normalisées vers cette forme (`(ppm) =` en style normal).
  **J en italique** (`italic_j`, configurable) : seule la mise en forme change.
- **Plage de déplacements** (décision du 2026-11-12) : `7.41 – 7.50`, tiret
  demi-cadratin ENTOURÉ d'espaces insécables (`nmr_common.RANGE_SEP`) ; même
  forme pour les plages IR. **Intégration** `5 H` (espace insécable,
  `nmr_common.format_integration`). En 1H, l'attribution suit les données du
  signal après un point-virgule : `(m, 5 H; OCH₂)` (le `;` est aussi accepté en
  entrée) ; en 13C l'attribution reste seule entre parenthèses.
- **Décimales contrôlées, jamais modifiées** (décision du 2026-11-12) : δ 2
  décimales en 1H (3 tolérées), 1 décimale pour 13C / 19F / 31P (2 tolérées), J
  1 décimale ; autrement `FLAGGED` « Nombre de décimales … inattendu : valeurs »
  (`nmr_common.check_decimals`, attribut `NmrSectionRule.shift_decimals`).
  Contrôle limité aux listes entièrement parsables. Une nouvelle section RMN
  fixe `shift_decimals` (défaut 1).
- **Température obligatoire** (3 éléments) : décision du 2026-11-12, inchangée.
  Désactivable par `check_temperature` (défaut `True`) : à `False`, le 3e élément
  est laissé tel quel (ni marqueur, ni unité, ni signalement d'unité) ; seule la
  structure de la parenthèse (< 2 ou > 3 éléments) reste signalée.
- **Virgule décimale des signaux RMN** (décision du 2026-11-13, option
  `convert_decimal_comma`, défaut `True`) : `7,26 (s` -> `7.26 (s`,
  `J = 8,4 Hz` -> `8.4 Hz` (`CORRECTED` « Virgule décimale remplacée par un
  point : … »). Seulement si NON ambiguë (`nmr_common.convert_decimal_commas` :
  1-3 chiffres, virgule, 1-2 décimales, suivis de `(`, `Hz`, tiret de plage ou
  fin). Cas ambigus (`170,165 (`, 3 décimales, `J = 8,4, 2,1 Hz`) ou liste
  encore non parsable après conversion -> liste INTACTE + `FLAGGED`. Option à
  `False` : ancien comportement (liste conservée + `FLAGGED`). Les règles IR,
  HRMS, Rf et m.p. ne convertissent toujours pas.
- **Signe moins** : `-`, `−` (U+2212) et `–` (U+2013) acceptés devant un
  déplacement ; le signe est conservé tel qu'écrit.
- **Label seul en gras** (`¹H NMR`, `HRMS`), jamais la parenthèse qui suit
  (configurable : `bold_label`).
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
- Multiplicités autorisées par défaut (`config._default_multiplicities`) :
  simples (`s, d, t, q, quint, sext, sept, hept, septic, m`), composées
  usuelles (`dd, dt, td, tt, dq, qd, ddd, ddt, dtd, tdd, dddd, qt, tq`), larges
  (`br x` ; `bs`, `bd`, `br. s` → `br x`) et apparentes (`app x`). Table
  configurable. Une multiplicité hors table (`ddq`…) ou un champ inconnu AVANT
  un champ reconnu → signal non
  parsable. `J = 8.4, 2.1 Hz` et `J = 8.4 Hz, J = 2.1 Hz` sont reconnus.
- **Aucun texte supprimé autour de la section** : texte inconnu entre label et
  parenthèse → `FLAGGED` sans modification ; δ absent ou précédé d'un texte
  inconnu → parenthèse normalisée, suite conservée telle quelle, `FLAGGED`
  (aucun δ ajouté). Couvert par `tests/test_sections_and_formatting.py`.
- **Fin de section** : une section RMN s'arrête au label RMN suivant OU au
  label d'une autre analyse (`nmr_common._OTHER_ANALYSIS_RE`, aujourd'hui
  `HRMS` et `IR`). Toute nouvelle règle d'analyse doit y ajouter son label.

### HRMS (`core/rules/hrms.py`, `tests/test_rule_hrms.py`)

- Format cible : `HRMS (ESI-TOF) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.0910;
  Found 165.0912.` Label `HRMS` seul en gras (`bold_label`), `m/z` en italique,
  ion normalisé et placé avant `Calcd for`, formule en indices Unicode.
- **Les masses ne sont JAMAIS modifiées** (ni arrondies, ni corrigées). La
  masse calculée est recalculée (`mass.py`) : formule de l'ion OU formule
  neutre + ion, avec ou sans masse de l'électron ; incohérente → `FLAGGED`
  avec la valeur attendue. Écart trouvé / calculé > `hrms_ppm_tolerance`
  (5 ppm) → `FLAGGED`. Écart absolu > `hrms_abs_tolerance` (0.003 Da, en plus des
  ppm) → `FLAGGED`. Masse calculée < 500 : 4 décimales attendues pour les masses
  calculée et trouvée, sinon `FLAGGED` (valeurs conservées). Ion ou méthode
  absents → `FLAGGED`.
- Structure non reconnue (virgule décimale, ordre inhabituel) → `FLAGGED`
  sans modification. Mention en prose (sans `calcd` / `found`) ignorée.
- Une entrée déjà conforme mais incohérente reste signalée (les vérifications
  ne dépendent pas d'un changement de texte).

### IR (`core/rules/ir.py`, `tests/test_rule_ir.py`)

- Format cible (décision du 2026-11-12) : `IR (ATR): ν̃(cm⁻¹) = 3420, 1715,
  1600` (`ν̃` = ν + U+0303). Label `IR` seul en gras (`bold_label`), pas
  d'italique ni d'indice Word. Méthode recopiée telle qu'écrite (indices
  Unicode : `CHCl₃`), unité `cm⁻¹` Unicode dans la parenthèse du symbole.
- Bandes : entiers de 3 à 4 chiffres, ou plage d'entiers (`3300 – 2400`, tiret
  demi-cadratin entouré d'espaces insécables, triée sur sa borne haute),
  recopiés tels quels, tri DÉCROISSANT FIXE
  (pas de paramètre), attribution / intensité entre parenthèses conservée.
- Variantes acceptées : `νmax`, `ν`, `ν̃`, `vmax`, `v` ou aucun symbole ; unité
  `cm-1`, `cm−1`, `cm^-1`, `cm⁻¹` en fin de liste, en tête (`νmax/cm-1`, forme
  RSC convertie), entre parenthèses ou dans la parenthèse de la méthode ;
  `=` / `:` optionnel ; ponctuation finale conservée. Symbole ou unité absents :
  ajoutés (forme, pas donnée).
- Sûreté : méthode absente, bande décimale (`1715.5`), virgule décimale
  (`\d,\d`, donc `3420,1715` sans espace aussi), texte hors parenthèse,
  parenthèse imbriquée, liste vide → entrée INTACTE + `FLAGGED` (aucun arrondi,
  aucun tri). Le segment IR court jusqu'au label d'analyse suivant ou la fin du
  paragraphe : du texte libre après les bandes rend donc l'entrée non
  reconnue.
- Mention en prose (« Les spectres IR… » hors tête de paragraphe) ignorée.

### Solvants RMN (`config.solvents`, `nmr_common.lookup_solvent`, `tests/test_solvents.py`)

- Le 2e élément de la parenthèse des sections RMN est cherché dans la table
  `RmnConfig.solvents` (écrit -> sortie balisée), élément entier, insensible à
  la casse et aux espaces multiples. m.p./b.p., IR et Rf ne l'utilisent pas.
- Balisage de la sortie : `*…*` = italique (`DMSO-*d*6`) ; indices Unicode
  automatiques (`nmr_common.parse_solvent_markup`, appliqués sur le texte
  complet puis redécoupés). Le balisage n'apparaît jamais dans `new_text`.
  Un `*` non apparié est refusé par `config_from_dict` (la clé est recopiée).
- Solvant trouvé : remplacé (`CORRECTED`, « Solvant remplacé » ou, si seuls les
  indices changent, « Solvant en indices Unicode »). Absent : indices
  automatiques, AUCUN remplacement, `FLAGGED` « Solvant absent de la table :
  <valeur> ; … » (surlignage sur le solvant).
- Idempotence : la forme déjà rendue (`DMSO-d₆`) est reconnue par `lookup_solvent`.
- `ParenResult.solvent_pieces` alimente `nmr_section._paren_segments` : la
  parenthèse n'est découpée en segments QUE si une pièce est en italique.
- Limite (comme Rf) : texte déjà conforme -> document non réécrit, un *d* non
  italique dans Word n'est pas corrigé.

### 11B / 29Si, Unités, Ordre des analyses

- **11B NMR, 29Si NMR** (`nmr_hetero.py`, `tests/test_analysis_order_and_nmr_b_si.py`) :
  héritent de `NmrSectionRule` comme 31P (`format_signal_13c`), 1 décimale pour δ.
  La largeur à mi-hauteur (Hz) du 11B n'est pas reconnue (signal non analysable
  -> liste intacte + `FLAGGED`).
- **Unités** (`units.py`, `tests/test_rule_units.py`) : espace insécable entre
  nombre et unité (`220 mg`, `77 %`, `25 °C`), `mol%` / `wt%` / `vol%` collés,
  `ºC` / `˚C` -> `°C`. Seule la forme change. Unités d'une lettre (`g h L M`)
  seulement avec espace déjà écrite. Édition par diff (`apply_text_edit`, pas
  de segments). **Tout texte à partir du premier label d'analyse est exclu**
  (sinon la règle et les règles d'analyse se contrediraient : `400 MHz`
  reste avec une espace ordinaire). Rendement avec décimale -> `FLAGGED`.
- **Ordre des analyses** (`analysis_order.py`) : séquence Rf ; m.p./b.p. ; 1H ;
  13C ; autres RMN ; IR ; UV/Vis ; MS ; HRMS ; analyse élémentaire. Aucune
  modification. `applies` n'est vrai QUE si l'ordre est incorrect (une règle
  de contrôle toujours « conforme » gonflerait le score d'évaluation). Intra-
  paragraphe seulement : l'ordre entre paragraphes n'est pas contrôlé.
  Dérogation assumée à « applies vrai aussi sur la sortie » : cette règle ne
  produit pas de sortie.

### Ponctuation (`core/rules/punctuation.py`, `tests/test_rule_punctuation.py`)

- Première règle du catalogue (elle nettoie avant les règles d'analyse).
  Supprime les espaces (ordinaires, insécables) AVANT `:` et `;` ; réduit `,,`
  `;;` `::` et `..` (pas `...`). Deux ponctuations différentes collées (`,;`,
  `;,`, `:;`, `,.`…) -> `FLAGGED`, texte conservé. `.,` / `.;` ignorés
  (abréviations). Édition par diff (`apply_text_edit`).
- Comme l'ordre des analyses, `applies` n'est vrai QUE s'il y a quelque chose à
  corriger ou signaler (dérogation assumée, pour ne pas gonfler le score).
- **IR** : « IR intensities / inten. » (légende) n'est pas une entrée IR.
- **RMN** : pour un signal non analysable, seul ce signal est surligné
  (`Action.highlights`) ; toute la liste si le cas est global (virgule ambiguë).

### m.p. / b.p. (`core/rules/melting_point.py`, `tests/test_rule_melting_point.py`)

- Structure IMPOSÉE (décisions du 2026-11-12) : `m.p. 185 – 186 °C (Et₂O/hexane;
  dec.; lit. [12] 185 – 187 °C)` ; b.p. : `b.p. 80 °C (15 mmHg)`. Label en
  minuscules avec points, en gras (`bold_label`), même règle pour les deux.
- Température entière ou plage (tiret demi-cadratin entouré d'espaces
  insécables, espace insécable avant `°C`). `°C` SEUL : `ºC`, `˚C`, `C` ou unité
  absente -> `°C` (unité absente = correction signalée). Kelvins : jamais
  convertis, entrée intacte + `FLAGGED`.
- Parenthèse optionnelle, éléments dans cet ordre séparés par `; ` : solvant
  (recopié, indices Unicode), pression, `dec.`, `lit. [réf] valeur`. Entrées
  reconnues : `(dec.)`, `décomp.`, `dec.` seul, `/ 15 mmHg`, `Et2O/hexane: [réf]
  185-187 °C`, éléments dans un autre ordre.
- **0 décimale** (valeurs principale et littérature) : sinon `FLAGGED`, valeur
  conservée. Plage inversée -> `FLAGGED`, jamais corrigée. Valeur de la
  littérature non exigée (produits connus non détectables).
- Sûreté : virgule décimale, deux solvants, élément en double, littérature
  illisible -> entrée intacte + `FLAGGED`. Toutes les entrées d'un paragraphe
  sont traitées (le texte entre elles est conservé). Labels français (`Pf`,
  `Tf`) non reconnus. `m.p.` / `b.p.` terminent une section RMN collée devant
  (`_OTHER_ANALYSIS_RE`, avec une valeur qui suit).

### Rf (`core/rules/rf.py`, `tests/test_rule_rf.py`)

- Format cible (décision du 2026-11-12, guide LCMCE) : `Rf = 0.38 (SiO₂;
  heptane/CH₂Cl₂ 1:1)` AVEC phase stationnaire. Label `Rf` en gras
  (`bold_label`), **f en indice Word** (`StyledSegment.subscript`, exception 7.8),
  R sans italique ; reste de l'entrée sans style.
- La valeur n'est JAMAIS modifiée. Contrôles (`FLAGGED`) : 2 décimales,
  intervalle [0 ; 1], phase stationnaire (SiO₂, silica, Al₂O₃, alumina, C18,
  RP…) absente, proportions de l'éluant absentes (`4:1`, `9/1`, `20 %`,
  `v/v`), parenthèse absente.
- Variantes : `Rf:`, `Rf 0.35`, `R.f.`, `R_f`, parenthèse avant la valeur
  (déplacée après), `,` après la phase stationnaire en tête (devient `;`).
  Éluant recopié (indices Unicode ; `C18`, `F254` jamais en indice).
- Sûreté : virgule décimale, plage (`0.3-0.4`), deux parenthèses, texte inconnu
  → entrée INTACTE + `FLAGGED`. Seule la première entrée `Rf` d'un paragraphe
  est traitée. Mention en prose ignorée. `Rf` termine une section RMN collée
  devant (`_OTHER_ANALYSIS_RE`).
- Limite : si le texte est déjà conforme, le document n'est pas réécrit : un
  `f` non mis en indice dans Word n'est donc pas corrigé (la règle ne voit que
  le texte).

---

## 5. Configuration (`core/config.py`)

- `RmnConfig` centralise les paramètres éditables ; ses **défauts reproduisent
  exactement** le comportement historique (les tests existants doivent rester
  verts sans fichier de préférences).
- Persistance dans `rules_config.json` (UTF-8, indenté) dans le dossier
  utilisateur : `config.user_config_path()` (`%APPDATA%\StandardisationRMN`
  sous Windows, `~/.config/standardisation-rmn` ailleurs, ou la variable
  `STANDARDISATION_RMN_CONFIG`). Jamais dans le dossier de l'application.
  L'ancien fichier à la racine (`LEGACY_CONFIG_PATH`) est seulement LU, tant
  que le nouveau n'existe pas.
- **Non versionné** (présent dans `.gitignore`) et recréé/relu sans exception
  s'il est absent ou corrompu. `config_from_dict` est tolérante champ par champ.
- État de processus via `get_config` / `set_config` / `reset_config`. Les règles
  lisent la config au moment de `apply`.

- `solvents` : table des solvants RMN (voir section 4), même validation que
  `multiplicities` ; table vide ou invalide -> défauts. Un fichier de
  préférences sans ce champ reçoit les défauts.

Pour ajouter un paramètre : l'ajouter à la dataclass avec un défaut qui préserve
le comportement actuel, l'intégrer à `config_to_dict` / `config_from_dict`
(avec validation), puis l'exposer dans le dialogue Paramètres de
`ui/web/index.html` (`fillSettings` / `collectSettings` dans `app.js`).

---

## 6. Séparation des couches

- `core/` ne doit **jamais** importer pywebview ni quoi que ce soit de `ui/`.
  Il doit rester testable sans interface graphique.
- La logique applicative testable vit dans `ui/controller.py` (sans interface) ;
  `ui/web_api.py` l'expose au JavaScript et n'importe pywebview qu'à
  l'exécution (boîtes de dialogue injectables : testable sans fenêtre). Ses
  attributs doivent rester PRIVÉS : pywebview expose au JavaScript tout
  attribut public.
- `ui/web/` ne fait qu'afficher et transmettre : aucune logique métier en
  JavaScript, aucune ressource distante (l'application fonctionne hors ligne).
  Aperçu dans un navigateur : servir `ui/web` en local et simuler
  `window.pywebview.api`, puis déclencher l'événement `pywebviewready`.
- Toute nouvelle logique métier va dans `core/`, pas dans l'UI.

---

## 7. Ajouter une nouvelle règle : notice pas à pas

Cette section suffit pour ajouter une règle sans connaître l'historique du
projet. Suivre les étapes **dans l'ordre**. En cas de doute sur un choix
métier marqué « ⚠ À valider », demander à l'utilisateur au lieu de trancher.

### 7.1 Principes (rappel, non négociables)

1. **Ne jamais inventer ni modifier une donnée** : une valeur numérique
   (déplacement, masse, pourcentage, température, Rf…) est recopiée
   caractère pour caractère. On ne corrige que la *forme* (espaces, ordre des
   champs, ponctuation, unités écrites, indices / exposants, gras / italique).
2. **Vérifier plutôt que corriger** : une incohérence détectée (masse
   recalculée différente, écart hors tolérance) produit une action `FLAGGED`
   avec la valeur attendue dans le message. La valeur du document reste.
3. **En cas de doute, ne rien toucher** : structure non reconnue → `FLAGGED`,
   `new_text` identique au texte d'entrée. Mieux vaut signaler que casser.
4. **Ne rien supprimer** : aucun texte hors de la portion reconnue n'est
   modifié. Préfixe et suffixe sont repris du texte ORIGINAL (espaces
   insécables compris).
5. **Idempotence** : appliquer la règle à sa propre sortie renvoie `UNCHANGED`.
   La règle doit donc reconnaître sa forme de sortie (indices Unicode `₂`,
   exposants `⁺`, `δ`…) aussi bien que la forme brute.
6. **Unicode pour les exposants / indices** (`¹`, `₂`, `⁺`, `⁻`, `ₘₐₓ`),
   jamais l'exposant / indice Word. Seule exception : le D de `[α]D`, le f de
   `Rf` et le R de `tR` (voir 7.8).
7. Messages d'action **en français**, compréhensibles par un chimiste, qui
   disent quoi vérifier. Forme imposée : **type d'écart fixe, puis `' : '`,
   puis les valeurs** (« Masse calculée incohérente avec la formule :
   165.0950 écrit, 165.0910 attendu pour C₁₀H₁₃O₂ ; valeur conservée,
   vérification manuelle requise. »). Le mode évaluation regroupe les écarts
   sur la partie avant `' : '` : aucune valeur ne doit y figurer.
8. **Reconnaître sa propre sortie** dans `applies` (voir section 3) : sinon
   une section déjà conforme n'est pas comptée par le mode évaluation.

### 7.2 Choisir le bon modèle

| Cas | Modèle à copier | Ce qu'on écrit |
|---|---|---|
| Nouvelle section RMN (`11B NMR`, `29Si NMR`, `15N NMR`…) | `core/rules/nmr_hetero.py` | une classe héritant de `NmrSectionRule` avec `name`, `description`, `nucleus` (ex. `"11B"`) et `format_signal` (réutiliser `nmr_common.format_signal_1h`). Tout le reste est hérité : label, `{1H}`, tiret, parenthèse, δ, tri, sûreté. |
| Entrée à structure fixe (analyse élémentaire, IR, mp, [α]D, Rf, UV-vis, HPLC) | `core/rules/hrms.py` | une classe héritant de `Rule` : une regex complète de l'entrée, une reconstruction, des vérifications. |

### 7.3 Boîte à outils existante (à réutiliser, ne pas dupliquer)

- `core/rules/nmr_common.py` :
  - `normalize_spaces(text)` : `\xa0` → espace, caractère pour caractère
    (les positions restent valables dans le texte original) ;
  - `subscript_formula("CDCl3")` → `CDCl₃` (chiffres après une lettre ou `)`) ;
  - `subscript_attribution(...)` : idem, mais laisse les numéros de position
    (`H4`, `C3`) ;
  - `to_superscript("13")` → `¹³` ;
  - `split_trailing_punctuation(body)` : sépare un `.` / `;` final ;
  - `_OTHER_ANALYSIS_RE` : labels qui terminent une section RMN collée (7.4,
    étape 5).
- `core/rules/mass.py` : `parse_formula("C6H5(CH3)2")` → `{"C": 8, "H": 11}`
  (accepte les indices Unicode, `None` si élément inconnu),
  `monoisotopic_mass`, `ion_mz`, `adduct_mass`, `ELECTRON_MASS`. Les masses
  sont **monoisotopiques** (pour la HRMS) : pour des pourcentages
  (analyse élémentaire), il faut une table de **masses atomiques moyennes**
  (C 12.011, H 1.008, N 14.007, O 15.999, S 32.06…) à ajouter dans ce module.
- `core/rules/hrms.py` : exemples de regex tolérantes aux variantes
  (`(?i:calcd|calc|calculated)`), de motif réutilisé nommé / non nommé
  (`_ion_pattern`), de détection « vraie entrée » vs mention en prose
  (`_labels`), et de découpage en `StyledSegment`.
- `core/config.py` : `get_config()` dans `apply` (jamais à l'import) ;
  `bold_label` sert aussi au label des analyses non RMN.

### 7.4 Étapes

1. **Écrire les tests d'abord** dans `tests/test_rule_<analyse>.py` (squelette
   en 7.6). Les lancer : ils doivent échouer.
2. **Créer `core/rules/<analyse>.py`** (renseigner `Action.highlights` sur les
   `FLAGGED`, voir « Surlignage dans l'interface ») : `from __future__ import annotations`,
   docstring de module en français qui donne le format cible et la liste des
   vérifications (squelette en 7.5).
3. **Respecter le contrat `RuleResult`** (section 3) :
   - `new_text` = texte COMPLET du paragraphe après correction ;
   - `segments` = découpage de la portion remplacée, dont la concaténation
     est exactement cette portion dans `new_text` ;
   - `replaced_text` = sous-chaîne EXACTE du texte original remplacée ;
   - texte inchangé → pas de `segments`, actions = les `FLAGGED` éventuels,
     sinon une seule action `UNCHANGED`. Les vérifications (masse, écart)
     restent signalées même si le texte est déjà conforme.
4. **L'ajouter au catalogue** : `available_rules()` dans `core/processor.py`
   (import local dans la fonction, comme les autres). Elle apparaît alors
   dans le CLI, l'UI et le rapport. Mettre à jour la liste attendue dans
   `tests/test_web_api.py::test_initial_state_lists_rules_and_settings`.
5. **Enregistrer son label dans `nmr_common._OTHER_ANALYSIS_RE`** (ex.
   `HRMS|IR|Anal\.|mp|\[α\]|Rf|UV`) pour qu'une section RMN collée devant
   (`… δ 77.0. IR (ATR) …`) s'arrête au bon endroit. Ajouter le test
   correspondant (modèle : `test_rule_hrms.py::test_nmr_section_stops_before_hrms`).
   Garder le motif strict (`(?<![A-Za-z])IR(?![A-Za-z])`) pour ne pas
   couper une attribution.
6. **Paramètre configurable** (seulement si utile, ex. tolérance) :
   - champ dans `RmnConfig` avec un défaut qui ne change rien au
     comportement existant ;
   - `config_to_dict` + `config_from_dict` (validation tolérante : un type
     invalide retombe sur le défaut ; un booléen n'est pas un nombre) ;
   - UI : un `<label>` + `<input>` dans le `fieldset` « Mise en forme » de
     `ui/web/index.html`, une ligne dans `fillSettings` et dans
     `collectSettings` de `ui/web/app.js` (modèle : `hrms-ppm`) ;
   - test aller-retour (modèle : `test_rule_hrms.py::test_hrms_tolerance_config_roundtrip`).
7. **Aperçu UI** (facultatif) : `renderNmr` dans `ui/web/app.js` imite gras /
   italique dans la liste des corrections. Affichage seulement, aucune
   logique métier en JavaScript.
8. **Documentation** : une section « Format cible `<analyse>` » dans
   `README.md` ; ici, une sous-section dans la section 4 (comportements
   voulus) et l'arborescence de la section 2.
9. **`python -m pytest`** : toute la suite doit être verte. Puis essayer la
   règle sur une dizaine de variantes réelles (script jetable, pas de
   nouveau `.docx` versionné) et ajouter un test pour chaque variante
   corrigée.

### 7.5 Squelette d'une règle à structure fixe

```python
"""Règle de standardisation des entrées <ANALYSE> (sortie stylisée).

Format cible : <exemple exact>

Vérifications (valeurs jamais modifiées) : <liste>.
"""

from __future__ import annotations

import re
from typing import List

from core.config import get_config
from core.rules import nmr_common
from core.rules.base import Action, ActionKind, Rule, RuleResult, StyledSegment

# Label isolé (pas au milieu d'un mot).
_LABEL_RE = re.compile(r"(?<![A-Za-z])<LABEL>(?![A-Za-z])")

# Entrée complète, du label à la dernière valeur. Une regex nommée et
# commentée par élément ; accepter la forme brute ET la forme de sortie.
_ENTRY_RE = re.compile(r"<LABEL>" r"...(?P<valeur>\d+(?:\.\d+)?)" r"(?P<end>\.(?!\d))?")


class XxxRule(Rule):
    name = "<ANALYSE>"
    description = "Format … ; valeurs jamais modifiées, … signalé si …"

    def applies(self, paragraph_text: str) -> bool:
        text = nmr_common.normalize_spaces(paragraph_text)
        # Ne s'applique pas à une simple mention en prose : exiger le label en
        # tête de paragraphe OU un indice de données après lui.
        return bool(_LABEL_RE.search(text))

    def apply(self, paragraph_text: str) -> RuleResult:
        config = get_config()
        text = nmr_common.normalize_spaces(paragraph_text)
        entry = _ENTRY_RE.search(text)
        if entry is None:
            return RuleResult(
                new_text=paragraph_text,
                actions=[Action(ActionKind.FLAGGED, "Entrée <ANALYSE> non reconnue : "
                                "laissée telle quelle, vérification manuelle.", self.name)],
            )
        flags: List[str] = []  # vérifications -> messages FLAGGED
        segments = [
            StyledSegment("<LABEL> (…)", bold=config.bold_label),
            StyledSegment(" …reste reconstruit, valeurs recopiées telles quelles…"),
        ]
        start, end = entry.span()
        new_text = paragraph_text[:start] + "".join(s.text for s in segments) + paragraph_text[end:]
        actions = [Action(ActionKind.FLAGGED, f, self.name) for f in flags]
        if new_text == paragraph_text:
            return RuleResult(new_text=paragraph_text, actions=actions or [
                Action(ActionKind.UNCHANGED, "Entrée déjà conforme.", self.name)])
        actions.insert(0, Action(ActionKind.CORRECTED, "Entrée <ANALYSE> reformatée.", self.name))
        return RuleResult(new_text=new_text, actions=actions, segments=segments,
                          replaced_text=paragraph_text[start:end])
```

### 7.6 Squelette de tests

```python
from core import config as cfg
from core.config import RmnConfig
from core.processor import build_registry, process_texts
from core.rules.base import ActionKind
from core.rules.xxx import XxxRule

RULE = XxxRule()
TARGET = "<sortie attendue exacte>"

def _flags(result):
    return [a.message for a in result.actions if a.kind == ActionKind.FLAGGED]

def test_typical_entry_is_normalized():
    assert RULE.apply("<entrée brute>").new_text == TARGET

def test_output_is_idempotent():
    result = RULE.apply(TARGET)
    assert result.new_text == TARGET
    assert [a.kind for a in result.actions] == [ActionKind.UNCHANGED]

def test_segments_match_new_text():
    result = RULE.apply("<entrée brute>")
    assert "".join(s.text for s in result.segments) in result.new_text

def test_values_are_never_changed():          # valeur incohérente -> signalée, conservée
    ...

def test_unrecognized_structure_is_flagged_unchanged():
    text = "<variante non prise en charge>"
    assert RULE.apply(text).new_text == text

def test_prose_mention_is_ignored():
    assert not RULE.applies("<phrase qui cite le label>")

def test_conform_output_is_recognized():      # pour le mode évaluation
    assert RULE.applies(TARGET)

def test_in_paragraph_with_nmr():             # chaîne complète
    final = process_texts([text], build_registry()).paragraphs[0].new_text
```

Une configuration non par défaut se teste avec `cfg.set_config(RmnConfig(...))`
dans le test : `conftest.py` remet les défauts après chaque test.

### 7.7 Pièges déjà rencontrés

- **Console Windows** : afficher du texte Unicode (`ẟ`, `₂`) dans un script
  lève `UnicodeEncodeError` (cp1252). Préfixer par
  `PYTHONIOENCODING=utf-8`, ou écrire dans un fichier.
- **Échappements** : écrire les regex en chaînes brutes `r"..."` ; pour
  combiner une classe Unicode (`"−"`), concaténer
  `r"\-" + "−–"` plutôt que d'écrire `"\-"` (avertissement
  Python). Dans une classe `[...]`, le tiret littéral se met en premier ou
  s'échappe.
- **Plage de déplacements** (décision du 2026-11-12) : `7.41 – 7.50`, tiret
  demi-cadratin ENTOURÉ d'espaces insécables (`nmr_common.RANGE_SEP`) ; même
  forme pour les plages IR. **Intégration** `5 H` (espace insécable,
  `nmr_common.format_integration`). En 1H, l'attribution suit les données du
  signal après un point-virgule : `(m, 5 H; OCH₂)` (le `;` est aussi accepté en
  entrée) ; en 13C l'attribution reste seule entre parenthèses.
- **Décimales contrôlées, jamais modifiées** (décision du 2026-11-12) : δ 2
  décimales en 1H (3 tolérées), 1 décimale pour 13C / 19F / 31P (2 tolérées), J
  1 décimale ; autrement `FLAGGED` « Nombre de décimales … inattendu : valeurs »
  (`nmr_common.check_decimals`, attribut `NmrSectionRule.shift_decimals`).
  Contrôle limité aux listes entièrement parsables. Une nouvelle section RMN
  fixe `shift_decimals` (défaut 1).
- **Température obligatoire** (3 éléments) : décision du 2026-11-12, inchangée.
- **Signe moins** : un nombre négatif peut arriver avec `-`, `−` (U+2212) ou
  `–` (U+2013, inséré par Word). Convertir pour le calcul, recopier tel quel
  en sortie (voir `nmr_common._to_float`).
- **Virgule décimale** (`165,0912`, fréquent en français) : ambiguë avec le
  séparateur de liste ; ne pas l'interpréter, signaler.
- **Idempotence** : la sortie contient des caractères que l'entrée n'avait
  pas (`₁₀`, `⁺`, `−`, `δ`). Les classes de caractères doivent les accepter,
  et les valeurs doivent être ramenées en ASCII avant calcul
  (`str.translate`, voir `hrms._TO_ASCII`).
- **Mention en prose** : « Les analyses HRMS ont été réalisées… » ne doit
  pas être signalée. Exiger un indice de données (`calcd`, `found`, `=`, un
  nombre…) ou le label en tête de paragraphe.
- **Parenthèses imbriquées** : `[^)]*` coupe `(CD3)2SO` ; tolérer un niveau
  (`(?:[^()]|\([^()]*\))*`).
- **`process_texts(texts, registry)`** renvoie un `ProcessingReport` : le
  texte final est `report.paragraphs[i].new_text` (seulement les paragraphes
  concernés par une règle).
- **Préférences enregistrées** : un utilisateur qui a déjà enregistré ses
  paramètres garde son ancienne table (ex. multiplicités) ; un nouveau défaut
  ne s'applique qu'après « Rétablir les valeurs par défaut ». Le dire dans le
  README quand on change un défaut.
- **Ordre des règles** : `available_rules()` fixe l'ordre d'application.
  Chaque règle n'édite que sa portion ; ne jamais dépendre de l'ordre.

### 7.8 Indice Word pour `[α]D`, `Rf`, `tR` (CONSTRUIT avec la règle Rf)

> Infrastructure en place (`StyledSegment.subscript`, `docx_io._segment_run`,
> tests dans `test_docx_io.py` et `test_rule_rf.py`) : les règles `[α]D` et
> `tR` n'ont plus qu'à poser `subscript=True` sur leur lettre. Le texte
> d'origine de cette section est conservé ci-dessous.

Unicode n'a pas d'indice pour D, f, R. Décision de l'utilisateur
(2026-11-08) : ces trois lettres, et elles seules, passent en indice Word.
Infrastructure à ajouter, avec des tests :

1. `core/rules/base.py` : champ `subscript: bool = False` dans
   `StyledSegment` (défaut sans effet sur les règles existantes).
2. `core/docx_io.py` : dans `_segment_run`, poser
   `run.font.subscript = True` quand `segment.subscript` est vrai. Garder
   `w:vertAlign` dans `_SEGMENT_STRIPPED_PROPS` (le style de base est
   toujours nettoyé).
3. Test dans `tests/test_docx_io.py` : un segment `subscript=True` produit
   un run en indice ; les autres non.
4. Le texte (`new_text`) reste `[α]D`, `Rf`, `tR` (l'indice n'est que de la
   mise en forme) : `process_texts` et l'idempotence ne changent pas.
5. Mettre à jour la section 4 (règle Unicode) et `_SEGMENT_STRIPPED_PROPS`
   (commentaire) pour citer cette exception.

### 7.9 Cahier des charges des règles restantes

Format de référence : ACS (*J. Org. Chem.*, *Org. Lett.*). Pour chaque règle :
format cible, variantes à accepter, vérifications. Ordre conseillé : analyse
élémentaire, IR, point de fusion, puis [α]D / Rf / HPLC (qui demandent 7.8),
puis UV-vis.

**Analyse élémentaire** (`core/rules/elemental.py`, label `Anal.`)
- Cible : `Anal. Calcd for C₁₀H₁₂O₂: C, 73.15; H, 7.37. Found: C, 73.02; H, 7.41.`
- Variantes : `Anal. calcd. for`, `Elemental analysis calcd for`, `Calc.`,
  `found`, séparateurs `,`/`;`, `N` et `S` présents ou non, `%` écrits.
- Vérifications : recalculer chaque pourcentage depuis la formule avec les
  masses atomiques MOYENNES (à ajouter dans `mass.py`) ; « Calcd » écart >
  0,01 (arrondi) → `FLAGGED` avec la valeur attendue ; `|Found − Calcd|` >
  0,4 (paramètre `ea_tolerance`, défaut 0.4) → `FLAGGED` ; un élément trouvé
  sans valeur calculée (ou l'inverse) → `FLAGGED`. Ordre des éléments C, H,
  N, S… conservé tel qu'écrit.

**IR** (`core/rules/ir.py`, label `IR`)
- **IMPLÉMENTÉE** (voir section 4). Cible retenue : `IR (ATR): ν̃(cm⁻¹) = 3420,
  1715, 1600` ; tri décroissant fixe ; forme RSC convertie. Notes d'origine
  ci-dessous conservées pour mémoire.
- Cible initiale (remplacée) : `IR (ATR) ν̃ 3420, 1715, 1600 cm⁻¹` (`ν̃` = ν + U+0303).
- Variantes : `IR (neat|film|KBr|ATR|CHCl3)`, `νmax`, `ν (cm-1)`, `vmax`
  (v latin), `cm-1`, `cm−1`, `cm^-1`, unité en tête (`νmax/cm⁻¹ 3420, …`,
  forme RSC), intensités `(s)`, `(br)`, `(w)` et attributions `(C=O)`.
- ⚠ À valider : `ν̃` (IUPAC) ou `νmax` en sortie ? Forme RSC conservée ou
  convertie ?
- Traitement : unité `cm⁻¹` Unicode en fin de liste ; nombres entiers
  recopiés ; tri décroissant SEULEMENT si tous les éléments sont parsables
  (même règle de sûreté que la RMN), sinon liste conservée + `FLAGGED` ;
  solvant / milieu en indices (`CHCl₃`).

**Point de fusion** (`core/rules/melting_point.py`, label `mp`)
- **IMPLÉMENTÉE** (voir section 4, sous-section m.p. / b.p.) avec la structure
  du guide LCMCE (`m.p.`, plage avec espaces, 0 décimale). Les notes
  ci-dessous, d'origine, sont conservées pour mémoire.
- Cible : `mp 128–130 °C` ; avec solvant : `mp 128–130 °C (EtOH)` ;
  littérature : `mp 128–130 °C (lit. 129–130 °C)`.
- Variantes : `m.p.`, `Mp`, `M.p.`, `128-130°C`, `128 - 130 ºC` (º ordinal),
  `˚C`, `(dec.)`, `(decomp.)`.
- ⚠ À valider : `m.p.` / `Mp` → `mp` ? Les labels français (`Pf`, `Tf`)
  sont-ils conservés comme `RMN` ?
- Traitement : tiret demi-cadratin dans la plage, espace insécable ou espace
  avant `°C`, `°` vrai (U+00B0) ; aucune conversion d'unité ; plage inversée
  (`130–128`) → `FLAGGED`, non corrigée.

**Pouvoir rotatoire** (`core/rules/optical_rotation.py`, label `[α]`)
- Cible : `[α]D²⁰ +25.3 (c 1.00, CHCl₃)` : D en indice Word (7.8),
  température en exposant Unicode, *c* en italique, concentration sans unité
  (g/100 mL implicite).
- Variantes : `[a]D`, `[α]20D`, `[α]D20`, `[α]D 20`, `[α]D^20`, `αD`,
  `c = 1.0`, `c 1.0 g/100 mL`, signe absent.
- ⚠ À valider : retirer l'unité `g/100 mL` écrite ? (sinon `FLAGGED`) ;
  ajouter `+` à une valeur positive sans signe ? (sinon `FLAGGED`).
- Vérification : température absente → `FLAGGED` (jamais inventée).

**Rf** (`core/rules/rf.py`, label `Rf`)
- **IMPLÉMENTÉE** (voir section 4, sous-section Rf). Cible retenue : `Rf = 0.38
  (SiO₂; heptane/CH₂Cl₂ 1:1)`, avec phase stationnaire.
- R en italique : non (le guide LCMCE ne le demande pas).

**HPLC / GC chirale** (`core/rules/chiral_hplc.py`, labels `HPLC`, `GC`, `SFC`)
- Cible : `HPLC (Chiralpak AD-H, hexane/i-PrOH 90:10, 1.0 mL/min, 254 nm):
  tR = 12.3 min (major), 14.5 min (minor); 95% ee` : R en indice Word, t en
  italique.
- Variantes : `t_R`, `tR (major)`, `ee = 95%`, `er 97.5:2.5`.
- Vérifications : aucune valeur recalculée ; si `er` et `ee` sont tous deux
  donnés, contrôler `ee = |a − b|` (`FLAGGED` si incohérent).

**UV-vis** (`core/rules/uv_vis.py`, label `UV`)
- Cible : `UV–vis (MeCN) λₘₐₓ (ε) 254 (12 000), 310 (3 500) nm` (ₘₐₓ en
  indices Unicode : U+2098, U+2090, U+2093).
- Variantes : `UV-Vis`, `UV/Vis`, `λmax`, `lambda max`, `log ε`,
  `ε / M⁻¹ cm⁻¹`.
- Traitement : unité en Unicode (`M⁻¹ cm⁻¹`), valeurs recopiées.

**Compléments RMN encore ouverts** (dans les règles existantes)
- Option `decoupled_13c` : écrire `¹³C{¹H} NMR` (notation JOC) quand
  l'entrée dit `13C NMR` ; défaut `False` (comportement actuel).
- Cohérence multiplicité / nombre de J : ÉCARTÉE (décision du 2026-11-12).
- ⚠ À valider : remplacer `septic` (coquille) par `sept` en sortie.

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
  dépendances d'exécution : `python-docx`, `pywebview` ; de développement :
  `pytest`, `pyinstaller` (construction des exécutables via
  `standardisation_rmn.spec` ; le CLI exécutable exclut l'interface, et les modèles
  `docx/templates` doivent rester embarqués pour les commentaires Word).
- Préférer des fonctions pures et testables dans `core/` ; isoler les effets de
  bord (I/O fichier, interface).

---

## 10. Garde-fous pour une modification assistée par IA

- Lire le code concerné **avant** de proposer un changement ; ne pas supposer un
  comportement non vérifié.
- Respecter les invariants des sections 3 et 4 : ils sont la raison d'être de
  l'outil (ne jamais inventer de chimie, ne jamais réordonner des signaux non
  parsables, conserver le mot d'entrée, Unicode plutôt que superscript Word).
- Après toute modification de code, exécuter `python -m pytest` et corriger les
  régressions avant de conclure.
- Garder `core/` libre de toute dépendance d'interface.
- Mettre à jour `README.md` et ce fichier si un comportement visible ou une
  règle métier change.
