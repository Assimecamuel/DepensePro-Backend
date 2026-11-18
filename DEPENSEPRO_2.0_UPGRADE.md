# DepensePro 2.0 — audit initial et stratégie de mise à niveau

## État du socle livré

Le backend actuel est un projet Django 5.2 + Django REST Framework, avec une application `expenses`. Il contient déjà les modèles Category, Transaction, Budget, PasswordResetOTP, UserProfile, Notification, GlobalCurrency et PlatformSetting. Les routes historiques sont centralisées dans `expenses/urls.py` et doivent rester compatibles.

Le frontend est une application Flutter unique avec authentification, tableau de bord, transactions, budgets, catégories, objectifs, tâches, rapports, analyses, paramètres, notifications et espace administrateur. Il utilise actuellement `http`, `shared_preferences`, `fl_chart`, `pdf` et `printing`.

## Règles de conservation

1. Ne pas supprimer ni réécrire les migrations existantes.
2. Ne pas renommer les routes `/api/auth/`, `/api/transactions/`, `/api/budgets/`, `/api/categories/`, `/api/dashboard/`, `/api/reports/` ou `/api/profile/`.
3. Ajouter les nouveaux modules de manière additive et versionner leurs routes sous `/api/v2/` si un contrat incompatible devient nécessaire.
4. Faire une sauvegarde de la base avant toute migration.
5. Les transferts entre comptes ne doivent pas être comptés comme dépenses ou revenus.
6. Les opérations hors ligne doivent avoir une clé d'idempotence et une résolution explicite des conflits.
7. Les paiements Orange Money / MTN MoMo doivent être confirmés par webhook signé du fournisseur ; ne jamais collecter ni stocker le PIN Mobile Money.

## Modules DepensePro 2.0 à ajouter

- Comptes financiers multiples et transferts internes.
- Transactions récurrentes avec exécution idempotente.
- Objectifs d'épargne et contributions historisées.
- Dettes, emprunts et remboursements.
- Notifications configurables et préférences par canal.
- Rapports PDF/Excel générés côté serveur en complément des rapports Flutter existants.
- Adaptateur Mobile Money pour Orange Money et MTN MoMo, activé uniquement après obtention des accès marchands/sandbox.
- Synchronisation hors ligne avec journal des opérations et déduplication.
- Budgets familiaux, membres, invitations et permissions.
- Administration plateforme, audit et indicateurs de supervision.

## Configuration PostgreSQL

SQLite reste utilisé par défaut en développement pour ne pas casser l'installation existante. Pour activer PostgreSQL, installer le pilote puis configurer `DB_ENGINE=postgres` et les variables `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.

Avant la migration : sauvegarder la base actuelle. Pour transférer les données SQLite vers PostgreSQL, utiliser `dumpdata`/`loaddata` après validation du schéma et des contraintes, puis vérifier les totaux de transactions, budgets, catégories et comptes utilisateurs. Ne pas supprimer `db.sqlite3` avant validation métier.

## Configuration Flutter

La configuration API ne contient plus d'adresse IP privée codée en dur. Exemples :

```powershell
# Web / desktop local
flutter run -d chrome --dart-define=API_BASE_URL=http://127.0.0.1:8000/api

# Android Emulator
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api

# Production
flutter build web --release --dart-define=API_BASE_URL=https://api.votre-domaine.com/api
```

## Dépendances externes qui nécessitent des accès

- SMTP : compte expéditeur et mot de passe d'application/fournisseur.
- Push : projet Firebase, clés FCM et configuration des applications.
- Orange Money / MTN MoMo : contrat marchand, identifiants sandbox puis production, URL de callback/webhook et documentation officielle du pays.
- Déploiement : domaine API HTTPS, PostgreSQL, stockage média et sauvegardes.

Ces intégrations ne doivent pas être simulées comme des paiements réels.

## Sécurité des archives source

Les archives initiales contenaient un fichier `.env` et des identifiants SMTP dans `.env.example`. Les fichiers secrets et la base SQLite ne sont pas inclus dans cette livraison nettoyée. Il faut renouveler la clé Django et le mot de passe d'application SMTP exposés dans les archives, puis stocker les nouvelles valeurs uniquement dans les variables d'environnement du serveur.
