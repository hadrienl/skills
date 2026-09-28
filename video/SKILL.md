---
name: video
description: Tourner et monter une vidéo de démo d'app mobile (iOS au simulateur, Android à l'émulateur) à la charte de n'importe quelle marque — le template est extrait d'un fichier fourni (pptx/potx, Keynote, PDF, capture ou image, logo SVG/PNG, CSS, tokens JSON, polices). Pilotage scripté des apps, montage vertical 1080x1920 ou paysage iOS + Android côte à côte en 60 i/s, voix off générée par Voicebox, versions multilingues. À utiliser pour « fais une vidéo de mon app », « filme la démo avec la charte de X », « ajoute une voix off », « /video ».
---

# video

Produit une courte vidéo de démo lisible et fluide : **peu d'actions, chacune précédée d'une courte
pause sur l'état de départ, en temps réel**, habillée à la charte de la marque.

## 1. Demander le template (toujours en premier)

Demander à l'utilisateur **la charte à appliquer**, en listant les formats gérés :

| Format | Ce qui est extrait |
|---|---|
| `.pptx` `.potx` `.ppsx` (PowerPoint, ou Google Slides téléchargé en pptx) | couleurs du thème et réellement utilisées, fond de la 1re diapo, police des titres (gros textes) et du texte, images à fond transparent (logos) |
| `.key` (Keynote) | exporté en PDF via Keynote, puis comme un PDF |
| `.pdf` (charte graphique, présentation) | palette de la 1re page |
| `.png` `.jpg` `.webp` (capture du site, moodboard) | palette dominante ; une image à fond transparent devient le logo |
| `.svg` / `.png` transparent (logo) | logo, décliné en version blanche pour les fonds sombres |
| `.css` `.scss` | variables `--x: #hex` (`primary`/`brand`/`accent` = couleur principale), `font-family` (celle des `h1`/`h2` = titres) |
| `.json` | tokens `{colors:{…}, fonts:{…}}`, ou un `theme.json` déjà au bon format (utilisé tel quel) |
| `.ttf` `.otf` | polices : la 1re pour les titres, la 2e pour le texte |

Les sources se **combinent** (ex. un pptx + un logo SVG + une police). Un lien Google Slides/Drive :
télécharger d'abord le fichier (export pptx). Une URL de site : faire une capture et passer l'image.
Sans aucun fichier : utiliser `template/` (neutre, gris anthracite) ou partir d'une couleur + un logo.

Polices : cherchées parmi les polices installées, sinon téléchargées depuis Google Fonts (statique, ou
variable avec graisse Bold appliquée aux titres), sinon Arial. Les polices embarquées d'un pptx (EOT) sont
inutilisables : leur nom suffit à les retrouver.

## 2. Construire et valider le template

```bash
SK="<ce dossier>/scripts"; W=<dossier de travail>; T=$W/template
python3 "$SK/extract_template.py" charte.pptx logo.svg --out "$T" --name "Nom de la marque"
export VIDEO_TEMPLATE="$T"          # lu par les scripts de montage (défaut : template/ de ce skill)
```
Sortie : `theme.json` (rôles `cover_bg`, `primary`, `ink`, `body`, `muted`, `border`, `page_bg`…),
`logo-color.png`, `logo-white.png`, `fonts/` et **`preview.png`** (couverture + page d'étape).
**Montrer `preview.png` et le faire valider** avant de tourner ; corriger `theme.json` à la main si une
couleur est mal attribuée. Facultatif : un grand symbole de couverture (`assets.mark_light_blue`, PNG
transparent). Pied de page : `labels.footer_left` / `labels.footer_right` (vides par défaut — ne rien inventer).

## 3. Principes de montage

1. **Une vidéo = 2 à 3 actions** (ou une étape par fonctionnalité en format paysage), pas de tour exhaustif.
2. **Pause ~1,5 s sur l'état initial** avant chaque action, titre de l'étape déjà affiché. 3,5 s paraît mou.
3. **Rythme serré** : ≤ 0,5 s entre deux gestes ; saisie fluide, sans pause après chaque mot.
4. **Jamais d'accélération** (×2 = saccadé et illisible) : on **coupe** les temps morts (attente réseau,
   génération d'une IA) — montrer le début, couper, reprendre sur le résultat.
5. **60 i/s constants** : convertir la source en CFR (`fps=60`) AVANT de découper — la capture du simulateur
   est à images variables, un `-ss` tombant dans un passage figé saute la pause.

## 4. Préparer la machine et les apps
- **Libérer la machine** : fin des compilations, apps lourdes fermées, swap raisonnable
  (`sysctl vm.swapusage`, `ps -Ao pcpu,comm | sort -rn | head`). **Un seul simulateur/émulateur à la fois** :
  tout iOS, puis tout Android. Faire confirmer par l'utilisateur.
- Installer le build voulu ; **demander à l'utilisateur de se connecter** et vérifier le compte affiché.
  Même compte / mêmes données sur les deux plateformes pour une vidéo côte à côte.
- **Essai à blanc** de chaque geste avec captures avant d'enregistrer (les données créées pendant les essais
  apparaissent ensuite à l'écran).

## 5. Piloter iOS — pilote XCUITest (aucune permission macOS requise)
Depuis Xcode 27, Simulator.app est remplacé par `Xcode.app/Contents/Applications/DeviceHub.app`, et
l'AppleScript (System Events) est souvent refusé : on pilote l'app par un test UI qui lit des commandes
dans un fichier.

```bash
cp -R "$SK/ios-driver" "$W/driver" && cd "$W/driver" && xcodegen generate -q && mkdir -p "$W/io"
TEST_RUNNER_PV_IO_DIR="$W/io" TEST_RUNNER_PV_BUNDLE_ID=<bundle.id.de.l.app> \
  xcodebuild -project Driver.xcodeproj -scheme DriverUITests \
  -destination "platform=iOS Simulator,id=$UDID" -derivedDataPath dd test > run.log 2>&1 &   # tourne jusqu'à `quit`
export PV_IO_DIR="$W/io" PV_UDID=$UDID
"$SK/ios" tree              # arbre d'accessibilité (libellés + cadres, en points)
"$SK/ios" label "Envoyer"   # taper un élément par libellé
"$SK/ios" tap 220 824       # coordonnées en points
"$SK/ios" type "Bonjour"    # exige un clavier affiché (sinon « nokeyboard »)
"$SK/ios" swipe 220 440 220 900 ; "$SK/ios" long 150 245 1.2
"$SK/ios" sb "Autoriser"    # bouton d'une alerte système (SpringBoard)
"$SK/ios" shot nom          # capture → $W/nom.png
xcrun simctl io $UDID recordVideo --codec=h264 --force rec.mp4   # filmer ; arrêt par SIGINT
```
Pièges : `xcrun simctl privacy grant` tue l'app (relancer : `ios activate`) ; la 1re lecture de l'arbre
peut prendre 30 s ; la reconnaissance vocale n'existe pas au simulateur ; sur un Mac chargé, le simulateur
rend les animations par à-coups (150-600 ms) — filmer un vrai iPhone si la fluidité est critique.
Sur Apple Silicon avec un shell sous Rosetta, préfixer les builds par `arch -arm64`.

## 6. Piloter Android — adb
`scripts/and.py` (env `PV_WORK_DIR` pour les captures) : `tap X Y` (pixels), `text "Libellé"`
(uiautomator), `has "Libellé"`, `type`, `swipe`, `long`, `key N`, `tree`, `shot`.
- Filmer avec `adb shell screenrecord --size <largeur>x<hauteur> --time-limit 175 /data/local/tmp/x.mp4`
  (segments de 3 min max) ; **jamais** `adb emu screenrecord` (fichier énorme, émulateur figé). Écrire dans
  `/data/local/tmp`, pas `/sdcard` (sinon les vidéos apparaissent dans la galerie filmée).
- Installer **ADBKeyBoard** (`ime enable` + `ime set com.android.adbkeyboard/.AdbIME`) et désactiver Gboard
  et la saisie vocale Google : sinon un clavier recouvre l'écran filmé. `adb input text` ne tape pas les
  accents (ADBKeyBoard : `am broadcast -a ADB_INPUT_TEXT --es msg "…"`).
- `uiautomator dump` bloque sur les écrans animés (streaming) → coordonnées ; un libellé peut aussi
  correspondre à un texte de liste → coordonnées.

## 7. Monter
**Vertical 1080x1920** (une plateforme) :
```bash
python3 "$SK/montage.py" --src rec.mp4 --out demo.mp4 --card "Sur-titre|Titre|Sous-titre|Pastille" \
  --seg "0:23.5|Étape 1 / 2|Titre de l'étape|Sous-titre" --seg "33.8:end|Étape 2 / 2|…|…"
```
Temps en secondes de la vidéo CFR (créée par le script) ; début ≈ 1,5 s avant le 1er geste, fin ≈ 1-2 s
après que l'écran s'est posé (repérer avec `ffmpeg -ss T -frames:v 1`).

**Paysage 1920x1080, iOS + Android côte à côte** : filmer chaque étape séparément par plateforme, puis
`python3 "$SK/montage_duo.py" plan.json demo.mp4` avec
```json
{"cover": {"eyebrow": "…", "title": "…", "sub": "…", "pill": "…", "voice": "…"},
 "footer": "", "unavailable": "Non disponible", "device_labels": {"ios": "iOS", "android": "Android"},
 "steps": [{"eyebrow": "Étape 1 / 4", "title": "…", "sub": "…", "voice": "…",
            "ios": "clips/ios_1.mp4", "android": "clips/and_1.mp4", "ios_note": "si pas de clip iOS"}]}
```
Les deux clips d'une étape démarrent ensemble, le plus court se fige sur sa dernière image ; sommaire à
gauche. Toujours contrôler une planche (`fps=1/2,tile=11x3`) avant de livrer.

## 8. Voix off avec Voicebox (optionnel)
Voicebox (app Mac) expose une API locale `http://127.0.0.1:17493` (`/openapi.json`) ; un bac à sable réseau
peut bloquer localhost.
- Champ `"voice"` (1-2 phrases, ~6-8 s) par étape et sur la couverture ; écrire pour l'oreille (épeler
  les sigles, pas de symboles).
- `python3 "$SK/voiceover.py" plan.json --profile <nom du profil> --language fr` → `vo/step_<n>.wav`,
  `voice_file`/`voice_duration` renseignés ; seuls les textes modifiés sont regénérés. ~30 s par phrase ;
  une génération bloquée est annulée et relancée automatiquement.
- `--language` suffit à changer de langue, quelle que soit la voix (une voix clonée parle d'autres langues).
- `montage_duo.py` cale la voix 0,8 s après le début de l'étape ; l'étape dure au moins voix + 1 s.
- Voix clonée d'une personne : ne l'utiliser qu'avec son accord ; sinon voix prédéfinie
  (`GET /profiles/presets/{engine}`).

## 9. Autre langue
Copier le plan, traduire `cover`, `eyebrow`/`title`/`sub`/`voice`, les notes, `footer`/`unavailable` ;
retirer `voice_file`/`voice_duration`/`voice_text_done` ; lier les mêmes `clips/` ; relancer `voiceover.py
--language xx` puis `montage_duo.py`. Les écrans filmés restent dans la langue de l'app au tournage : pour
une version entièrement traduite, changer la langue des apps et refilmer.

## Limites
- Couleurs : fiable sur pptx/CSS/tokens, approximatif sur une image → toujours faire valider l'aperçu.
- Mise en page fixe (couverture pleine couleur, pages claires titre + écran en carte) ; seuls couleurs,
  polices, logos et textes changent.
- macOS uniquement (`qlmanage`, Keynote, simulateur iOS).
