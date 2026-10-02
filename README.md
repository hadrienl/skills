# skills

Des skills pratiques pour [Claude Code](https://claude.com/claude-code).

| Skill | Rôle |
|---|---|
| [`video`](video/) | Tourner et monter une vidéo de démo d'app — mobile (iOS au simulateur, Android à l'émulateur) ou **web (Chrome piloté, curseur animé)** — à la charte de n'importe quelle marque : template extrait d'un pptx, Keynote, PDF, image, logo, CSS ou tokens JSON ; montage vertical, paysage côte à côte ou paysage web en 60 i/s ; voix off Voicebox avec **sélection des prises par timbre** et boucle d'écoute ; fond musical ; **lecteur web multilingue** (une vidéo, une voix et des sous-titres par langue) publiable dans une doc Mintlify. |

## Installation

```bash
git clone https://github.com/hadrienl/skills.git
cp -R skills/video ~/.claude/skills/            # pour tous vos projets
# ou : cp -R skills/video <projet>/.claude/skills/
```
Puis dans Claude Code : `/video`.

## Prérequis (`video`)
macOS, `ffmpeg`, Python 3 + Pillow ; selon la cible : Xcode (simulateur iOS, `xcodegen`), Android SDK (`adb`, émulateur), Node ≥ 22 + Google Chrome (web).
Optionnel : Keynote (sources `.key`), [Voicebox](https://voicebox.sh) (voix off).
