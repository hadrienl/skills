---
name: video
description: Tourner et monter une vidéo de démo d'app (iOS au simulateur, Android à l'émulateur, ou application web dans un Chrome piloté) à la charte de N'IMPORTE QUELLE marque — le template est extrait d'un fichier fourni (pptx/potx, Keynote, PDF, capture ou image, logo SVG/PNG, CSS, tokens JSON, polices). Montage vertical, paysage côte à côte ou paysage web (fenêtre de navigateur + curseur animé), 60 i/s, narration Voicebox, versions multilingues. À utiliser pour « fais une vidéo de mon app », « filme la démo avec la charte de X », « /video ». Pour la charte Prisme.ai, préférer /prisme-video.
---

# video

Version générique de `prisme-video` : **même méthode de tournage et de montage, sans la charte Prisme.ai**.
La charte vient d'un fichier que fournit l'utilisateur, transformé en template.

**La méthode complète est dans [`METHODE.md`](METHODE.md)** — la lire avant de tourner : principes de montage
(rythme, aucun silence > 2,5 s, jamais d'accélération), pilotage iOS / Android / web (Chrome : `scripts/web.mjs`,
§ 2 bis), formats vertical / paysage duo / paysage web, **lecteur web multilingue** (§ 5 ter, déroulé type en
tête), narration Voicebox avec **sélection des prises par timbre** (§ 6) et **boucle d'écoute obligatoire**
(§ 6 ter), fond musical, publication (Mintlify). Elle est écrite pour la charte Prisme.ai ; ici :
- la charte vient de `VIDEO_TEMPLATE` (§ 1-2 ci-dessous) au lieu de `template/` Prisme.ai ;
- **aucune référence de voix fournie** : pour une voix clonée, valider des prises à l'oreille puis
  `voiceover.py plan.json --make-ref <prises> --language <l>` (§ 6 ter, étape 5) ; avant cela l'échantillon du
  profil Voicebox sert de référence provisoire ;
- **aucune musique fournie** : `package_player.py … --music <fichier>` (`default` cherche `$VIDEO_TEMPLATE/music/`) ;
  prompt de génération musicale dans METHODE.md § 5 ter ;
- les exemples (sandbox Prisme.ai, agents, docs.prisme.ai) sont à transposer à l'app filmée.

## 1. Demander le template (toujours en premier)

Avant de filmer, demander à l'utilisateur **la charte à appliquer**, en listant les formats gérés :

| Format | Ce qui est extrait |
|---|---|
| `.pptx` `.potx` `.ppsx` (PowerPoint, ou Google Slides téléchargé en pptx) | couleurs du thème et réellement utilisées, fond de la 1re diapo, police des titres (gros textes) et du texte, images à fond transparent (logos) |
| `.key` (Keynote) | exporté en PDF via Keynote, puis comme un PDF |
| `.pdf` (charte graphique, présentation) | palette de la 1re page |
| `.png` `.jpg` `.webp` (capture du site, moodboard) | palette dominante ; une image à fond transparent devient le logo |
| `.svg` / `.png` transparent (logo) | logo, décliné automatiquement en version blanche pour les fonds sombres |
| `.css` `.scss` | variables `--x: #hex` (`primary`/`brand`/`accent` = couleur principale), `font-family` (celle des `h1`/`h2` = titres) |
| `.json` | tokens `{colors:{…}, fonts:{…}}`, ou un `theme.json` déjà au bon format (utilisé tel quel) |
| `.ttf` `.otf` | polices : la 1re pour les titres, la 2e pour le texte |

Les sources se **combinent** (ex. un pptx + un logo SVG + une police). Un lien Google Slides/Drive :
télécharger d'abord le fichier (outil Google Drive, export pptx). Une URL de site : faire une capture puis
passer l'image. Sans aucun fichier : proposer une couleur principale + un logo, ou un template neutre.

Polices : cherchées parmi les polices installées, sinon téléchargées depuis Google Fonts (statique, ou
variable avec graisse Bold appliquée aux titres), sinon Arial. Les polices embarquées d'un pptx (EOT) sont
inutilisables : le nom suffit à les retrouver.

## 2. Construire et valider le template

```bash
SK="<ce dossier>/scripts"; T=<dossier de travail>/template
python3 "$SK/extract_template.py" charte.pptx logo.svg --out "$T" --name "Nom de la marque"
```
Sortie : `theme.json` (même schéma que `template/theme.json`), `logo-color.png`,
`logo-white.png`, `fonts/`, et **`preview.png`** (couverture + page d'étape). **Montrer `preview.png` à
l'utilisateur et le faire valider** avant de tourner ; corriger `theme.json` à la main si une couleur est mal
attribuée (rôles : `cover_bg`, `primary`, `ink`, `body`, `muted`, `border`, `page_bg`…). Le script ne
fabrique pas de grand symbole de couverture (`mark_light_blue`) : l'ajouter à `assets` si la marque en a un.
Les textes de pied de page viennent de `labels.footer_left` / `labels.footer_right` (vides par défaut —
ne pas inventer de mention « confidentiel »).

## 3. Tourner et monter avec ce template

Suivre [`METHODE.md`](METHODE.md) (préparation, pilotes iOS/Android/web, scénario, rythme) en passant le
template par la variable d'environnement **`VIDEO_TEMPLATE`** :

```bash
export VIDEO_TEMPLATE="$T"
python3 "$SK/montage.py" --src rec.mp4 --out demo.mp4 --card "Sur-titre|Titre|Sous-titre|Pastille" --seg "…"   # vertical
python3 "$SK/montage_duo.py" plan.json demo.mp4                                                              # paysage iOS + Android
python3 "$SK/montage_web.py" plan.json demo.mp4                                                              # paysage web (Chrome)
```
Dans `plan.json` (paysage) : `footer`, `unavailable` et `device_labels` (`{"ios": "…", "android": "…"}`)
remplacent les textes par défaut, pensés pour Prisme.ai. L'identifiant d'app à piloter (`bundle id`,
package Android, URL web) et les coordonnées des gestes sont propres à chaque app : faire un essai à blanc.
En web, le halo de clic prend la couleur `primary` du template ; la barre d'adresse dessinée (`"url"`) ne
change pas avec la charte (pastilles macOS, fond clair).

**Lecteur web multilingue** (une vidéo aux captures seules, une voix et des sous-titres par langue, tous les
textes en HTML, à la charte du template) : plan multilingue (`"langs"`, textes `{"en": …, "fr": …}`), puis
`voiceover.py plan.json`, puis `package_player.py plan.json out/ [--base-url /tutorials/<nom>/]` → dossier
statique (`index.html` + `player.*` + médias + `snippet.mdx` pour Mintlify). Détails, contraintes Mintlify et
choix techniques (Web Audio, vitesses sans changement de hauteur, plein écran de toute la composition,
hébergeurs sans `Range`) : [`METHODE.md`](METHODE.md) § 5 ter ; exemple de plan :
`examples/web-multilang-plan.json` (le `scenarios/web-multilang/plan.json` cité dans METHODE.md).

## Limites connues
- Heuristique de couleurs : fiable sur un pptx ou un CSS, approximative sur une simple image (la couleur la
  plus présente n'est pas toujours la couleur de marque) → toujours faire valider l'aperçu.
- La mise en page (couverture pleine couleur, pages blanches à titre + écran en carte) est fixe ; seuls
  couleurs, polices, logos et textes changent.
- Keynote doit être installé pour les `.key` ; `qlmanage` (macOS) rend les PDF et SVG.
