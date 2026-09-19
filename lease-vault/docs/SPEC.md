# Lease Vault, spécification v0.1

Date : 17 septembre 2026. Réseau cible : Robinhood Chain (4663), Uniswap v4.

## 1. Objectif

Donner de la liquidité immédiate à un fournisseur de liquidité Uniswap v4 sans prêt, sans intérêt, sans liquidation, en respectant les conditions de l'ijara muntahia bittamleek telles que formalisées par AAOIFI (standard 9) et la déclaration AAOIFI de 2008 sur les sukuk. Reproduire l'expérience utilisateur de Gage (cash tout de suite, choix à l'échéance, pas d'oracle) avec une nature juridique différente.

Hors périmètre v1 : positions Uniswap v3, rachat à valeur de marché, vault d'agrégation côté financeurs, actions tokenisées synthétiques.

## 2. Acteurs

| Acteur | Rôle | Ce qu'il détient |
|---|---|---|
| Vendeur puis locataire | Fournisseur de liquidité qui veut du cash | Le droit d'usage de la position (frais de swap) et une promesse de rachat |
| Financeur | Apporteur de cash | La propriété de la position NFT, cessible, et un loyer fixe |
| Registre | Politique d'admission, géré par un propriétaire | Allowlist des pools, durées, grâce, frais fixes plafonnés |
| Vault | Exécution, sans propriétaire | Escrow des NFT et des USDG, soldes à retirer |

## 3. Cycle de vie

```
None --list()--> Listed --fund()--> Active --buyBack()--> BoughtBack
                   |                   |
                   +--cancel()-->      +--release()  (après terme + grâce) --> Released
                   Cancelled
```

Pendant `Active` :

- `collectFees` : locataire uniquement, jusqu'à la fin du terme. Actions v4 émises : `DECREASE_LIQUIDITY` avec liquidité zéro puis `TAKE_PAIR` vers le locataire. Aucune autre action n'est jamais encodée par le vault.
- `claimRent` : n'importe qui, crédite le financeur du loyer couru.
- `buyBack` : locataire, du financement jusqu'à ce que le financeur ait pris livraison. Le locataire paie le prix de rachat, récupère le NFT, et le loyer non couru lui est remboursé.
- `release` : financeur, à partir de terme + grâce. Il prend livraison du NFT. Le loyer non couru pour cause de gel est remboursé au locataire.
- `transferFinancierPosition` : le financeur cède sa propriété. Le bail continue. Le loyer couru est d'abord réglé au cédant. Jamais vers le locataire.
- `checkpointFreeze` : n'importe qui, enregistre un gel ou une levée de gel du sous-jacent.

Fin de partie : `withdrawUSDG` et `withdrawPosition` sont les seules sorties d'actifs, toujours à l'initiative du bénéficiaire.

## 4. Économie d'un deal

Exemple, USDG à 6 décimales.

| Paramètre | Valeur |
|---|---|
| Valeur de marché de la position | 2 280 USDG |
| Prix de vente | 1 815 USDG |
| Loyer total, 7 jours | 9 USDG |
| Prix de rachat | 1 815 USDG |
| Frais fixes de protocole | 2 USDG |
| Reçu par le vendeur au financement | 1 804 USDG |

Le financeur touche 9 USDG de loyer si le bail va au bout, soit environ 0,5 % sur 7 jours, plus 1 815 au rachat. S'il n'y a pas de rachat, il garde une position valant ce qu'elle vaut. Le vendeur a payé 2 USDG de frais et 9 USDG de loyer pour 1 815 USDG de cash, tout en encaissant les frais de swap de la semaine.

Contrainte codée : loyer + frais < prix. Le prix de rachat est libre. Le registre suggère à l'interface un prix de vente proche de la valeur de marché, la décote étant négociée et non imposée.

## 5. Loyer et gel du sous-jacent

Le loyer est un montant fixe pour le terme, prépayé en escrow, qui s'écoule linéairement par seconde utilisable. Il ne compose jamais et n'est jamais affiché annualisé par le contrat.

Le bailleur porte le risque du propriétaire. La v1 matérialise ce risque par le gel : à chaque interaction et à chaque appel de `checkpointFreeze`, le vault interroge `paused()` sur les deux jetons de la paire. Les secondes gelées sont retirées de l'assiette du loyer et remboursées au locataire au règlement. Le terme calendaire, lui, ne s'allonge pas.

Limite connue : un gel non checkpointé n'est pas rétroactif. Un keeper doit appeler `checkpointFreeze` aux transitions. Une destruction de la position par exploit du pool n'est pas détectable de façon générique on-chain ; dans ce cas le financeur possède une position sans valeur et le locataire ne doit rien de plus, ce qui est le résultat attendu en ijara.

## 6. Mapping fiqh

| Exigence | Mécanisme dans le code | Référence |
|---|---|---|
| Vente réelle, transfert de propriété | Le NFT est enregistré au financeur dès `fund`, cessible via `transferFinancierPosition`, livré par `release` sans étape de « réclamation » | AAOIFI 9, 3/1 ; déclaration sukuk 2008 |
| Le bailleur porte le risque de l'actif | Loyer suspendu pendant le gel, remboursement du non-couru ; aucune créance sur le locataire en cas de destruction | AAOIFI 9, 5/1/7 |
| Loyer pour un usufruit réel | Le locataire encaisse les frais de swap via `collectFees` ; la position doit être dans le range au listing (`OutOfRange`) et avoir une liquidité minimale | AAOIFI 9, 5/1 |
| Pas de 'inah | Vente et bail sont deux actes réglés dans l'ordre dans `fund` ; le financeur ne peut pas céder au locataire hors `buyBack`. La vérification `SelfDeal` compare des adresses : elle empêche l'auto-financement évident, pas un vendeur qui utiliserait une seconde adresse. Aucun contrat ne peut faire mieux on-chain, c'est au comité de l'apprécier | Académie du Fiqh OCI, rés. 66 ; AAOIFI 9, 3/2 |
| Rachat par promesse unilatérale, prix fixé admis | `buyBack` au `buybackPrice`, exercice au seul choix du locataire | Déclaration AAOIFI 2008 sur les sukuk ijara, à condition que le bailleur porte la perte totale |
| Pas de ghalaq ar-rahn | Il n'y a pas de gage : le financeur ne « garde » rien, il prend livraison de son bien | Hadith « la yaghlaq ar-rahn » |
| Frais de service au coût, pas en pourcentage | `listingFee` en montant fixe, plafonné à la construction du registre, snapshoté dans le deal | AAOIFI 19 sur les frais de qard, par analogie |
| Pas d'oracle ni de liquidation | Aucun prix lu dans le chemin du deal ; `StateView` sert seulement à vérifier le range au listing | Principe du produit |
| Actifs licites | Allowlist par pool, `assetClass`, `screeningRef` | Screening AAOIFI 21 pour les actions |

Points restant à faire trancher par un comité :

1. Le loyer exprimé en pourcentage du prix par l'interface, même si le contrat ne connaît qu'un montant. Position AAOIFI : l'indexation du loyer est admise, l'affichage ne change pas la nature.
2. Le rachat à prix fixe égal au prix de vente. Admis par la déclaration AAOIFI de 2008 pour les sukuk ijara, critiqué par une partie des savants. Alternative : rachat à valeur de marché calculée depuis l'état du pool, qui expose à la manipulation de prix sur les pools peu profonds.
3. Le remboursement du loyer non couru en cas de rachat anticipé. Cohérent avec un bail qui s'éteint par transfert de propriété ; certains comités préfèrent un rachat au prix de rachat plus le loyer restant.
4. Le caractère « productif » d'une position LP sur une paire crypto. Les frais de swap sont un revenu de service de marché ; la licéité dépend de la licéité des deux jetons et de l'absence de mécanisme de prêt dans le pool.

## 7. Cadre réglementaire au 17 septembre 2026

**SEC, exemption d'innovation.** Ordonnance temporaire de cinq ans exemptant les Tokenized Securities Venues de la définition de bourse pour le trading d'actions NMS tokenisées via des AMM permissionnés, avec une exemption conditionnelle de la définition de dealer pour les fournisseurs de liquidité en capital propre. Conditions : participants permissionnés, contrats auditables sur registre public, arrêts synchronisés avec le marché primaire, notification de l'émetteur, limites de symboles et de volume, interdiction pour la venue d'offrir du financement. Seules les actions tokenisées portant les mêmes droits qu'une action sont éligibles ; les synthétiques sont exclus.

Conséquences pour Lease Vault :

- Les positions LP sur pools de TSV seront détenues par le vault, contrat sans propriétaire. Il faut vérifier si un contrat peut être « participant permissionné » et si l'exemption dealer couvre un financeur qui achète une position existante plutôt que d'apporter de la liquidité lui-même.
- Le vault n'est pas une TSV et n'offre pas de financement au sens de l'ordonnance : il n'y a ni prêt ni marge. La qualification exacte reste à confirmer avec un conseil.
- Les Stock Tokens Robinhood actuels, titres de dette Jersey interdits aux personnes américaines, sont hors périmètre et ne doivent pas être allowlistés.

**CFTC, lettre 26-25.** No-action pour les fournisseurs de logiciels passifs qui ne détiennent pas de fonds, n'exercent aucune discrétion, ne routent pas d'ordres et ne sont pas rémunérés en fonction du volume. Le vault et une interface qui l'affiche cochent ces cases, ce qui est un argument pour une interface neutre rémunérée par des frais fixes. Cette lettre concerne les registrations IB et AP côté dérivés, pas les titres.

## 8. Sécurité

Une passe d'audit adversarial a eu lieu le 19 septembre 2026 ; ses conclusions et ce qui a été
corrigé sont dans `../../docs/AUDIT.md`. Deux points en sont issus et méritent d'être lus ici :
le gel n'est compté que six heures au-delà de la dernière observation, sinon un seul appel pendant
un arrêt d'une seconde suffirait à stopper le loyer pour tout le terme ; et les frais gagnés
pendant la période de grâce reviennent à celui qui prend livraison, le bail étant terminé.


- Réentrance : verrou simple sur toutes les fonctions qui déplacent des actifs. Les transferts NFT utilisent `transferFrom`, sans hook de réception.
- Registre : ses paramètres sont lus au listing et gelés dans le deal ; un changement ultérieur ne touche aucun deal actif. Le registre ne peut pas retirer d'actifs.
- Actions v4 : le vault ne sait encoder que la collecte de frais. Toute autre modification de liquidité est impossible tant que le NFT est dans le vault.
- Abonnés v4 : refusés au listing ; v4 désabonne de toute façon au transfert.
- Jetons à pause : `collectFees` échoue proprement si le jeton est gelé ; le loyer est suspendu.
- Pools permissionnés v4 : les actions `UNWIND_WITH_FALLBACK`, `SUBSCRIBE` et `UNSUBSCRIBE` ne sont pas utilisées. Un hook qui refuse les transferts vers un contrat empêcherait le listing, ce qui est le comportement souhaité.

## 9. Feuille de route

1. Fait. Compilation et 29 tests unitaires.
2. Fait. 5 tests d'intégration en fork de Robinhood Chain contre le vrai PositionManager : garde du NFT, collecte des frais sans toucher à la liquidité, rachat, livraison au financeur d'une position qu'il peut réellement dénouer, impossibilité pour le locataire de retirer la liquidité pendant le bail.
3. Interface : listing, financement, timeline du bail, rappels avant échéance, affichage du loyer en montant et en pourcentage pour le terme.
4. Revue par un comité shariah sur la base de la section 6.
5. Avis réglementaire sur la section 7 avant d'allowlister une paire d'actions tokenisées à droits complets.
6. Audit.
