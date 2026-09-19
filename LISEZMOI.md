# Tenure, dossier du projet

« Tenure » est un nom de travail. Tout ce qui a été produit est ici, en quatre dossiers.

## Où trouver quoi

| Tu cherches | Va dans |
|---|---|
| Le logo, la bannière, le favicon | `brand/` |
| La landing et la waitlist | `landing/` |
| Les contrats Solidity et leurs tests | `lease-vault/` |
| L'API de valorisation des positions LP | `lp-api/` |

## brand/

| Fichier | Usage |
|---|---|
| `logo-avatar-1024.png`, `logo-avatar-400.png` | **Photo de profil** X, Discord, Telegram. Dessin resserré pour survivre au rognage en cercle |
| `logo-mark-1024.png`, `logo-mark-512.png` | Icône carrée, pour tout ce qui n'est pas rogné en cercle |
| `logo-mark.svg` | Symbole vectoriel, toutes tailles à partir de 48 px |
| `logo-mark-small.svg` | Favicon et tailles de 32 px et moins, traits plus épais |
| `logo-mark-mono.svg` | Une seule couleur, sans fond : tampon, filigrane |
| `logo-horizontal-dark.png` et `.svg` | Symbole plus nom, sur fond sombre |
| `logo-horizontal-light.png` et `.svg` | Symbole plus nom, sur fond clair |
| `logo-nav.svg` | Version compacte à fond transparent, pour un en-tête de site |
| `banner-1500x500.png` et `.svg` | Bannière X active, copie de la variante choisie |
| `banner-t1.png`, `banner-t2.png`, `banner-t3.png` | Même graphique, trois traitements du texte : t1 taille d'origine, **t2 texte agrandi (active)**, t3 avec une accroche au-dessus. Pour changer : `$env:BRAND_BANNER="t3"` avant `export.ps1` |
| `_banner-alts.html` | Compare les trois avec la photo de profil en surimpression |
| `build.py`, `export.ps1` | Régénèrent tout. `export.ps1 NouveauNom` change le nom partout |
| `video/tenure-intro.mp4` | Teaser « coming soon », 1920x1080, 16 s, sans son |
| `_x-preview.html` | Simule le profil X : vérifie que la photo de profil ne recouvre pas la bannière |
| `video/intro.html`, `video/render.ps1` | Source de l'animation et script de rendu. `render.ps1 -Tag "ton-domaine"` remplace la dernière ligne |

Couleurs : bleu nuit `#0E1726`, ambre `#F5B84B`, blanc cassé `#F4F1EA`. Police : Bahnschrift, convertie en tracés dans les SVG. Sur le web, Barlow en est l'équivalent libre.

## landing/

Ouvrir un terminal dans le dossier puis :

```
python dev_server.py
```

et aller sur http://127.0.0.1:8410. Le `README.md` du dossier explique le branchement de la waitlist et le déploiement.

## lease-vault/ et lp-api/

Chacun a son `README.md`. Les deux se lancent depuis WSL, où Foundry et Python sont déjà installés.

| Commande | Effet |
|---|---|
| `forge test --offline` dans `lease-vault` | 29 tests unitaires |
| `./fork-test.sh` dans `lease-vault` | 5 tests contre le vrai Uniswap v4 de Robinhood Chain |
| `./run.sh test` dans `lp-api` | tests de l'API |
| `./run.sh serve` dans `lp-api` | lance l'API sur le port 8402 |

## État

Prototype. Rien n'est déployé, rien n'est audité, et la structure n'a pas été revue par un comité de conformité. L'analyse est dans `lease-vault/docs/SPEC.md`.
