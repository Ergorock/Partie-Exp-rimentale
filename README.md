# Standardisation de partie expérimentale (chimie organique)

Outil pour standardiser le formatage d'une partie expérimentale contenue dans
un fichier Word (`.docx`). On charge un `.docx` mal formaté et on récupère un
`.docx` corrigé, accompagné d'un rapport des corrections.

Six règles RMN (`1H NMR`, `13C NMR`, `19F NMR`, `31P NMR`, `11B NMR`, `29Si NMR`) et les règles
`HRMS`, `IR`, `Rf` et `m.p. / b.p.`, `Unités` et `Ordre des analyses` sont disponibles ; elles produisent une
sortie **stylisée** (gras / italique, exposants et indices Unicode). D'autres
règles (HRMS, IR…) peuvent être ajoutées facilement grâce à l'architecture
modulaire (voir plus bas).

## Conventions communes aux règles RMN

Les deux règles RMN partagent la logique du module `core/rules/nmr_common.py`
et appliquent les conventions suivantes.

### Label (en gras) et parenthèse

Seul le label (`¹H NMR`, `¹³C NMR`…) est écrit **en gras** ; la parenthèse qui
le suit reste en style normal. Le mot d'entrée
est **conservé tel quel** : `1H NMR` reste `NMR`, `1H RMN` reste `RMN` ; on
ajoute seulement l'exposant Unicode au nombre de masse (`1H` → `¹H`,
`13C` → `¹³C`, `19F{1H}` → `¹⁹F{¹H}`).

La parenthèse contient exactement **trois éléments** séparés par deux virgules :

1. la **fréquence** en MHz (ex. `400.18 MHz`) ;
2. le **solvant**, remplacé d'après la table des solvants (voir
   « Solvants configurables ») avec indices en Unicode (ex. `CDCl3` →
   `CDCl₃`, `dmso d6` → `DMSO-d₆` avec le *d* en italique) ;
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

### Solvants configurables

Le solvant (2ᵉ élément de la parenthèse des sections RMN : `1H`, `13C`, `19F`,
`31P`, `11B`, `29Si`) est cherché dans une table **Solvants RMN** des
Paramètres : « écrit dans le document » → « devient ». La correspondance porte
sur l'élément entier, sans tenir compte de la casse ni des espaces multiples
(`dmso  D6` = `DMSO-d6`). Dans « devient », entourez de `*` le texte à mettre
**en italique** (`DMSO-*d*6` → `DMSO-d₆` avec le *d* en italique) ; les indices
Unicode sont ajoutés automatiquement après une lettre ou une parenthèse
fermante. Une valeur au balisage `*` non apparié est ignorée (l'entrée est
recopiée).

- **Solvant absent de la table** : indices automatiques comme avant, mais le
  texte n'est pas remplacé et un signalement « Solvant absent de la table »
  est émis. En **mode évaluation**, un solvant inconnu rend donc la section
  « à vérifier » (le score peut baisser tant que la table est incomplète).
- La table par défaut couvre `CDCl3`, `DMSO-d6` (+ `DMSO d6`, `d6-DMSO`,
  `(CD3)2SO`), `CD3OD` (+ `MeOD`), `C6D6`, `acetone-d6`, `D2O`, `CD3CN`,
  `CD2Cl2`, `THF-d8`, `pyridine-d5`, `toluene-d8`, `CD3COOH`, `CD3COOD`,
  `TFA-d`.
- Un utilisateur qui a déjà enregistré ses paramètres reçoit cette table par
  défaut (le champ était absent de son fichier) ; ses modifications ultérieures
  sont conservées. **Rétablir les valeurs par défaut** recharge la table
  d'origine.
- Limite : si le texte du paragraphe est déjà conforme, le document n'est pas
  réécrit ; un *d* non mis en italique dans Word n'est alors pas corrigé.

### Symbole δ (en italique)

Le symbole δ qui précède la liste des signaux est écrit **en italique** et
suivi de `(ppm) =` en style normal (`δ (ppm) = 7.26 (s, 1 H)`, forme du guide
LCMCE). Les variantes d'entrée (`δ`, `ẟ`, avec ou sans `(ppm) =`) sont
normalisées en cette forme. Le symbole `J` des constantes de
couplage (`J = 8.4 Hz`) est lui aussi mis en italique (désactivable).

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
¹H NMR (<fréquence> MHz, <solvant>, <température> K) δ (ppm) = <signaux>
```

Pour chaque signal, l'ordre est : déplacement chimique (valeur unique ou plage
`a – b`, tiret demi-cadratin entouré d'espaces insécables) → multiplicité →
`J = x.x Hz` (une décimale, si présente) → intégration (`5 H`, avec espace
insécable) ; les données sont suivies, après un point-virgule, de l'attribution
(`m, 5 H; OCH₂`). Le point-virgule est aussi reconnu en entrée ; l'attribution
reste optionnelle. Multiplicités autorisées par défaut : simples
(`s`, `d`, `t`, `q`, `quint`, `sext`, `sept`, `hept`, `septic`, `m`), composées
(`dd`, `dt`, `td`, `tt`, `dq`, `qd`, `ddd`, `ddt`, `dtd`, `tdd`, `dddd`, `qt`,
`tq`), larges (`br s`, `br d`…, avec `bs`/`bd`/`br. s` normalisés en `br x`) et
apparentes (`app t`…). Une multiplicité hors table (`ddq`…) ou un champ inconnu placé avant
un champ reconnu rendent le signal non parsable (liste laissée telle quelle et
signalée) ; ajoutez la multiplicité dans les paramètres pour qu'elle soit
reconnue. Plusieurs constantes sont acceptées : `J = 8.4, 2.1 Hz` ou
`J = 8.4 Hz, J = 2.1 Hz` (forme d'entrée conservée).

Le label est aussi reconnu écrit avec un tiret (`1H-NMR` → `¹H NMR`). Un
déplacement négatif peut être écrit avec un trait d'union, le signe moins
Unicode `−` ou un tiret `–` (inséré par Word) : le signe est conservé tel quel.
Dans l'attribution, seuls les groupes chimiques passent en indices (`OCH3` →
`OCH₃`, `N(CH3)2` → `N(CH₃)₂`) ; les numéros de position (`H4`, `C3`, `C4'`)
restent inchangés. Le solvant accepte une parenthèse (`(CD3)2SO` → `(CD₃)₂SO`).

La mise en forme Word du paragraphe est conservée : le texte hors section garde
toutes ses propriétés (police, taille, couleur…), et la section reformatée
reprend la police de son texte d'origine, sans exposant/indice Word. Un
paragraphe dont le texte n'est pas entièrement porté par des runs simples (lien
hypertexte, champ…) n'est pas modifié et est signalé.

## Format cible `13C NMR`

```
¹³C NMR (<fréquence> MHz, <solvant>, <température> K) δ (ppm) = <signaux>
```

La règle reconnaît en entrée aussi bien `13C NMR` que `13C RMN`, ainsi que la
forme découplée `13C{1H} NMR` (→ `¹³C{¹H} NMR`). Les signaux
découplés sont donnés par leur déplacement chimique (une décimale) suivi d'une
attribution optionnelle entre parenthèses (`Cq`, `CH`, `CH₂`, `CH₃`, `C=O`…).
La multiplicité et la constante de couplage `J` sont conservées lorsqu'un
couplage est présent (ex. `162.3 (d, J = 245 Hz)` pour un couplage C–F).

## Formats cibles `19F NMR` et `31P NMR`

```
¹⁹F{¹H} NMR (<fréquence> MHz, <solvant>, <température> K) δ (ppm) = <signaux>
³¹P{¹H} NMR (<fréquence> MHz, <solvant>, <température> K) δ (ppm) = <signaux>
```

Même traitement que `1H NMR` (parenthèse, δ, tri, règle de sûreté), avec
découplage `{1H}` optionnel conservé ; intégration acceptée (`3 F`).

## Contrôle du nombre de décimales (RMN)

Les valeurs ne sont jamais arrondies ni corrigées ; un nombre de décimales
inattendu est seulement **signalé** (à vérifier), pour les signaux analysés :

- déplacement δ : 2 décimales pour le `1H` (3 tolérées, cas ambigu), 1 décimale
  pour `13C`, `19F`, `31P` (2 tolérées) ; les deux bornes d'une plage sont
  contrôlées ;
- constante de couplage `J` : 1 décimale.

Une liste de signaux non analysable n'est pas contrôlée (elle est déjà
signalée).

## Formats cibles `11B NMR` et `29Si NMR`

```
¹¹B NMR (<fréquence> MHz, <solvant>, <température> K) δ (ppm) = <signaux>
²⁹Si{¹H} NMR (<fréquence> MHz, <solvant>, <température> K) δ (ppm) = <signaux>
```

Même traitement que `31P NMR` (parenthèse, δ, tri, règle de sûreté, découplage
`{1H}` optionnel). δ s'écrit avec 1 décimale (2 tolérées). La largeur à
mi-hauteur des pics larges du `11B` (en Hz) n'est pas reconnue : un champ
inconnu rend le signal non analysable, la liste est alors laissée telle quelle
et signalée.

## Règle `Unités`

Pose une **espace insécable** entre un nombre et son unité dans la procédure :
`220 mg`, `0.9 mmol`, `6.3 mL`, `12 min`, `2 h`, `77 %`, `25 °C` ; `10 mol %`
devient `10 mol%` (le `%` est collé) et `ºC` / `˚C` deviennent `°C`. Seule la
forme change : aucun nombre, aucune unité ajoutée.

- Les unités d'une lettre (`g`, `h`, `L`, `M`) ne sont traitées que si une
  espace est déjà écrite (`5g` peut être le composé 5g) ; une espace fine
  insécable (U+202F) déjà présente est conservée.
- Le texte à partir du premier label d'analyse (RMN, HRMS, IR, Rf, m.p., b.p.)
  est laissé aux règles d'analyse. Les `MHz`, `K` et `Hz` des parenthèses RMN
  restent donc écrits avec une espace ordinaire.
- Un rendement avec décimale dans `(843 mg, 77.5 %)` est signalé (0 décimale
  attendue), sans modification.

## Règle `Ordre des analyses`

Contrôle, **dans un paragraphe**, l'ordre du guide LCMCE : Rf ; m.p./b.p. ;
`1H` ; `13C` ; autres RMN ; IR ; UV/Vis ; MS ; HRMS ; analyse élémentaire. Un
ordre différent est signalé (« 1H NMR après 13C NMR »), le texte n'est jamais
déplacé. L'ordre entre paragraphes n'est pas contrôlé (on ne sait pas où un
composé s'arrête) ; un paragraphe bien ordonné n'est pas compté en mode
évaluation.

## Format cible `HRMS`

```
HRMS (ESI-TOF) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.0910; Found 165.0912.
```

Format de l'ACS (*J. Org. Chem.*) : label `HRMS` seul en gras,
*m/z* en italique, ion normalisé et placé avant `Calcd for` (`[M+H]+` →
`[M + H]⁺`, `[M-H]-` → `[M − H]⁻`, `(M+)` ou `M+•` → `[M]⁺` / `[M]⁺•`,
`[M+2H]2+` → `[M + 2H]²⁺`), formule en indices Unicode, `calcd` / `found` →
`Calcd` / `Found`, séparateur `;`. L'ion peut être écrit avant `calcd` ou
après la formule.

**Les masses ne sont jamais modifiées**, seulement vérifiées :

- la masse calculée est recalculée depuis la formule (masses monoisotopiques,
  `core/rules/mass.py`). La formule peut être celle de l'ion (`C10H13O2`) ou
  la formule neutre (`C10H12O2`) combinée à l'ion, avec ou sans la masse de
  l'électron. Une valeur incohérente est signalée avec la valeur attendue ;
- un écart masse trouvée / calculée supérieur à la tolérance (5 ppm par
  défaut, paramétrable) est signalé ; un écart absolu supérieur à 0.003 Da
  (paramétrable) l'est aussi, indépendamment des ppm ;
- pour une masse inférieure à 500, 4 décimales sont attendues (masses calculée
  et trouvée) : un autre nombre de décimales est signalé, sans modification ;
- un ion ou une méthode d'ionisation absents sont signalés ; un élément
  inconnu de la table rend la masse non vérifiable (signalé).

Une entrée dont la structure n'est pas reconnue (virgule décimale, ordre
inhabituel…) est laissée telle quelle et signalée. Une simple mention de
« HRMS » dans une phrase (sans `calcd` / `found`) est ignorée. Une section RMN
collée devant une entrée HRMS s'arrête au label `HRMS`.

## Format cible `IR`

```
IR (ATR): ν̃(cm⁻¹) = 3420, 1715, 1600
```

Label `IR` seul en gras. La méthode (`KBr`, `film`, `neat`, `ATR`, `CHCl3` →
`CHCl₃`…) est recopiée entre parenthèses. Les bandes sont des **entiers**
recopiés tels quels et triés du plus grand au plus petit (tri fixe) ;
l'attribution ou l'intensité entre parenthèses est conservée
(`1715 (C=O)`, `3420 (br)`). `ν̃` est ν + U+0303 et l'unité `cm⁻¹` est écrite en
Unicode.

Variantes d'entrée acceptées : symbole `νmax`, `ν`, `ν̃`, `vmax`, `v` ou aucun ;
unité `cm-1`, `cm−1`, `cm^-1`, `cm⁻¹` en fin de liste, en tête (`νmax/cm-1`),
entre parenthèses ou dans la parenthèse de la méthode (`IR (ATR, cm-1)`) ;
séparateur `=` ou `:` optionnel ; ponctuation finale conservée.

Une plage (OH des acides) est acceptée : `3300-2400 (m)` devient
`3300 – 2400 (m)` (tiret demi-cadratin entouré d'espaces insécables) et est
triée sur sa borne haute.

Rien n'est jamais modifié ni arrondi. L'entrée est laissée telle quelle et
signalée si la méthode est absente, si une bande est décimale (`1715.5`) ou
écrite avec une virgule décimale, si du texte figure hors parenthèse ou si une
parenthèse est imbriquée. Une section RMN ou HRMS collée devant une entrée IR
s'arrête au label `IR`, et l'entrée IR s'arrête au label suivant.

## Format cible `Rf`

```
Rf = 0.38 (SiO₂; heptane/CH₂Cl₂ 1:1)
```

Label `Rf` en gras, avec le **f en indice Word** (seule exception, avec `[α]D`
et `tR` à venir, à la règle « indices en Unicode » : Unicode n'a pas d'indice
pour cette lettre). La valeur est recopiée telle quelle ; la parenthèse donne la
phase stationnaire puis l'éluant et ses proportions, avec indices Unicode
(`CH2Cl2` → `CH₂Cl₂`).

Variantes acceptées : `Rf:`, `Rf 0.35`, `R.f.`, `R_f`, parenthèse écrite avant
la valeur (`Rf (hexane/EtOAc 9:1) = 0.35`, déplacée après), `,` après la phase
stationnaire en tête (devenu `;`).

Signalé sans rien modifier : valeur qui n'a pas 2 décimales, valeur hors de
[0 ; 1], phase stationnaire absente, proportions de l'éluant absentes,
parenthèse absente. Entrée laissée telle quelle et signalée : virgule décimale,
plage (`0.3-0.4`), deux parenthèses. Seule la première entrée `Rf` d'un
paragraphe est traitée. Si le texte est déjà conforme, le document n'est pas
réécrit : un `f` non mis en indice dans Word n'est donc pas corrigé.

## Format cible `m.p.` / `b.p.`

```
m.p. 185 – 186 °C (Et₂O/hexane; dec.; lit. [12] 185 – 187 °C)
b.p. 80 °C (15 mmHg)
```

Même règle pour le point de fusion et le point d'ébullition. Label en gras
(`mp`, `m.p.`, `Mp`, `melting point`… → `m.p.` ; `bp`, `b.p.`… → `b.p.`).
Température entière ou plage (tiret demi-cadratin entouré d'espaces
insécables), toujours en `°C` : `ºC`, `˚C`, `C` ou une unité absente deviennent
`°C` (l'ajout est signalé) ; une température en kelvins n'est jamais
convertie.

La parenthèse suit un ordre imposé, éléments séparés par `; ` : solvant de
recristallisation, pression, `dec.` (décomposition), `lit.` suivi d'une
référence éventuelle `[12]` et de la valeur de la littérature. L'ordre d'entrée
est rétabli (`(dec.)`, `décomp.`, `/ 15 mmHg`, `Et2O/hexane: [12] 185-187 °C`
sont reconnus).

Signalé sans rien modifier : valeur avec décimale (0 attendue), plage inversée
(`130 – 128`). Entrée laissée telle quelle et signalée : kelvins, virgule
décimale, deux solvants, élément en double. Tous les points de fusion et
d'ébullition d'un paragraphe sont traités. Les labels français (`Pf`, `Tf`)
ne sont pas reconnus.

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
   automatiquement. Les cas sont **surlignés dans le texte**
   (légende au-dessus de la liste) : **vert** = texte modifié par la
   standardisation (une espace insécable ajoutée apparaît comme un petit bloc
   vert), **ambre** = passage à vérifier (la valeur ou l'entrée en cause), **violet** =
   marqueur inséré pour une donnée manquante. Les notes en marge et la pastille
   devant chaque ligne reprennent les mêmes couleurs. **Ouvrir dans Word** ouvre le fichier produit.

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
- **Solvants RMN** : table « écrit » → « devient » (balisage `*italique*`,
  indices automatiques), même fonctionnement que les multiplicités ; voir
  « Solvants configurables ».
- **Règle Ponctuation** : supprime les espaces avant `:` et `;`, réduit la
  ponctuation doublée (`,,` `;;` `::` `..`) ; deux ponctuations différentes
  collées sont seulement signalées.
- **Remplacer la virgule décimale par un point** (coché par défaut) : `7,26 (s`
  devient `7.26 (s` dans les signaux RMN, seulement si le cas est non ambigu ;
  sinon la liste est laissée telle quelle et signalée. Décoché : ancien
  comportement. Un utilisateur ayant déjà enregistré ses paramètres reçoit la
  valeur par défaut (cochée) car le champ est absent de son fichier.
- **Contrôler la température** (coché par défaut) : décoché, le 3ᵉ élément de
  la parenthèse est laissé tel quel (pas de marqueur si absente, pas de
  normalisation ni de signalement d'unité) ; une parenthèse de moins de 2 ou de
  plus de 3 éléments reste signalée.
- **Marqueur de température manquante** : texte inséré lorsqu'une température
  est absente ou illisible (défaut `[??? K]`). Tant qu'il garde sa forme par
  défaut, il suit l'unité choisie (`[??? °C]`).
- **Ordre des signaux** : décroissant (défaut), croissant ou ordre du document.
- **Label en gras**, **symbole δ en italique** et **J en
  italique** : activent ou désactivent ces styles.
- **Écart HRMS toléré (ppm)** : au-delà, l'écart entre masse trouvée et masse
  calculée est signalé (défaut 5 ppm).
- **Écart HRMS absolu toléré (Da)** : critère indépendant du précédent, appliqué
  en plus (défaut 0.003 Da, usage du guide LCMCE).
- **Évaluation** : pourcentage minimal de sections conformes pour chaque note
  (défaut : Parfait 100, Très bon 90, Bon 75, Correct 50 ; en dessous :
  Mauvais). Les seuils doivent être décroissants entre 0 et 100, sinon les
  valeurs par défaut sont reprises.
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
# évaluation seule, aucun fichier écrit :
python cli.py --evaluer "partie exp.docx"
```

### Mode évaluation

**Évaluer sans modifier** (interface) ou `--evaluer` (ligne de commande) note
la conformité d'un document **sans rien écrire**. Chaque section reconnue
(section RMN, entrée HRMS…) est classée :

- **conforme** : rien à corriger ni à signaler ;
- **corrigeable** : le format n'est pas respecté, mais **Standardiser** le
  corrige automatiquement ;
- **à vérifier** : un point demande une intervention (signalement, marqueur
  de donnée manquante).

Le **score** est le pourcentage de sections conformes ; la **note**
(Parfait, Très bon, Bon, Correct, Mauvais) en découle selon les seuils des
Paramètres. Le résultat détaille le score par règle, les **règles non
respectées** regroupées par type (« Fréquence normalisée », « Masse calculée
incohérente avec la formule »…) avec le nombre de sections concernées, et
chaque section non conforme. Un document déjà standardisé est reconnu (labels
`¹H NMR`, `¹³C{¹H} NMR`… en exposants) : l'évaluer après **Standardiser**
montre ce qui reste à vérifier à la main.

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
  evaluation.py     Mode évaluation : score, note, écarts (sans écrire)
  rules/
    base.py         Interface Rule + types Action / RuleResult / StyledSegment
    registry.py     Registre ordonné des règles
    nmr_common.py   Helpers partagés RMN (exposants/indices Unicode, parenthèse,
                    segment de section, parsing/tri/formatage des signaux)
    nmr_section.py  Base commune des règles de section RMN (localisation,
                    parenthèse, delta, signaux, sortie stylisée)
    nmr_1h.py       Règle 1H NMR (noyau + formatage d'un signal)
    nmr_13c.py      Règle 13C NMR (noyau + formatage d'un signal)
    nmr_hetero.py   Règles 19F NMR, 31P NMR, 11B NMR et 29Si NMR
    hrms.py         Règle HRMS (format + vérification des masses)
    ir.py           Règle IR (méthode, bandes entières triées, cm⁻¹)
    rf.py           Règle Rf (f en indice Word, phase stationnaire, éluant)
    melting_point.py  Règle m.p. / b.p. (plage, °C, solvant, pression, dec., lit.)
    mass.py         Masses monoisotopiques, formule brute, m/z d'un ion
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
- `13C NMR` — `core/rules/nmr_13c.py` (sortie stylisée, implémentée) ;
- `19F NMR`, `31P NMR` — `core/rules/nmr_hetero.py` (sortie stylisée) ;
- `HRMS` — `core/rules/hrms.py` (sortie stylisée, masses vérifiées) ;
- `IR` — `core/rules/ir.py` (sortie stylisée, bandes entières triées) ;
- `Rf` — `core/rules/rf.py` (sortie stylisée, f en indice Word) ;
- `m.p. / b.p.` — `core/rules/melting_point.py` (structure imposée) ;
- `11B NMR`, `29Si NMR` — `core/rules/nmr_hetero.py` ;
- `Unités` — `core/rules/units.py` (espace insécable nombre-unité) ;
- `Ordre des analyses` — `core/rules/analysis_order.py` (contrôle seulement).

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
