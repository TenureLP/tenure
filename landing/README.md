# Landing et waitlist

Page statique plus un endpoint d'inscription. Aucune dépendance, aucun build.

```
index.html          la page, CSS et JS inclus
assets/             logo, favicon, image de partage
api/waitlist.py     endpoint POST /api/waitlist (fonction Python Vercel)
dev_server.py       aperçu local, bibliothèque standard uniquement
```

## Aperçu local

```bash
python dev_server.py
```

Puis ouvrir http://127.0.0.1:8410. En local, les inscriptions s'ajoutent à `waitlist.jsonl`, une ligne JSON par personne, sans doublon.

## Où vont les inscriptions en production

L'endpoint lit la variable `WAITLIST_WEBHOOK_URL` et y envoie chaque inscription en POST JSON.

- **Webhook Discord.** Le plus rapide : dans un salon privé, Paramètres, Intégrations, Webhooks, copier l'URL. Chaque inscription arrive comme un message. L'URL est détectée et le message est mis au format Discord.
- **Google Sheets, Make, Zapier ou ta propre API.** Toute autre URL reçoit `{"email", "role", "source", "ts"}`.

Sans cette variable, un déploiement Vercel répond 503 au lieu de perdre des inscriptions en silence.

Garde-fous inclus : validation de l'email côté page et côté serveur, champ piège pour les robots, corps de requête limité à 4 Ko, rôles et sources restreints à une liste.

## Déployer sur Vercel

1. Créer un projet Vercel dont la racine est ce dossier `landing`. Aucun framework, aucune commande de build.
2. Ajouter la variable d'environnement `WAITLIST_WEBHOOK_URL`.
3. Déployer. `index.html` est servi à la racine et `api/waitlist.py` devient `/api/waitlist`.

## Avant de publier

- Le nom « Tenure » est un nom de travail. Vérifier la marque et le domaine.
- Relire les affirmations de la section Status à chaque évolution : nombre de tests, audit, déploiement.
- L'image de partage `og:image` doit être une URL absolue une fois le domaine connu.
- Les emails sont des données personnelles. Le pied de page promet un seul usage et la suppression sur demande : s'y tenir, et prévoir une adresse de contact.
