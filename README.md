# skills

Des skills pratiques pour [Claude Code](https://claude.com/claude-code).

| Skill | Rôle |
|---|---|
| [`video`](video/) | Tourner et monter une vidéo de démo d'app mobile (iOS au simulateur, Android à l'émulateur) à la charte de n'importe quelle marque : template extrait d'un pptx, Keynote, PDF, image, logo, CSS ou tokens JSON ; montage vertical ou paysage côte à côte en 60 i/s ; voix off générée par Voicebox ; versions multilingues. |

## Installation

```bash
git clone https://github.com/hadrienl/skills.git
cp -R skills/video ~/.claude/skills/            # pour tous vos projets
# ou : cp -R skills/video <projet>/.claude/skills/
```
Puis dans Claude Code : `/video`.

## Prérequis (`video`)
macOS, Xcode (simulateur iOS, `xcodegen`), Android SDK (`adb`, émulateur), `ffmpeg`, Python 3 + Pillow.
Optionnel : Keynote (sources `.key`), [Voicebox](https://voicebox.sh) (voix off).
