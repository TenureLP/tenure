# lpval

API de valorisation des positions de liquidité Uniswap v4 sur Robinhood Chain (4663), avec un paywall à la requête. Prototype en Python, bibliothèque standard uniquement, aucune installation.

## Ce que ça renvoie

Pour un `tokenId` du PositionManager v4 :

- le pool, les deux jetons, le hook, les frais ;
- le range, la liquidité, si la position est dans le range, si elle a un abonné ;
- les montants des deux jetons et les frais non collectés, en arithmétique entière exacte ;
- la valeur en USDG quand l'USDG est un des deux jetons ;
- un taux de frais mesuré sur une fenêtre, avec un indicateur de confiance ;
- sur `/quote`, des termes indicatifs de vente et location : prix, rachat, loyer.

## Lancer

Tout se fait depuis WSL, Python 3.10 ou plus.

```bash
./run.sh test
```

```bash
./run.sh find --scan 600 --min-usdg 1000
```

Avec `--wide`, ne garde que les positions dans le range et à range très large, celles qui restent éligibles assez longtemps pour un test.

```bash
./run.sh position 2908278 --quote
```

```bash
./run.sh serve --port 8402
```

Test de bout en bout contre la chaîne réelle, mode gratuit puis mode payant :

```bash
bash tests/smoke.sh
```

## Routes

| Route | Rôle |
|---|---|
| `GET /health` | état, toujours gratuit |
| `GET /v1/position/<tokenId>` | valorisation |
| `GET /v1/position/<tokenId>/quote?term=7&haircut=0.2&rentShare=0.5&lookbackHours=24` | valorisation et termes indicatifs |

## Paywall

Désactivé par défaut. Pour l'activer :

```bash
LPVAL_PAY_TO=0xTonAdresse LPVAL_PRICE_WEI=1000000000000 ./run.sh serve
```

Sans preuve de paiement, les routes payantes répondent 402 avec l'adresse, le montant et la chaîne, dans le corps et dans l'en-tête `PAYMENT-REQUIRED`. Le client envoie l'ETH, puis rappelle avec la preuve au format documenté par Olanas :

```
PAYMENT-SIGNATURE: base64({"scheme":"onchain-tx","txHash":"0x..","payer":"0x.."})
```

Le raccourci `X-Payment-Tx: <hash>` est aussi accepté. Le serveur vérifie le destinataire, le payeur, le montant, le succès, l'ancienneté (une heure au plus), refuse tout hash déjà utilisé, et renvoie un reçu dans `PAYMENT-RESPONSE`.

Différence voulue avec Olanas : chez eux une preuve reste réutilisable pour la même ressource, ce qui convient à un téléchargement. Ici un paiement achète une seule requête.

Test du chemin complet sans bouger de fonds, en rejouant un vrai transfert de la chaîne comme preuve :

```bash
python3 tests/paywall_live.py
```

## Taux de frais et instantanés

Le RPC public ne sert qu'une dizaine de minutes d'historique. Chaque valorisation enregistre donc un instantané de la croissance des frais du range dans SQLite. Le taux est calculé sur le plus vieil instantané de la fenêtre demandée. Sans instantané, il est estimé sur les huit dernières minutes et marqué `lowConfidence`. Pour garder une liste de positions à jour :

```bash
./run.sh snapshot 2908278 2908010 2908292
```

à placer dans un cron horaire.

## Variables d'environnement

| Variable | Défaut |
|---|---|
| `LPVAL_RPC` | `https://rpc.mainnet.chain.robinhood.com` |
| `LPVAL_PAY_TO` | vide, paywall coupé |
| `LPVAL_PRICE_WEI` | `1000000000000` |
| `LPVAL_DB` | `lpval_payments.sqlite` |
| `LPVAL_SNAP_DB` | `lpval_snapshots.sqlite` |

Sous WSL, placer les deux bases hors de `/mnt/c`, par exemple dans `/tmp` ou le home Linux, SQLite supportant mal ce système de fichiers.

## Limites connues

- Valeur en USDG seulement si l'USDG est dans la paire. Les paires contre WETH demandent un pool de référence.
- Le prix vient du pool lui-même. Pas encore de recoupement avec les flux Chainlink des Stock Tokens, donc pas de détection de prix manipulé.
- Le taux de frais suppose la liquidité actuelle constante sur la fenêtre, et devient faux si les ticks du range n'étaient pas initialisés au début.
- Le paiement est en ETH. Pas encore de x402 standard ni d'USDG.
- Serveur `http.server` : suffisant pour un prototype, à remplacer avant toute mise en production.
