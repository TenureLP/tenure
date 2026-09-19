# Lease Vault

Vente et location de positions de liquidité Uniswap v4 sur Robinhood Chain. Un fournisseur de liquidité vend sa position à un financeur, la loue immédiatement contre un loyer fixe, garde les frais de swap pendant la durée du bail, et peut la racheter à un prix convenu d'avance. Rien n'est prêté, rien n'est liquidé.

C'est l'implémentation du « modèle C » discuté autour de Gage : la même expérience produit, cash maintenant contre un actif productif, avec une structure juridique de vente et location avec promesse de rachat, au lieu d'un prêt gagé à surcoût fixe. L'analyse de conformité détaillée est dans la section 6 de la spec.

**Statut : prototype.** Le code compile avec solc 0.8.28. Les 29 tests unitaires passent contre des contrats simulés, et les 5 tests d'intégration passent en fork contre le vrai PositionManager Uniswap v4 de Robinhood Chain. Il n'a pas été audité et la structure n'a pas été revue par un comité de conformité. Ne pas déployer en l'état.

## Le point bloquant à connaître avant tout

Les Stock Tokens de Robinhood Chain ne sont pas des actions tokenisées. D'après la documentation officielle, ce sont des titres de dette tokenisés émis par Robinhood Assets (Jersey) Limited, sans droit de vote, sans droit sur l'action sous-jacente, et interdits aux personnes américaines. Conséquences :

- **Côté SEC.** L'exemption d'innovation du 17 septembre 2026 ne couvre que les actions NMS tokenisées portant les mêmes droits qu'une action classique. Elle exclut explicitement les jetons synthétiques qui ne donnent qu'une exposition au prix. Les Stock Tokens actuels sont hors périmètre.
- **Côté conformité.** Un titre de dette dont la valeur suit un cours d'action est une créance, pas une propriété. En faire du LP revient à faire du marché sur une créance, ce que l'analyse de la spec écarte.

Les deux critères convergent. L'allowlist du protocole doit donc se limiter, pour la v1, aux paires crypto jugées licites (WETH/USDG par exemple) et, dès qu'elles apparaîtront sur la chaîne, aux actions tokenisées à droits complets qui satisfont la définition de la SEC. Le registre porte un champ `assetClass` et un `screeningRef` pour tracer cette décision paire par paire.

## Comment ça marche

1. **Listing.** Le fournisseur de liquidité met en vente sa position NFT avec un prix, un loyer total pour la durée, un prix de rachat et une durée (7 ou 21 jours par exemple). Le NFT entre dans le vault.
2. **Financement.** Un financeur paie le prix. Il devient propriétaire de la position. Le vendeur reçoit le prix moins le loyer prépayé et moins des frais fixes de protocole. Le loyer reste en escrow et s'écoule vers le financeur seconde par seconde.
3. **Bail.** Le locataire collecte les frais de swap de la position autant qu'il veut. Il ne peut jamais retirer de liquidité. Si le jeton sous-jacent est gelé par l'émetteur, le loyer cesse de courir.
4. **Échéance.** Le locataire rachète la position au prix convenu, à tout moment jusqu'à la fin de la période de grâce, et le loyer non couru lui est remboursé. Sinon, après la grâce, le financeur prend livraison de ce qui lui appartient déjà.

Tous les paiements sont des soldes à retirer, jamais des transferts forcés. Le vault n'a ni propriétaire ni mise à jour possible.

## Arborescence

```
src/LeaseVault.sol          contrat principal, sans propriétaire
src/AssetRegistry.sol       allowlist des pools, durées, grâce, frais fixes
src/interfaces/             surfaces minimales de PositionManager, StateView, ERC-20
src/libraries/Types.sol     types v4 recopiés, décodage PositionInfo, actions
test/LeaseVault.t.sol       suite de tests unitaires
test/fork/VaultFork.t.sol   tests d'intégration en fork de Robinhood Chain
test/mocks/                 USDG, jeton pausable, PositionManager et StateView simulés
script/Deploy.s.sol         déploiement sur Robinhood Chain
docs/SPEC.md                spécification, analyse de conformité, cadre réglementaire
```

## Lancer

Le projet n'a aucune dépendance externe : les quelques cheatcodes Foundry utilisés sont déclarés dans `test/utils/MiniTest.sol`. Avec Foundry installé (sous WSL par exemple) :

```bash
forge test --offline -vv
```

Tests d'intégration en fork contre le vrai déploiement Uniswap v4. Le script choisit tout seul une position vivante, dans le range et à range large, grâce à `../lp-api`. Rien n'est envoyé sur la chaîne.

```bash
./fork-test.sh
```

Déploiement :

```bash
REGISTRY_OWNER=0x... FEE_RECIPIENT=0x... forge script script/Deploy.s.sol --rpc-url robinhood --broadcast --verify
```

## Adresses utilisées sur Robinhood Chain (4663)

| Contrat | Adresse |
|---|---|
| USDG | 0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168 |
| Uniswap v4 PositionManager | 0x58daec3116aae6D93017bAAea7749052E8a04fA7 |
| Uniswap v4 StateView | 0xF3334192D15450CdD385c8B70e03f9A6bD9E673b |
| Uniswap v4 PoolManager | 0x8366a39CC670B4001A1121B8F6A443A643e40951 |

RPC : https://rpc.mainnet.chain.robinhood.com. Explorateur : https://robinhoodchain.blockscout.com. Les adresses viennent de la page d'adresses de Gage et doivent être revérifiées sur l'explorateur avant tout déploiement.

## Références

- [Statement SEC, Innovation Exemption, 17 septembre 2026](https://www.sec.gov/newsroom/speeches-statements/uyeda-statement-innovation-exemption-091726)
- [Communiqué SEC 2026-90](https://www.sec.gov/newsroom/press-releases/2026-90-sec-issues-innovation-exemption-facilitate-trading-tokenized-nms-stock-request-comment)
- [CFTC, no-action pour les fournisseurs de logiciels passifs, 17 septembre 2026](https://www.cftc.gov/PressRoom/PressReleases/9300-26)
- [Robinhood Chain, Stock Tokens](https://docs.robinhood.com/chain/stock-tokens/)
- [Uniswap v4, PositionManager](https://developers.uniswap.org/docs/protocols/v4/guides/position-manager)
- [Gage, adresses de protocole](https://docs.gage.cash/protocol/addresses)
