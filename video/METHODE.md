---
name: prisme-video
description: Tourner et monter une vidéo de démo Prisme.ai — apps mobiles (iOS au simulateur, Android à l'émulateur) ET plateforme web (studio, Agent Creator, builder, AI Store…) dans un Chrome piloté — pilotage scripté, enregistrement 60 i/s, montage à la charte Prisme.ai (vertical 1080x1920, paysage iOS + Android côte à côte, ou paysage web avec fenêtre de navigateur et curseur animé), narration générée par Voicebox, versions FR/EN, ou lecteur web multilingue (une vidéo, une voix et des sous-titres par langue, textes en HTML) à publier dans la doc. À utiliser quand on demande « fais une vidéo de l'app », « filme la démo », « montre la fonctionnalité X en vidéo », « tuto vidéo du studio / du builder », « vidéo de doc », « ajoute une voix off », « version anglaise de la vidéo », « lecteur multilingue », « vidéo pour la doc », « /prisme-video ».
---

# prisme-video

Produit une courte vidéo de démo lisible : **peu d'actions, chacune précédée d'une pause
sur l'état de départ**, en temps réel, fluide. Méthode validée le 25/09/2026 sur iOS
(exemple : « discuter avec un agent, puis changer de modèle et relancer »).

## Principes de montage (retours utilisateur)

1. **Une vidéo = 2 à 3 actions**, pas un tour complet de l'app. Au-delà, faire plusieurs vidéos (exception : le
   tutoriel de doc multilingue, découpé en sections cliquables — § 5 ter).
2. **Pause courte (~1,5 s) sur l'état initial avant chaque action**, titre de l'étape déjà affiché :
   le spectateur doit voir l'écran de départ avant qu'il ne bouge. 3,5 s a été jugé « lent et mou » (26/09).
3. **Rythme serré** : enchaîner les gestes sans délai artificiel (≤ 0,5 s entre deux gestes) ; saisie
   fluide (caractère par caractère rapide ou mot à mot sans pause), pas 0,12 s par mot + 1 à 3 s par geste.
   (`scenarios/chat-then-model.sh` date d'avant ce retour : ses `sleep 3.5` sont à raccourcir.)
4. **Attente du modèle coupée, jamais accélérée** : montrer le début du streaming (~2 s), couper, reprendre
   sur la réponse complète. Idem canvas (~1 min de génération). En paysage synchronisé, une plateforme
   figée 10 s à attendre l'autre est ressenti comme mou : couper aussi ces attentes.
5. **Jamais d'accélération** pendant une action (×2 = image saccadée et incompréhensible).
   On COUPE les temps morts statiques (attente réseau figée) au lieu de les accélérer.
6. **Aucun silence de plus de ~2,5 s** (retour du 01/10 sur le tutoriel SharePoint : « les pauses de 3 s sont
   bien trop longues, ça casse le rythme ») : même si l'écran bouge (frappe, réponse qui s'écrit), un passage
   sans voix est coupé (`timeline.SILENT_MAX` = 2,5 s), en gardant ~0,6 s après la voix et ~0,9 s avant la
   suivante. Entre deux phrases d'étapes différentes s'ajoutent les marges du lecteur : 3,5 s au plus.
7. **Voix vive, régulière et validée à l'oreille** (même retour : « le rythme de la voix est trop mollasson »,
   « certains passages n'ont pas la bonne voix, d'autres sont soudain accélérés ») : `voiceover.py` choisit la
   prise au bon timbre et ramène toutes les phrases au même débit, ×1,12 (§ 6) ; puis **boucle d'écoute** (§ 6 ter).
8. **60 i/s constants** : convertir la source en CFR (`fps=60`) AVANT de découper.
   La capture du simulateur est à images variables (une image n'est écrite qu'au changement) :
   un `-ss` qui tombe dans un passage figé saute l'image figée → l'étape démarre sans pause.
9. Cadre 1080x1920 à la **charte Prisme.ai** (`template/`, voir plus bas) : couverture bleue de 2,8 s,
   puis une « page » blanche par étape (sur-titre bleu, titre Play Bold, écran dans une carte), fondu 0,5 s.
   (Lecteur multilingue : couverture ≥ 2 s, voix 0,4 s après le début d'étape, `package_player.py:49`.)

## Charte graphique (`template/`)
Les scripts de montage lisent le template désigné par `VIDEO_TEMPLATE` (défaut : `template/` de ce skill).
Le skill générique `/video` réutilise ces scripts avec une charte extraite d'un fichier quelconque.

Extraite le 25/09/2026 de la présentation « Weekly - template - EN - v2 » (Drive
`1jy1FvlcJe0HB-pV8qBgg3-qM8VBgnDZb`). `theme.json` porte les couleurs, polices et motifs.
- **Couverture** : fond `#1E50D2`, logo blanc en haut à gauche, grand symbole `#4D8BEE`, sur-titre en
  capitales `#9DB4EE`, titre Play Bold blanc, sous-titre `#C9D8F7`, pastille blanche texte `#205BE1`.
- **Page d'étape** : fond blanc, sur-titre capitales `#205BE1` (Arial Bold), titre Play Bold `#151B24`,
  sous-titre `#69707F`, logo couleur en haut à droite, filet `#E4E7ED` + pied de page gris.
- Fichiers : `logo-white.png` / `logo-color.png` (issus du pptx), `mark.svg` + `mark-*.png` (symbole
  redessiné d'après la géométrie du masque de couverture : 1 disque, 4 demi-disques, 4 quarts),
  `fonts/Play-*.ttf` (Google Fonts, licence OFL — le pptx n'embarque qu'un EOT inutilisable).
- Pour changer de charte : remplacer les fichiers de `template/` et `theme.json`, sans toucher au script.

## Déroulé

### 0. Préparer
- **Dossier de travail DURABLE** (clips, `plan.json`, `vo/`, `out/`) : `~/Movies/prisme-video/<nom>/`, pas le
  scratchpad — vidé entre deux jours (01/10 : rushes, voix et plan SharePoint perdus).
- **Disque** : `df -h /System/Volumes/Data` ≥ 5 Go libres avant voix et montage (02/10 : disque plein en pleine
  génération, `OSError 28`). Signaler les gros postes à l'utilisateur, ne supprimer que ses propres fichiers.
- **Libérer la machine avant de tourner** (diagnostic du 26/09 : swap 8,3 Go/9 Go sur 32 Go de RAM,
  compilations Swift et Vibe Manager en fond) : attendre la fin des builds, fermer les apps lourdes, vérifier
  `sysctl vm.swapusage` et `ps -Ao pcpu,comm | sort -rn | head`. **Un seul simulateur/émulateur allumé à la
  fois** : filmer toutes les étapes iOS, fermer DeviceHub, puis démarrer l'émulateur et filmer Android.
  Demander à l'utilisateur de confirmer que les ressources sont libérées avant le tournage.
- Build à jour : voir la mémoire `reference_mobile_build_and_run_commands` (iOS : `xcodebuild` sur
  le simulateur ; Android : `arch -arm64` + JBR d'Android Studio). Vérifier le worktree.
- **Demander à l'utilisateur de se connecter** dans l'app, et vérifier le compte (Réglages › Profil).
  Choisir un agent adapté à la démo (ex. sandbox `+admin` : « Structured Search » propose 20 modèles,
  « Secure Chat » un seul).
- Faire un **essai à blanc** de chaque geste (captures d'écran) avant d'enregistrer ; les conversations
  créées pendant les essais sont visibles dans l'historique filmé.

### 1. iOS — pilote XCUITest (aucune permission macOS requise)
Xcode 27 n'a plus Simulator.app (c'est `Xcode.app/Contents/Applications/DeviceHub.app`) et
System Events est refusé → on pilote l'app via un test UI qui lit des commandes dans un fichier.

```bash
SK="<ce dossier>/scripts"; W=<dossier de travail>; UDID=<simulateur démarré>
cp -R "$SK/ios-driver" "$W/driver" && cd "$W/driver" && /usr/local/bin/xcodegen generate -q
mkdir -p "$W/io"
# lancer en arrière-plan (reste actif tant qu'on n'envoie pas `quit`)
TEST_RUNNER_PV_IO_DIR="$W/io" TEST_RUNNER_PV_BUNDLE_ID=ai.prisme.chat.debug \
  arch -arm64 xcodebuild -project Driver.xcodeproj -scheme DriverUITests \
  -destination "platform=iOS Simulator,id=$UDID" -derivedDataPath dd test > run.log 2>&1 &
export PV_IO_DIR="$W/io" PV_UDID=$UDID
"$SK/ios" tree            # arbre d'accessibilité (libellés + cadres en points)
"$SK/ios" label "Envoyer" # taper un élément par libellé
"$SK/ios" tap 220 824     # coordonnées en POINTS (Pro Max = 440x956, 17 Pro = 402x874)
"$SK/ios" type "Bonjour " # exige un clavier affiché, sinon « nokeyboard »
"$SK/ios" swipe 220 440 220 900   # glisser long vers le bas = ferme le clavier du chat
"$SK/ios" sb "Autoriser"  # bouton d'une alerte système (SpringBoard)
"$SK/ios" shot nom        # capture → $W/nom.png
```
Pièges : `xcrun simctl privacy grant` TUE l'app (relancer via `ios activate`) ; la 1ʳᵉ lecture de
l'arbre peut prendre 30 s ; le vocal iOS ne marche pas au simulateur (SpeechAnalyzer absent).

### 2. Android — adb
`scripts/and.py` : `tap X Y` (pixels), `text "Libellé"` (via uiautomator), `type`, `swipe`, `shot`.
- `adb shell screenrecord --size 1080x2410 --time-limit 175` en segments ; **jamais** `adb emu screenrecord`
  (webm de 600 Mo, émulateur figé) ; sans `--size`, image déformée en 720x1280.
- `uiautomator dump` bloque sur les écrans animés (streaming, canvas) → coordonnées là.
- `adb input text` ne tape pas les accents ; un libellé peut matcher un titre de liste → coordonnées.
- Clavier : masquer par `keyevent 4` **seulement** si `dumpsys input_method` montre `mInputShown=true`.
- Photos lourdes (13 Mo) : l'app Android ne les réduit pas → envoi refusé ; pousser des images de 1-2 Mo.

### 2 bis. Web — Chrome piloté (`scripts/web.mjs`, validé le 28/09)
Pour les démos de la plateforme web. Node ≥ 22, **aucune dépendance** : parle au protocole DevTools d'un
Chrome dédié. Les appels vers `127.0.0.1` exigent `dangerouslyDisableSandbox`.

```bash
WEB="<ce dossier>/scripts/web.mjs"; export PV_WORK_DIR=<dossier de travail>
node "$WEB" launch https://studio.sandbox.prisme.ai --size 1440x900   # viewport exact, fenêtre ajustée
node "$WEB" tree [filtre]              # éléments cliquables visibles : « x,y  lxh  libellé » (iframes même origine incluses)
node "$WEB" click "Nouvel agent"       # libellé visible / aria-label / placeholder / title ; 2e occurrence : click "X" 1
node "$WEB" click --sel 'button[type=submit]' | click 640 320      # sélecteur CSS ou coordonnées (px CSS)
node "$WEB" hover "Capacités"          # survol seul (menus au :hover)
node "$WEB" type "Liste mes sites SharePoint"   # frappe humaine (~35 ms/caractère, accents OK) ; \n = Entrée
node "$WEB" paste --file bloc.yml      # colle d'un coup : pour le CODE (Monaco ré-indente ce qu'on tape)
node "$WEB" key Enter | key Meta+a Backspace
node "$WEB" scroll 600                 # molette animée sous le curseur (défile le bon conteneur)
node "$WEB" wait "Connecté" 60 | waitgone "Chargement"
node "$WEB" shot essai                 # capture de contrôle → $PV_WORK_DIR/essai.png
node "$WEB" record start clips/web_3.mp4 ; … ; node "$WEB" mark "clic installer" ; node "$WEB" record stop
node "$WEB" tabs | use popup | use main
```
- **Profil persistant** `~/.cache/video-skill/chrome` (`PV_CHROME_PROFILE`) : **demander à l'utilisateur de se
  connecter une fois** dans ce Chrome (studio, compte Microsoft de démo…) ; la session reste pour les prises
  suivantes. Jamais le profil Chrome réel. Port DevTools 9333 (`PV_CHROME_PORT`).
- **Curseur** : le pointeur système n'apparaît pas dans la capture → `web.mjs` dessine une flèche dans la page,
  la déplace en courbe douce (280-900 ms selon la distance) et affiche un halo bleu à chaque clic ; les vrais
  événements souris partent en parallèle (survols, menus). `cursor hide` pour une prise sans curseur.
- **Popups (OAuth Microsoft…)** : pendant l'enregistrement, une popup ouverte par la page est **filmée à la
  place** de l'onglet (centrée sur fond gris) et devient l'onglet piloté ; à sa fermeture on revient à l'onglet
  principal. Hors enregistrement : `use popup` / `use main`.
- **Capture** : screencast CDP (images seulement quand l'écran change), rééchantillonné en 60 i/s CFR au
  `record stop` ; la dernière image tient jusqu'à l'arrêt. `--max 1920` par défaut : ~47 i/s réels en
  mouvement, contre ~32 i/s en 2880 (mesuré le 28/09) — largement assez pour la carte de ~1400 px du montage.
  Des à-coups ponctuels (≤ 120 ms) restent possibles : faire 2 prises des gestes clés. `record stop` affiche la
  cadence mesurée (fichier `.log`), `mark` écrit des repères horodatés dans `<clip>.marks.txt`.
- **Un clip par étape** (comme le format duo) : `record start` → pause ~1,5 s → gestes → réponse posée →
  `record stop`. Les attentes longues (réponse du modèle, installation d'app) se retirent au montage (`cuts`).
- Pièges : la fenêtre Chrome ne doit pas être **minimisée** (plus d'images) — masquée derrière d'autres
  fenêtres, c'est OK (flags anti-occlusion). Les iframes d'une **autre origine** ne sont pas fouillées par
  `tree`/`click "…"` → coordonnées. Un libellé peut matcher plusieurs éléments : vérifier avec `tree X`.
  Pour du texte long dans un champ, préférer `type` (visible) ; pour du YAML/JSON, `paste`.

### 3. Écrire et jouer le scénario
Partir de `scenarios/chat-then-model.sh` : il lance `simctl io recordVideo`, enchaîne
**pause 3,5 s → action → attente de la réponse → pause**, écrit des repères (`marks.txt`) et tape
les messages **mot à mot** (plus lisible qu'un bloc).

### 4. Monter
```bash
python3 "$SK/montage.py" --src "$W/short.mp4" --out ~/Downloads/demo.mp4 \
  --card "Prisme.ai Mobile · iOS|Discuter et changer de modèle|Un agent, vingt modèles, en deux gestes.|iPhone · 1 minute" \
  --seg "0:23.5|Étape 1 / 2|Discuter avec l'agent|Structured Search · Claude 4.6 Sonnet" \
  --seg "33.8:end|Étape 2 / 2|Changer de modèle|Mistral large, puis nouvelle question"
```
`--card` = `sur-titre|titre|sous-titre|pastille`. Chaque `--seg` = `début:fin|sur-titre|titre|sous-titre`, en secondes de la vidéo **CFR** (le script la crée
d'abord). Choisir début/fin en regardant des images extraites (`ffmpeg -ss T -frames:v 1`) :
début = ~3 s avant le premier geste, fin = ~3 s après que l'écran s'est posé.
Contrôler avec une planche (`fps=1/2,tile=11x3`) avant de livrer. Déposer dans `~/Downloads`.

### 5. Format paysage iOS + Android côte à côte (validé le 25/09)
`scenarios/duo/` : `lib.sh` = une fonction par étape et par plateforme (`ios_3`, `and_3`…), `run.sh 1 2 …`
filme chaque étape **séparément** (iOS puis Android), `plan.json` décrit l'ordre et les textes.
`scripts/montage_duo.py plan.json out.mp4` : 1920x1080 60 i/s, couverture bleue, puis par étape le texte +
sommaire à gauche et les deux téléphones à droite ; les deux clips démarrent ensemble, le plus court se fige
sur sa dernière image. Étape sans clip d'une plateforme → carte grise avec `ios_note`/`android_note`.
- Même compte, même environnement et même agent sur les deux apps (vérifier Réglages › Profil : une app
  connectée en prod avec un compte restreint ne voit qu'1 agent au catalogue).
- Android : installer **ADBKeyBoard** (`ime enable/set com.android.adbkeyboard/.AdbIME`) et désactiver Gboard
  + la saisie vocale Google — sinon le clavier ou « Dites quelque chose » recouvre l'écran filmé.
- Retirer de la galerie Android les `.mp4` de `screenrecord` écrits dans `/sdcard` (ils apparaissent dans le
  sélecteur de photos) → enregistrer dans `/data/local/tmp`.
- Dans une fonction zsh qui boucle, déclarer `local k` : sinon elle écrase la variable de boucle de `run.sh`.

### 5 bis. Format paysage web (validé le 28/09)
`scripts/montage_web.py plan.json out.mp4` : 1920x1080 60 i/s, couverture bleue, puis par étape une colonne de
texte à gauche (sur-titre, titre, sous-titre, **sommaire**) et à droite l'écran filmé dans une **fenêtre de
navigateur dessinée** (3 pastilles + barre d'adresse). Même `plan.json` que le duo, avec `"web": "clips/web_1.mp4"` et :
- `"section"` : le sommaire liste les **sections** (ex. « Usage par chat », « Agent Creator », « Builder »,
  « Administrateur ») au lieu des étapes — indispensable au-delà de 8 étapes ;
- `"url"` : texte de la barre d'adresse (sans `https://`) ;
- `"trim": [début, fin]` et `"cuts": [[a, b], …]` en secondes du clip : on **coupe** les attentes, jamais d'accélération.
- `"cuts": "auto"` : les passages figés (> 1,2 s, `freezedetect`) sont retirés en gardant ~0,5 s avant chaque geste,
  et tout passage SANS VOIX de plus de 2,5 s est raccourci même s'il bouge (`timeline.silent_cuts`) — pratique
  quand le scénario a été joué par à-coups (réflexion entre deux commandes).
- `"comments": [{"t": 12.4, "text": "Je clique sur Se connecter."}, …]` : **narration au fil de l'action**, `t` en
  secondes du clip SOURCE (les repères `web.mjs mark` servent à les caler). Chaque commentaire est posé à son temps
  monté, jamais superposé au précédent ; les coupes `auto` n'enlèvent aucune image pendant qu'il parle ; l'étape
  s'allonge sur sa dernière image si la voix dépasse. Première phrase de l'étape = commentaire à `t` = début du trim.
  Écrire à la 1re personne, au présent, une action par phrase (« J'ouvre… », « Je coche… »), 3 à 8 s chacune.
Voix off : `voiceover.py plan.json` génère `voice` (couverture, intro d'étape) ET chaque commentaire
(`vo/step_<n>_<k>.wav`), sans regénérer les textes inchangés.

### 5 ter. Lecteur web multilingue — une vidéo, N langues (recommandé pour la doc, validé le 29/09)
Au lieu d'une vidéo par langue aux textes incrustés, on publie **un dossier statique** : une vidéo (les
captures seules), une voix par langue, et **tous les textes en HTML** (panneau, sommaire, barre d'adresse,
couverture, sous-titres) — traduisibles, cliquables, indexables. Filmer l'interface en **anglais** si possible.

**Déroulé type d'une nouvelle vidéo de doc** (modèle : tutoriel SharePoint, docs.prisme.ai, validé le 02/10) :
0. § 0 : dossier durable `~/Movies/prisme-video/<nom>/`, disque ≥ 5 Go, scénario validé avec l'utilisateur.
1. **Tournage** (§ 2 bis) : `web.mjs launch <url> --size 1440x900 --lang en-US` (interface ET dates en anglais),
   un clip par grande partie, `mark c<étape>_<k>` au début de chaque geste commenté, `mark s<étape>` aux
   frontières d'étape ; `clips/web_<n>.marks.txt` donne ensuite `trim` et `comments[].t`.
2. **Plan** : copier `scenarios/web-multilang/plan.json` (exemple complet, 2 étapes, testé le 02/10) ;
   commentaires ≥ 2,5 s, une énumération = une phrase.
3. **Voix** : `nohup python3 scripts/voiceover.py plan.json --profile Me > vo.log 2>&1 &` — les références de
   timbre `voices/Me.en.json` et `Me.fr.json` existent déjà (pas de `--make-ref` pour Me en/fr).
4. **Boucle d'écoute** (§ 6 ter) jusqu'à ce que l'utilisateur valide chaque langue.
5. **Montage** : `package_player.py plan.json out/ --base-url /tutorials/<nom>/ --music default`.
6. **Contrôles** (point 4 ci-dessous) puis écoute du montage complet par l'utilisateur, dans Safari ou Chrome.
7. **Publication** (point 5) sur une branche du dépôt docs, PR, merge à la demande de l'utilisateur.

1. **Plan multilingue** : `"langs": ["en", "fr"]`, `"default_lang"`, chaque texte en `{"en": …, "fr": …}`
   (`cover.*`, `section`, `title`, `sub`, `comments[].text`, `ui.<langue>.footer`) ; `comments[].voice`
   (facultatif) = texte DIT s'il diffère du sous-titre (prononciation). Mêmes `web`, `trim`,
   `"cuts": "auto"`, `url`, `comments[].t` qu'en 5 bis. Sans `section`, chaque étape est une entrée du sommaire.
2. `voiceover.py plan.json --profile Me` : génère TOUTES les langues de `langs` (`vo/<langue>/…`, champ
   `voices` de chaque élément) ; `--language fr` pour une seule ; une traduction absente est sautée.
   ~1 min 30 par phrase (2 à 4 prises) : ~1 h 15 par langue pour 50 phrases → lancer en **`nohup … &`** (une
   tâche d'arrière-plan de l'outil Bash est tuée à sa limite de durée ; une reprise ne refait que le manquant).
2 bis. **Boucle d'écoute — OBLIGATOIRE avant de monter** (§ 6 ter) : faire écouter `vo/<langue>/ecoute.html`
   prise par prise, corriger, et seulement ensuite `package_player.py`.
3. `package_player.py plan.json out/ --base-url /tutorials/<nom>/` →
   `media/video.mp4` (captures, < 20 Mo, réencodée plus fort si besoin), `media/voice_<l>[_<vitesse>].mp3`,
   `tracks/*.json`, `manifest.json`, `brand/`, `captions/<l>.vtt|.srt`, le lecteur (`index.html`,
   `player.css`, `player.js`) et **`snippet.mdx`** (manifeste + pistes en base64, pour Mintlify).
   `--manifest-only` : regénère textes, manifeste et snippet sans refaire les médias (refuse si la timeline a changé).
   **Fond musical** (02/10) : `--music default` mixe `template/music/fokkered-fokus.m4a` (choisie par
   l'utilisateur pour les vidéos de doc ; `--music <fichier>` pour une autre, `none` par défaut) DANS chaque piste
   de voix — le lecteur n'a rien à changer, et les vitesses étirent musique et voix ensemble. Rognée avant son
   silence final, bouclée par fondu enchaîné de 4 s, fondus d'entrée 1,5 s / sortie 3 s, `--music-gain -9` dB
   (choisi à l'écoute le 02/10 : −18 « pas assez forte », −12 et −9 comparés → −9 ; ≈ −25 LUFS, la voix à −20) et **ducking** : la voix pilote un `sidechaincompress` (ratio 8)
   qui la baisse d'~8 dB pendant qu'on parle. Pistes alors en stéréo 128 kb/s (au lieu de mono 96).
   Pour un autre morceau, faire écouter un extrait de 40 s avant le montage complet (niveau = affaire de goût) :
   `ffmpeg -t 40 -i out/media/voice_en.mp3 -t 40 -i <musique> -filter_complex "[0:a]aresample=48000,aformat=
   channel_layouts=stereo,asplit=2[v1][v2];[1:a]aresample=48000,aformat=channel_layouts=stereo,volume=-9dB[m];
   [m][v2]sidechaincompress=threshold=0.015:ratio=8:attack=30:release=600:makeup=1[d];[v1][d]amix=inputs=2:
   normalize=0:duration=first" extrait.mp3`, page `<audio>` (audible dans la vue web), plusieurs gains côte à côte.
   Prompt de génération (Suno/Udio…) qui a donné cette piste : instrumental, électro-pop douce, 95 BPM, énergie
   constante sans montée ni drop, médiums dégagés pour la voix, boucle de 3-4 min ; exclure voix, lead, drops.
   **Timeline commune** : chaque phrase occupe la durée de sa langue la plus longue ; coupes auto sans jamais
   couper une voix (`scripts/timeline.py`, partagé avec `montage_web.py`). Chaque segment est rendu en deux
   passes (plages, puis tenue de la dernière image) et sa durée contrôlée : dans une même chaîne `concat →
   tpad`, `tpad` ne prolonge rien (segments 1,2 s trop courts, la voix dérivait de 18 s — vu le 29/09) et
   `tpad stop=-1` ne se termine jamais.
4. **Tester** : `python3 -m http.server` dans `out/` → `tab_open` sur `index.html?lang=en`. 🔴 **La vue web de
   Vibe Manager ne sort pas le son Web Audio** (02/10 : « je n'ai pas les voix dans la preview ») : elle sert à
   vérifier image, sommaire et positionnement ; pour ÉCOUTER le lecteur, donner l'adresse à ouvrir dans Safari ou
   Chrome. (Les pages d'écoute en `<audio>` simple, elles, s'entendent dans la vue web.) Contrôle sans oreille :
   envelopper `AudioContext` et `AudioBufferSourceNode.prototype.start`, recréer l'hôte (`.pv-host` cloné sans
   `data-pv-state`), cliquer : contexte `running` + un `start` = la voix part.
   Contrôle du rythme : silences entre sous-titres (`tracks/subs_<l>.json`, médiane visée ~1,5 s, aucun > 3,5 s)
   et une image prise 0,3 s après chaque phrase (planche) : chaque phrase doit tomber sur l'écran qu'elle décrit.
   **Remonter une vidéo publiée sans les rushes** (le scratchpad est vidé entre deux jours) : le manifeste intégré
   au `snippet.mdx` contient chapitres et sous-titres (`tracks`) ; un plan dont chaque étape a pour `web` la
   `media/video.mp4` publiée, `trim` = bornes du chapitre et `comments[].t` = débuts des sous-titres permet de
   regénérer voix et rythme (fait le 01/10 pour SharePoint). **Garder les rushes hors du scratchpad.**
5. **Publier** :
   - Hébergement statique quelconque : copier `out/`, intégrer par
     `<iframe src=".../index.html" allow="fullscreen; autoplay">` (mode plein cadre détecté en iframe).
   - **Mintlify (docs.prisme.ai)** — contraintes vérifiées le 29/09 : pas de `.html` servi (donc pas d'iframe),
     ni `.m4a`, ni `.vtt`, ni `.json`/`.yml` en pratique (404 en `mint dev`, redirection en prod) ; fichiers < 20 Mo ;
     tout `.js`/`.css` du dépôt est chargé **sur toutes les pages**. Donc : `player.js` + `player.css` une seule
     fois dans `tutorials/`, les médias dans `tutorials/<nom>/{media,brand}`, `snippet.mdx` dans
     `snippets/tutorials/<nom>.mdx`, et dans la page `import X from "/snippets/tutorials/<nom>.mdx"` puis `<X />`.
     🔴 **Recopier `out/player.js` et `out/player.css` dans `tutorials/` à CHAQUE publication** : ils sont partagés
     par toutes les vidéos, et les correctifs du lecteur (Range/Blob, AudioContext) n'arrivent en prod que
     comme ça. Le même snippet peut être importé par plusieurs pages (SharePoint : vue d'ensemble des
     connecteurs + page du connecteur) — un seul fichier à mettre à jour. Nouvelle page : l'ajouter à la
     navigation (`docs.json`). Dépôt `prismeai/docs`, branche dédiée, PR via `gh` (push sur main bloqué).
     Vérifier avec `mint dev` (`~/.nvm/.../npx --yes mint@latest dev --port 3333`). Une PR du dépôt docs n'a
     **pas de prévisualisation Mintlify** (statut « Mintlify Deployment SKIPPED ») : l'écoute se fait en local.

Le lecteur (`player/`, Video.js 8.24.1 figé + SRI depuis jsDelivr, chargé à la demande) :
- **Composition = le lecteur** : panneau, fenêtre de navigateur dessinée, capture, sous-titres et contrôles
  sont dans l'élément Video.js ; le **plein écran** agrandit l'ensemble (scène 16:9 centrée, unité `--u`).
- **Voix par Web Audio**, horloge = la vidéo (sans son). Relancée à la position exacte sur lecture / seek /
  langue / vitesse, **jamais recalée pendant la lecture** (recaler un `<audio>` hachait le son : 33 sauts en
  6 s mesurés). Écart mesuré ±1-2 ms. Déverrouillée au premier geste ; iOS en mode silencieux : session
  `playback`. Seuls les tampons de la langue courante sont gardés (mémoire).
- **Pistes audio HLS multiples : écartées** — WebKit lit le HLS en natif et ignore le changement de piste.
- **Vitesses sans changement de hauteur** : versions pré-étirées (`atempo`) chargées à la demande ; en
  attendant, la voix de base accélérée plutôt qu'un silence.
- Langue : `?lang=`, choix mémorisé, langue du navigateur, `default_lang`. Menu **CC** (comme la voix, désactivés,
  ou une langue précise). Sommaire cliquable. Bouton lecture centré (blanc sur la couverture), remontré à chaque pause.
- **Hébergeur sans requêtes `Range`** (docs.prisme.ai : Vercel/mintcdn répondent toujours `200` complet,
  vu le 01/10 — `mint dev`, lui, répond `206`, donc le bug ne se voit qu'en prod) : sans `206`, le navigateur ne
  peut pas se positionner, la barre et le sommaire « repartent au début ». Le lecteur sonde une fois (en
  `cache: "no-store"` : le cache HTTP de Chrome sait répondre `206` tout seul et masque le défaut) et, sinon,
  télécharge la vidéo entière au premier geste puis la lit depuis un Blob ; la position demandée entre-temps
  (barre, sommaire) est rejouée, ainsi que la vitesse et l'état « démarré » (sinon la couverture revient).
  Tester avec `python3 -m http.server`, qui ne gère pas `Range` non plus.
- **Audio WebKit** : l'`AudioContext` est créé au premier geste et relancé dès qu'il n'est pas `running` — créé
  au chargement, WebKit le laisse `interrupted` (page en arrière-plan) et la narration restait muette (30/09).
- **Script global sûr** : ne fait rien sans `.pv-host`, suit la navigation sans rechargement (MutationObserver),
  ne démarre jamais deux fois, libère le lecteur quand l'hôte disparaît ; CSS entièrement préfixé `.pv.video-js`
  (la feuille de Video.js, chargée après, gagnerait à spécificité égale) ; médias et manifeste de même origine seulement.

### 6. Narration par Voicebox (validé le 26/09)
Voicebox (app Mac) expose une API locale `http://127.0.0.1:17493` (OpenAPI sur `/openapi.json`). Les appels
localhost exigent de sortir du bac à sable du shell (`dangerouslyDisableSandbox`).
- Écrire un champ `"voice"` (1 à 2 phrases, ~6-8 s) par étape et sur la couverture dans `plan.json`.
  Écrire pour l'oreille : « Prisme point A I », pas de sigles ni de symboles.
- `scripts/voiceover.py plan.json --profile Me [--engine kokoro] [--instruct "ton enthousiaste"]` : génère
  `vo/step_<n>.wav`, renseigne `voice_file`/`voice_duration`, ne regénère que les textes modifiés (`--force` sinon).
  ~30 s par prise (Qwen 1.7B, MLX), soit ~1 min 30 par phrase avec la sélection (2 à 4 prises). Une génération reste parfois bloquée (« loading_model »/« generating »
  sans activité) : le script annule puis relance tout seul au bout de 90 s.
- **Sélection des prises (01/10-02/10)** : le clonage Qwen part environ **une fois sur deux sur un autre timbre**
  (« une gen sur deux ne ressemble pas du tout à ma voix »). `voiceover.py` génère donc au moins 2 prises par
  phrase (au plus 4) et garde celle dont le **timbre** (spectre moyen à long terme, 24 bandes) est le plus proche
  de la référence `voices/<profil>.<langue>.json`. Seuil validé à l'oreille sur 23 prises : ≤ 4 dB = la bonne voix.
  - **Référence = prises validées à l'oreille DANS LA LANGUE** (`voiceover.py plan.json --make-ref a.raw.wav,b.raw.wav
    --language en`) : comparer à l'échantillon cloné (français) sépare mal les prises anglaises. Sans référence,
    l'échantillon sert de provisoire et `vo/<langue>/ecoute.html` liste les prises à faire écouter.
  - **Phrases < 2 s : non mesurables** (3 sur 4 « douteuses » étaient vraiment mauvaises, la 4e bonne) → les faire
    écouter, ou mieux, écrire des commentaires d'au moins 3 s.
  - **Débit commun** en passe finale : toutes les prises (`*.raw.wav`) sont rognées et ramenées au même débit,
    `--tempo` (1,12) × débit de référence (ou médiane réelle de la langue), **plafonné à ×1,25** (au-delà, l'oreille
    entend une voix « soudain accélérée »). Validé à l'écoute le 02/10.
- `montage_duo.py` lit ces champs : la voix démarre 0,8 s après le début de l'étape ; l'étape dure au moins
  voix + 1 s ; fondus audio (`acrossfade`) alignés sur les fondus vidéo.
- **Langue de la voix** : `--language en` (ou autre) suffit, quelle que soit la voix clonée — une voix
  clonée en français parle anglais sans accent (vérifié le 26/09 ; même paramètres que l'interface Voicebox).
- Références de timbre prêtes : `voices/Me.en.json` (9 prises), `voices/Me.fr.json` (31 prises).
- Options de `voiceover.py` : `--takes 2 --max-takes 4` (prises par phrase), `--seed`, `--tempo 1.12`, `--no-qc`
  (une prise, sans sélection), `--force` (tout regénérer). Voicebox renvoie parfois la MÊME prise pour deux
  seeds différentes : le script la rejette et tire une seed aléatoire.
- Profils existants : Me (voix clonée de l'utilisateur), Nath, BaBar d'écucume, Criquette 2. Pour une vidéo
  diffusée hors de l'équipe, préférer une voix prédéfinie neutre (`GET /profiles/presets/{engine}`).

### 6 ter. Boucle d'écoute des prises (OBLIGATOIRE, validée le 02/10)
La sélection automatique ne suffit pas : **c'est l'utilisateur qui valide**. Elle écarte les ratés grossiers,
mais à la 2e écoute (02/10) 5 phrases « pas ma voix » sur 50 avaient été retenues, dont deux à 2,5 et 2,7 dB
(bien sous le seuil). Faire aussi écouter le **montage final** (dans Safari/Chrome) : l'utilisateur signale par
minutage (« 2:29 mauvaise voix ») ; retrouver la clé via `out/tracks/subs_<l>.json` (n-ième sous-titre =
n-ième élément de `items_of` : couverture puis commentaires dans l'ordre).
1. Après chaque génération, ouvrir (`tab_open`) `vo/<langue>/ecoute.html` : toutes les prises, **pires en haut**
   (écart de timbre), en rouge au-delà du seuil. Demander la **liste des prises qui ne sont pas sa voix** (et
   « partielles » : début dans une autre voix, trop aigu/grave, tronqué, mot mal prononcé) — une seule question,
   l'utilisateur répond par clés (`3_3 4_2`).
2. **Mauvaise prise** → `voiceover.py plan.json --language fr --redo 3_3,4_2` (regénère avec sélection).
3. **Prise que la sélection ne réussit pas** (phrase courte, fragment d'énumération) → `--candidates 8_4 --n 6`
   puis ouvrir `vo/<langue>/candidats.html`, faire choisir un numéro, `--pick 8_4=3`. Retouches au choix :
   `@1.04` (un peu grave → hauteur ×1,04, durée inchangée) — **à éviter au milieu d'une énumération** : la
   phrase suivante ne suit plus le ton, « la transition est très mauvaise ». Si aucun candidat ne convainc,
   **reformuler** (texte ET sous-titre) : ≥ 2,5 s, et une énumération (« OAuth…, client credentials…, ou un
   access token. ») se dit en **une seule phrase**, jamais en fragments de 1-2 s posés sur chaque option
   (chaque fragment = une prise = un ton différent). Une fin **tronquée** à la génération (« La capacité est
   ajout… ») : rallonger la phrase (« La capacité est maintenant ajoutée à l'agent. »).
   Après fusion ou suppression d'un commentaire, les clés suivantes se décalent : renommer les `step_<k>.*`
   de l'étape (le n-ième fichier suit le n-ième commentaire) avant de relancer.
4. **Prononciation** : un champ `"voice": {"fr": …}` sur le commentaire remplace le texte DIT sans changer le
   sous-titre (`"text"`) — ex. « le tchat » dit, « le chat » écrit (sinon Qwen dit « chat » 🐱). Une langue
   absente de `voice` dit son sous-titre. (Avant le 02/10, le texte dit fuyait dans le sous-titre — corrigé.)
5. **Nouvelle voix ou nouvelle langue** (pas de `voices/<profil>.<langue>.json`) → après validation,
   `voiceover.py plan.json --make-ref vo/<l>/step_1_1.raw.wav,… --language <l>` avec les bonnes prises de ≥ 2,5 s
   (noms `step_<clé>.raw.wav` d'origine : le débit de référence en dépend ; `--language` obligatoire).
6. Chaque commande se termine par la passe de débit commun sur toute la langue (sans regénérer) ; puis monter.
Ne pas toucher au profil Voicebox (échantillon, `reference_text`) sans accord explicite : refusé le 02/10, bien
que la transcription de l'échantillon « Me » soit fausse.

### 7. Version dans une autre langue
- Copier le plan (`scenarios/duo/plan_en.json` = exemple anglais) : traduire `cover`, `eyebrow`/`title`/`sub`/`voice`
  de chaque étape, `ios_note`/`android_note`, et les champs globaux `footer` (pied de page) et `unavailable`
  (carte « non disponible »). Retirer `voice_file`/`voice_duration`/`voice_text_done`, sinon la voix n'est pas regénérée.
- Nouveau dossier par langue (`plan.json` + lien `clips` vers les clips existants) → `voiceover.py --language en`
  puis `montage_duo.py`. Réutiliser les clips = seules les incrustations et la voix changent.
- **Limite** : les écrans filmés restent dans la langue de l'app au tournage. Pour une version entièrement
  traduite, passer les apps dans la langue cible (Réglages › Langue) et traduire les messages `P1…P5` de
  `lib.sh`, puis refilmer.

## Pistes ouvertes (à itérer)
- **Saccades — diagnostic du 25/09** (mesuré sur les horodatages d'images, `ffprobe -show_entries frame=pts_time`) :
  chaque animation (sidebar, sélecteur de modèle) cale 2 fois 150-400 ms. **Ce n'est pas la capture** : même
  résultat en h264/hevc, sans émulateur Android, DeviceHub au premier plan, et avec l'attente de repos XCUITest
  neutralisée (`disableQuiescenceWait`, dans le pilote). L'ouverture de **Réglages d'iOS** — sans notre app
  ni XCUITest — cale aussi (jusqu'à 600 ms) : c'est le **simulateur** qui rend irrégulièrement sur ce Mac.
  → Solution retenue à tester : **filmer un vrai iPhone** (même pilote XCUITest, destination `platform=iOS,id=…` ;
  capture par QuickTime ou `ffmpeg -f avfoundation` sur l'iPhone branché). En attendant : tourner 3-4 prises et
  garder celle dont le « gel max » est le plus faible.
- `ffmpeg -f avfoundation` (capture d'écran Mac) reste bloqué tant que le terminal n'a pas la permission
  Enregistrement d'écran.
- Indicateur visuel de tap (cercle) : journaliser l'instant et la position de chaque geste dans le scénario.
- Vocal : tourner côté Android (le mode vocal fonctionne à l'émulateur).
- Web : pour de vraies 60 i/s sans à-coups, capturer l'écran du Mac (`ffmpeg -f avfoundation`, recadré sur la
  fenêtre) une fois la permission Enregistrement d'écran accordée au terminal ; le curseur dessiné par
  `web.mjs` resterait valable (masquer alors le pointeur système).
