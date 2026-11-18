# DepensePro — Backend Django REST

## Windows / PowerShell
```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py makemigrations expenses
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 0.0.0.0:8000
```
API locale : `http://127.0.0.1:8000/api/`
API sur le réseau local : `http://192.168.100.132:8000/api/`

Compte de test : `demo@depensepro.local` / `Demo2026!`

En développement (`DEBUG=True`), le backend autorise les origines Web sur
`localhost`, `127.0.0.1` et `192.168.100.132`, y compris les ports de
développement Flutter variables. Pour un autre frontend, ajoutez son origine à
`CORS_ALLOWED_ORIGINS` (origines séparées par des virgules). En production,
définissez explicitement cette variable et n'activez pas l'autorisation globale.

## API
- `POST auth/register/` `{ "name": "...", "email": "...", "password": "...", "password_confirmation": "..." }` → `201 Created`
- `POST auth/login/` `{ "email": "...", "password": "..." }` → token DRF
- `POST auth/password/forgot/` `{ "email": "..." }` → demande un envoi OTP par e-mail ; aucun OTP n’est retourné par l’API
- `POST auth/password/verify-otp/` `{ "email": "...", "otp": "123456" }` → valide l’OTP
- `POST auth/password/reset/` `{ "email": "...", "otp": "123456", "password": "...", "password_confirmation": "..." }` → change le mot de passe
- `POST auth/logout/`
- `GET auth/me/`
- `GET dashboard/`
- `GET|POST categories/`
- `GET|PUT|PATCH|DELETE categories/<id>/`
- `GET|POST transactions/`
- `GET|PATCH|DELETE transactions/<id>/`
- `GET|POST budgets/?period_type=daily&date=2026-11-12`
- `GET|POST budgets/?period_type=monthly&month=11&year=2026`
- `GET|POST budgets/?period_type=yearly&year=2026` (budget annuel)
- `GET|PUT|PATCH|DELETE budgets/<id>/`
- `GET reports/?months=6`
- `GET|PATCH profile/`

Les routes `auth/register/` et `auth/login/` sont publiques. Toutes les autres routes nécessitent `Authorization: Token <token>`.
Le frontend Flutter enregistre le token et le transmet à chaque requête.
Les trois routes `auth/password/forgot/`, `auth/password/verify-otp/` et `auth/password/reset/` sont publiques. L'OTP expire après 5 minutes. Pour qu'un vrai email soit envoyé, configurez le SMTP dans l'environnement avant de démarrer Django, par exemple avec Gmail :

```powershell
$env:EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
$env:EMAIL_HOST = "smtp.gmail.com"
$env:EMAIL_PORT = "587"
$env:EMAIL_USE_TLS = "True"
$env:EMAIL_HOST_USER = "votre.adresse@gmail.com"
$env:EMAIL_HOST_PASSWORD = "votre_mot_de_passe_application"
$env:DEFAULT_FROM_EMAIL = "votre.adresse@gmail.com"
python manage.py runserver 0.0.0.0:8000
```

Gmail requiert généralement un mot de passe d'application (avec la validation en deux étapes activée), pas le mot de passe habituel. Ne mettez jamais ce secret dans le code ou dans le frontend. En mode console, aucun email réel n'est envoyé : le message est écrit dans le terminal du serveur. En cas d'échec SMTP, l'API conserve une réponse générique et journalise l'erreur côté serveur, sans divulguer le code ni révéler si le compte existe.
Les réponses des budgets incluent `spent`, `remaining`, `percentage` et `alert`. L'alerte est `null` sous 80 %, contient le code `BUDGET_80_PERCENT` de 80 % à moins de 100 %, et `BUDGET_100_PERCENT` à partir de 100 %. Le frontend doit recharger les budgets après création ou modification d'une dépense pour afficher les alertes dans l'application. Aucun service de notification push/SMS n'est configuré.

Pour tester sur téléphone physique, démarrez Django avec `0.0.0.0:8000` et mettez dans
`lib/core/api_config.dart` l'adresse IPv4 LAN du PC, par exemple `http://192.168.100.132:8000/api`.
Le téléphone et le PC doivent être sur le même Wi-Fi. Autorisez le port 8000 dans le pare-feu Windows.
Pour Android émulateur, utilisez `http://10.0.2.2:8000/api`.

## Notifications

Le contrat OpenAPI des endpoints de notifications est décrit dans
[openapi-notifications.yaml](./openapi-notifications.yaml).

Les notifications internes couvrent l’enregistrement, la modification et la
suppression des transactions, les franchissements des seuils budgétaires de
80 % et 100 %, les connexions et événements de sécurité, ainsi que les
annonces envoyées par un super-administrateur. Le compte peut activer les
e-mails séparément dans **Mon compte > Préférences**. Les alertes de sécurité
liées à une réinitialisation réussie du mot de passe restent envoyées par
e-mail.

Les e-mails nécessitent une configuration SMTP (`EMAIL_HOST`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, etc.). En développement sans SMTP,
Django utilise le backend console et écrit les e-mails dans le terminal du
serveur. Exécutez `python manage.py migrate` après mise à jour.

Les paiements ne sont pas traités par l’application : les méthodes « carte » ou
« mobile money » sont uniquement des champs de transaction, donc aucun état de
paiement réussi/échoué n’est disponible. Les objectifs et tâches restent
stockés sur l’appareil ; les rappels planifiés, les dépenses récurrentes et les
bilans périodiques par e-mail nécessiteront leur synchronisation côté serveur
et un ordonnanceur. La détection des dépenses inhabituelles nécessite aussi
une règle de comparaison à définir.

## Réinitialisation du mot de passe par OTP e-mail

Le code OTP est généré uniquement par Django, stocké sous forme de hash et envoyé par SMTP. Flutter ne génère, ne reçoit et n'affiche jamais le code. Le code expire après 5 minutes, ne peut être utilisé qu'une fois et est bloqué après 5 tentatives invalides. Une demande est limitée à une demande par minute et par compte.

En production, configurez les variables d'environnement SMTP à partir de `.env.example`. Avec Gmail, activez la validation en deux étapes puis créez un mot de passe d'application Google. Utilisez ce mot de passe d'application dans `EMAIL_HOST_PASSWORD`, jamais votre mot de passe Gmail normal. Ne commitez jamais le fichier `.env` ni les identifiants SMTP.

En développement, Django peut utiliser `django.core.mail.backends.console.EmailBackend` : le message est alors écrit dans le terminal du serveur et aucun e-mail réel n'est envoyé. Pour tester l'envoi réel, configurez un serveur SMTP ou un fournisseur transactionnel.

## Espace administrateur

Les routes `/api/admin/...` exigent un utilisateur `is_staff`, `is_superuser` ou un profil dont le rôle est `admin` / `super_admin`. L'API expose les statistiques globales, la liste et la gestion des utilisateurs, les catégories gérées par l'administrateur connecté, les devises et les paramètres de plateforme. Un administrateur peut également ouvrir « Mon espace utilisateur » pour gérer ses propres dépenses, revenus, budgets et rapports.

Après mise à jour :

```bash
python manage.py migrate
python manage.py check
python manage.py test expenses
```

Pour promouvoir un compte existant en administrateur :

```bash
python manage.py shell
```

Puis dans le shell Django :

```python
from django.contrib.auth.models import User
from expenses.models import UserProfile
u = User.objects.get(email="admin@example.com")
u.is_staff = True
u.save(update_fields=["is_staff"])
p, _ = UserProfile.objects.get_or_create(user=u)
p.role = "admin"
p.save(update_fields=["role"])
```


## DepensePro 2.0 — configuration sûre
Consultez `DEPENSEPRO_2.0_UPGRADE.md` avant toute migration. Le fichier `.env` ne doit jamais être partagé ni commité. Pour PostgreSQL, définissez `DB_ENGINE=postgres` et les variables `DB_*`.
