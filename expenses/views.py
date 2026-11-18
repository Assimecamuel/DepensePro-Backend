from calendar import month_abbr
from datetime import date, timedelta
from decimal import Decimal
from smtplib import SMTPException
import logging
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction as db_transaction
from django.db.models import Count, Q
from django.contrib.auth.models import User
from django.db.models import Sum
from django.core.mail import send_mail, send_mass_mail
from django.shortcuts import get_object_or_404
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from .models import Category, Transaction, Budget, UserProfile, PasswordResetOTP, Notification, GlobalCurrency, PlatformSetting
logger = logging.getLogger(__name__)

from .serializers import (
    CategorySerializer, TransactionSerializer, BudgetSerializer,
    ProfileSerializer, RegistrationSerializer, ForgotPasswordRequestSerializer,
    PasswordResetOTPVerifySerializer, PasswordResetSerializer, NotificationSerializer,
    AnnouncementSerializer,
)

def profile_for(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile

@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def register_view(request):
    serializer = RegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response({
        "detail": "Account created successfully.",
        "user": {
            "id": user.id,
            "name": user.get_full_name() or user.username,
            "email": user.email,
        },
    }, status=status.HTTP_201_CREATED)

@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def login_view(request):
    identifier = str(request.data.get("email", "")).strip()
    password = str(request.data.get("password", ""))
    account = User.objects.filter(email__iexact=identifier).first() if "@" in identifier else User.objects.filter(username=identifier).first()
    user = authenticate(request, username=account.username if account else identifier, password=password)
    if not user:
        return Response({"detail": "Identifiants incorrects."}, status=status.HTTP_401_UNAUTHORIZED)
    token, _ = Token.objects.get_or_create(user=user)
    profile_for(user)
    create_user_notification(
        user,
        "Nouvelle connexion",
        "Une nouvelle connexion à votre compte DepensePro a réussi.",
        "security_login",
    )
    return Response({
        "token": token.key,
        "user": {"id": user.id, "name": user.get_full_name() or user.username, "email": user.email}
    })

@api_view(["POST"])
def logout_view(request):
    request.user.auth_token.delete()
    return Response({"detail": "Déconnexion réussie."})

@api_view(["GET"])
def me_view(request):
    p = profile_for(request.user)
    return Response({"id": request.user.id, "name": request.user.get_full_name() or request.user.username,
                     "email": request.user.email, "currency": p.currency, "theme": p.theme,
                     "notifications_enabled": p.notifications_enabled, "role": p.role,
                     "is_staff": request.user.is_staff, "is_superuser": request.user.is_superuser})


def send_password_reset_otp(user, otp_code):
    subject = "Code de réinitialisation du mot de passe - DepensePro"
    message = (
        f"Bonjour {user.get_full_name() or user.username},\n\n"
        f"Votre code de réinitialisation est : {otp_code}.\n"
        "Ce code expire dans 5 minutes et ne peut être utilisé qu'une seule fois.\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email."
    )
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def forgot_password_request_view(request):
    serializer = ForgotPasswordRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data["email"]
    user = User.objects.filter(email__iexact=email).first()

    # Même réponse pour une adresse existante ou non : ne pas révéler les comptes.
    generic_response = {
        "detail": "Si un compte correspond à cette adresse, un code de réinitialisation lui sera envoyé.",
        "expires_in_minutes": 5,
    }
    if user is None:
        return Response(generic_response, status=status.HTTP_200_OK)

    latest = PasswordResetOTP.objects.filter(user=user).order_by("-created_at").first()
    if latest and latest.created_at > timezone.now() - timedelta(seconds=60):
        return Response(generic_response, status=status.HTTP_200_OK)

    create_user_notification(
        user,
        "Demande de récupération du compte",
        "Une demande de réinitialisation du mot de passe a été effectuée pour votre compte.",
        "security_recovery",
        email=False,
    )
    PasswordResetOTP.objects.filter(user=user, is_active=True).update(is_active=False)
    otp_code = PasswordResetOTP.generate_otp_code()
    otp_record = PasswordResetOTP.objects.create(
        user=user,
        otp_hash=make_password(otp_code),
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    try:
        send_password_reset_otp(user, otp_code)
    except Exception:
        otp_record.is_active = False
        otp_record.save(update_fields=["is_active"])
        logger.exception("Échec de l'envoi du code de réinitialisation pour le compte %s", user.pk)
        # Réponse identique pour éviter l'énumération des comptes.
    return Response(generic_response, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def verify_password_reset_otp_view(request):
    serializer = PasswordResetOTPVerifySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data["email"]
    otp_code = serializer.validated_data["otp"]
    user = User.objects.filter(email__iexact=email).first()
    otp_record = PasswordResetOTP.objects.filter(
        user=user, is_active=True, expires_at__gte=timezone.now(), attempts__lt=5,
    ).order_by("-created_at").first() if user else None

    if otp_record is None or not check_password(otp_code, otp_record.otp_hash):
        if otp_record is not None:
            otp_record.attempts += 1
            if otp_record.attempts >= 5:
                otp_record.is_active = False
            otp_record.save(update_fields=["attempts", "is_active"])
        return Response({"detail": "Code OTP invalide ou expiré."}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"detail": "Code OTP valide. Vous pouvez définir un nouveau mot de passe.", "verified": True})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def reset_password_view(request):
    serializer = PasswordResetSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data["user"]
    otp_record = serializer.validated_data["otp_record"]
    new_password = serializer.validated_data["password"]

    with db_transaction.atomic():
        otp_record = PasswordResetOTP.objects.select_for_update().get(pk=otp_record.pk)
        if (not otp_record.is_active or otp_record.expires_at < timezone.now()
                or otp_record.attempts >= 5 or not check_password(request.data.get("otp", ""), otp_record.otp_hash)):
            return Response({"detail": "Code OTP invalide ou expiré."}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new_password)
        user.save(update_fields=["password"])
        otp_record.is_active = False
        otp_record.used_at = timezone.now()
        otp_record.save(update_fields=["is_active", "used_at"])
        # Invalide les anciennes sessions API après changement du mot de passe.
        from rest_framework.authtoken.models import Token
        Token.objects.filter(user=user).delete()

    create_user_notification(
        user,
        "Mot de passe modifié",
        "Le mot de passe de votre compte DepensePro vient d'être modifié. Si vous n'êtes pas à l'origine de cette action, contactez l'administrateur.",
        "security_password",
        force_email=True,
    )
    return Response({"detail": "Mot de passe réinitialisé avec succès."})

def create_user_notification(
    user, title, message, kind="general", *, email=True, force_email=False
):
    profile = profile_for(user)
    notification = None
    if profile.notifications_enabled:
        notification = Notification.objects.create(
            user=user,
            title=title[:160],
            message=message,
            kind=kind,
        )

    should_send_email = bool(
        user.email and (force_email or (email and profile.email_notifications_enabled))
    )
    if should_send_email:
        try:
            send_mail(
                f"DepensePro — {title}",
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
        except Exception:
            logger.exception(
                "Échec de l'envoi d'une notification par e-mail pour le compte %s",
                user.pk,
            )
    return notification


@api_view(["GET"])
def notifications_list_view(request):
    notifications = Notification.objects.filter(user=request.user)
    return Response({
        "notifications": NotificationSerializer(notifications[:100], many=True).data,
        "unread_count": notifications.filter(is_read=False).count(),
    })


@api_view(["POST"])
def notifications_mark_all_read_view(request):
    updated = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({"ok": True, "updated": updated})


@api_view(["PATCH", "DELETE"])
def notification_detail_view(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if request.method == "DELETE":
        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = NotificationSerializer(
        notification,
        data={"is_read": request.data.get("is_read", True)},
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


def _transaction_state(transaction):
    return {
        "user_id": transaction.user_id,
        "category_id": transaction.category_id,
        "kind": transaction.kind,
        "amount": transaction.amount,
        "currency": transaction.currency,
        "date": transaction.date,
    }


def _state_matches_budget(state, budget):
    if (
        state is None
        or state["user_id"] != budget.user_id
        or state["category_id"] != budget.category_id
        or state["kind"] != "expense"
    ):
        return False
    transaction_date = state["date"]
    if budget.period_type == Budget.DAILY:
        return budget.date == transaction_date
    if budget.period_type == Budget.MONTHLY:
        return (
            budget.year == transaction_date.year
            and budget.month == transaction_date.month
        )
    return budget.year == transaction_date.year


def _budget_spent(budget):
    expenses = Transaction.objects.filter(
        user=budget.user,
        category=budget.category,
        kind="expense",
        date__year=budget.year,
    )
    if budget.period_type == Budget.DAILY:
        expenses = expenses.filter(date=budget.date)
    elif budget.period_type == Budget.MONTHLY:
        expenses = expenses.filter(date__month=budget.month)
    return expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")


def _threshold(value, default):
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal(default)


def notify_budget_threshold_crossings(user, current_state, previous_state=None):
    if not any(
        state and state["kind"] == "expense"
        for state in (current_state, previous_state)
    ):
        return

    for budget in Budget.objects.filter(user=user).select_related("category"):
        if not (
            _state_matches_budget(current_state, budget)
            or _state_matches_budget(previous_state, budget)
        ):
            continue

        current_spent = _budget_spent(budget)
        previous_spent = current_spent
        if _state_matches_budget(current_state, budget):
            previous_spent -= current_state["amount"]
        if _state_matches_budget(previous_state, budget):
            previous_spent += previous_state["amount"]
        previous_spent = max(previous_spent, Decimal("0"))
        if not budget.amount:
            continue

        previous_pct = previous_spent * 100 / budget.amount
        current_pct = current_spent * 100 / budget.amount
        thresholds = budget.alert_thresholds or {}
        warning = _threshold(thresholds.get("warning_percent", 80), "80")
        critical = _threshold(thresholds.get("critical_percent", 100), "100")
        currency = (current_state or previous_state)["currency"]

        if previous_pct < warning <= current_pct:
            create_user_notification(
                user,
                "Alerte budget",
                f"Vous avez utilisé {current_pct:.0f} % de votre budget {budget.category.name}.",
                "budget_warning",
            )
        if previous_pct < critical <= current_pct:
            create_user_notification(
                user,
                "Budget dépassé" if current_pct > 100 else "Budget atteint",
                f"Le budget {budget.category.name} a atteint {current_pct:.0f} % "
                f"({current_spent:,.0f} / {budget.amount:,.0f} {currency}).",
                "budget_critical",
            )


def notify_transaction_created(transaction):
    create_user_notification(
        transaction.user,
        "Dépense enregistrée" if transaction.kind == "expense" else "Revenu enregistré",
        f"{transaction.amount:,.0f} {transaction.currency} enregistré dans "
        f"{transaction.category.name}.",
        "transaction",
    )
    notify_budget_threshold_crossings(
        transaction.user,
        _transaction_state(transaction),
    )


def notify_transaction_updated(transaction, previous_state):
    create_user_notification(
        transaction.user,
        "Dépense modifiée" if transaction.kind == "expense" else "Revenu modifié",
        f"La transaction de {transaction.amount:,.0f} {transaction.currency} "
        f"dans {transaction.category.name} a été modifiée.",
        "transaction_updated",
    )
    notify_budget_threshold_crossings(
        transaction.user,
        _transaction_state(transaction),
        previous_state,
    )


def notify_transaction_deleted(user, state, category_name):
    create_user_notification(
        user,
        "Dépense supprimée" if state["kind"] == "expense" else "Revenu supprimé",
        f"La transaction de {state['amount']:,.0f} {state['currency']} "
        f"dans {category_name} a été supprimée.",
        "transaction_deleted",
    )
    notify_budget_threshold_crossings(user, None, state)


def _is_platform_admin(user):
    if user.is_staff or user.is_superuser:
        return True
    return UserProfile.objects.filter(user=user, role__in=["admin", "super_admin"]).exists()


def _admin_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not _is_platform_admin(request.user):
            return Response({"detail": "Accès réservé à l'administration."}, status=status.HTTP_403_FORBIDDEN)
        return view(request, *args, **kwargs)
    return wrapped


def _user_admin_data(user):
    profile = profile_for(user)
    role = "super_admin" if user.is_superuser or profile.role == "super_admin" else ("admin" if user.is_staff or profile.role == "admin" else "user")
    return {
        "id": user.id, "username": user.username,
        "name": user.get_full_name() or user.username,
        "email": user.email, "role": role, "is_active": user.is_active,
        "date_joined": user.date_joined.isoformat(),
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


@api_view(["GET"])
@_admin_required
def admin_overview_view(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    qs = User.objects.filter(is_staff=False, is_superuser=False)
    transactions = Transaction.objects.filter(date__year=today.year, date__month=today.month)
    return Response({
        "stats": {
            "total_users": qs.count(),
            "active_users": qs.filter(is_active=True).count(),
            "inactive_users": qs.filter(is_active=False).count(),
            "admin_accounts": User.objects.filter(is_staff=True).count(),
            "new_users_this_month": qs.filter(date_joined__date__gte=month_start).count(),
            "total_global_categories": Category.objects.count(),
            "monthly_transactions": transactions.count(),
            "monthly_income": float(transactions.filter(kind="income").aggregate(v=Sum("amount"))["v"] or 0),
            "monthly_expenses": float(transactions.filter(kind="expense").aggregate(v=Sum("amount"))["v"] or 0),
            "default_currency": (GlobalCurrency.objects.filter(is_default=True).values_list("code", flat=True).first() or "XAF"),
        },
        "recent_activity": [
            {"message": f"Nouvel utilisateur inscrit : {u.get_full_name() or u.username} ({u.email})",
             "name": u.get_full_name() or u.username, "email": u.email,
             "role": _user_admin_data(u)["role"], "created_at": u.date_joined.isoformat()}
            for u in User.objects.order_by("-date_joined")[:8]
        ],
    })


@api_view(["GET", "POST"])
@_admin_required
def admin_users_view(request):
    if request.method == "GET":
        users = User.objects.all().order_by("-date_joined")
        search = request.query_params.get("search", "").strip()
        role = request.query_params.get("role")
        state = request.query_params.get("status")
        if search:
            from django.db.models import Q
            users = users.filter(Q(username__icontains=search) | Q(email__icontains=search) | Q(first_name__icontains=search) | Q(last_name__icontains=search))
        if state == "active": users = users.filter(is_active=True)
        if state == "disabled": users = users.filter(is_active=False)
        if role == "user": users = users.filter(is_staff=False, is_superuser=False)
        elif role == "admin": users = users.filter(is_staff=True, is_superuser=False)
        elif role == "super_admin": users = users.filter(is_superuser=True)
        return Response({"results": [_user_admin_data(u) for u in users[:500]], "count": users.count()})

    data = request.data
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    role = str(data.get("role", "user"))
    if not username or not email or len(password) < 8 or role not in ("user", "admin", "super_admin"):
        return Response({"detail": "Nom, email, rôle valide et mot de passe (8 caractères minimum) requis."}, status=400)
    if role == "super_admin" and not request.user.is_superuser:
        return Response({"detail": "Seul un super administrateur peut créer un super administrateur."}, status=403)
    if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=username).exists():
        return Response({"detail": "Cet identifiant ou cet email existe déjà."}, status=400)
    user = User.objects.create_user(username=username, email=email, password=password, is_active=bool(data.get("is_active", True)), is_staff=role in ("admin", "super_admin"), is_superuser=role == "super_admin")
    profile_for(user).role = role
    profile_for(user).save(update_fields=["role"])
    return Response(_user_admin_data(user), status=201)


@api_view(["PATCH"])
@_admin_required
def admin_user_detail_view(request, pk):
    user = get_object_or_404(User, pk=pk)
    data = request.data
    if "is_active" in data:
        if user.pk == request.user.pk and not data["is_active"]:
            return Response({"detail": "Vous ne pouvez pas désactiver votre propre compte."}, status=400)
        user.is_active = bool(data["is_active"])
    if "role" in data:
        role = str(data["role"])
        if role not in ("user", "admin", "super_admin"):
            return Response({"detail": "Rôle invalide."}, status=400)
        if role == "super_admin" and not request.user.is_superuser:
            return Response({"detail": "Seul un super administrateur peut attribuer ce rôle."}, status=403)
        if user.is_superuser and not request.user.is_superuser:
            return Response({"detail": "Action réservée au super administrateur."}, status=403)
        user.is_staff = role in ("admin", "super_admin")
        user.is_superuser = role == "super_admin"
        profile_for(user).role = role
        profile_for(user).save(update_fields=["role"])
    user.save()
    return Response(_user_admin_data(user))


@api_view(["PATCH"])
@_admin_required
def admin_user_status_view(request, pk):
    user = get_object_or_404(User, pk=pk)
    active = request.data.get("is_active")
    if not isinstance(active, bool):
        return Response({"detail": "is_active doit être un booléen."}, status=400)
    if user.pk == request.user.pk and not active:
        return Response({"detail": "Vous ne pouvez pas désactiver votre propre compte."}, status=400)
    user.is_active = active
    user.save(update_fields=["is_active"])
    return Response(_user_admin_data(user))


@api_view(["GET", "POST"])
@_admin_required
def admin_categories_view(request):
    if request.method == "GET":
        cats = Category.objects.filter(user=request.user).order_by("name")
        return Response({"results": [{"id": c.id, "name": c.name, "type": c.kind, "kind": c.kind, "color": c.color, "icon": c.icon, "is_active": True} for c in cats]})
    data = request.data
    kind = data.get("type", data.get("kind", "expense"))
    if kind not in ("expense", "income") or not str(data.get("name", "")).strip():
        return Response({"detail": "Nom et type de catégorie valides requis."}, status=400)
    c = Category.objects.create(user=request.user, name=str(data["name"]).strip(), kind=kind, color=data.get("color", "#2563EB"), icon=data.get("icon", "📦"))
    return Response({"id": c.id, "name": c.name, "type": c.kind, "kind": c.kind, "color": c.color, "icon": c.icon, "is_active": True}, status=201)


@api_view(["PATCH", "DELETE"])
@_admin_required
def admin_category_detail_view(request, pk):
    c = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == "DELETE":
        if c.transactions.exists():
            return Response({"detail": "Cette catégorie est utilisée et ne peut pas être supprimée."}, status=409)
        c.delete()
        return Response(status=204)
    data = request.data
    if "name" in data: c.name = str(data["name"]).strip()
    if "type" in data or "kind" in data:
        kind = data.get("type", data.get("kind"))
        if kind not in ("expense", "income"):
            return Response({"detail": "Type de catégorie invalide."}, status=400)
        c.kind = kind
    if "color" in data: c.color = data["color"]
    if "icon" in data: c.icon = data["icon"]
    c.save()
    return Response({"id": c.id, "name": c.name, "type": c.kind, "kind": c.kind, "color": c.color, "icon": c.icon, "is_active": True})


@api_view(["GET", "POST"])
@_admin_required
def admin_currencies_view(request):
    if request.method == "GET":
        GlobalCurrency.objects.get_or_create(code="XAF", defaults={"name": "Franc CFA BEAC", "symbol": "FCFA", "is_active": True, "is_default": True})
        return Response({"results": list(GlobalCurrency.objects.values("id", "code", "name", "symbol", "is_active", "is_default"))})
    data = request.data
    code = str(data.get("code", "")).strip().upper()
    name = str(data.get("name", "")).strip()
    if not code or not name:
        return Response({"detail": "Code et nom de devise requis."}, status=400)
    if data.get("is_default"): GlobalCurrency.objects.update(is_default=False)
    currency = GlobalCurrency.objects.create(code=code, name=name, symbol=data.get("symbol", ""), is_active=True, is_default=bool(data.get("is_default", False)))
    return Response({"id": currency.id, "code": currency.code, "name": currency.name, "symbol": currency.symbol, "is_active": currency.is_active, "is_default": currency.is_default}, status=201)


@api_view(["PATCH"])
@_admin_required
def admin_currency_detail_view(request, pk):
    currency = get_object_or_404(GlobalCurrency, pk=pk)
    if request.data.get("is_default") is True:
        GlobalCurrency.objects.update(is_default=False)
        currency.is_default = True
    for field in ("name", "symbol", "is_active"):
        if field in request.data: setattr(currency, field, request.data[field])
    currency.save()
    return Response({"id": currency.id, "code": currency.code, "name": currency.name, "symbol": currency.symbol, "is_active": currency.is_active, "is_default": currency.is_default})


@api_view(["GET", "PATCH"])
@_admin_required
def admin_settings_view(request):
    defaults = {"platform_name": "DepensePro", "default_currency": "XAF", "timezone": "Africa/Douala", "allow_user_registration": True, "allow_guest_access": False, "maintenance_mode": False}
    setting, _ = PlatformSetting.objects.get_or_create(key="platform", defaults={"value": defaults})
    if request.method == "PATCH":
        setting.value = {**defaults, **setting.value, **request.data}
        setting.save(update_fields=["value"])
    return Response({**defaults, **setting.value})


@api_view(["POST"])
def admin_announcement_view(request):
    if not request.user.is_superuser:
        return Response(
            {"detail": "Action réservée au super administrateur."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = AnnouncementSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    title = serializer.validated_data["title"].strip()
    message = serializer.validated_data["message"].strip()
    if not title or not message:
        return Response(
            {"detail": "Le titre et le message sont obligatoires."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    eligible_users = User.objects.filter(is_active=True).filter(
        Q(expense_profile__isnull=True)
        | Q(expense_profile__notifications_enabled=True)
    )
    notifications = [
        Notification(user=user, title=title, message=message, kind="announcement")
        for user in eligible_users.iterator()
    ]
    Notification.objects.bulk_create(notifications)

    email_profiles = UserProfile.objects.filter(
        user__is_active=True,
        email_notifications_enabled=True,
    ).exclude(user__email="")
    email_messages = [
        (f"DepensePro — {title}", message, settings.DEFAULT_FROM_EMAIL, [profile.user.email])
        for profile in email_profiles.select_related("user").iterator()
    ]
    emails_sent = 0
    email_delivery_failed = False
    if email_messages:
        try:
            emails_sent = send_mass_mail(email_messages, fail_silently=False)
        except Exception:
            email_delivery_failed = True
            logger.exception(
                "Échec de l'envoi par e-mail de l'annonce du super administrateur"
            )

    return Response({
        "notifications_created": len(notifications),
        "emails_sent": emails_sent,
        "email_delivery_failed": email_delivery_failed,
    }, status=status.HTTP_201_CREATED)


class CategoryListCreate(generics.ListCreateAPIView):
    serializer_class = CategorySerializer
    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class CategoryDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CategorySerializer
    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        if category.transactions.exists():
            return Response(
                {"detail": "Cette catégorie est utilisée par des transactions et ne peut pas être supprimée."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            self.perform_destroy(category)
        except ProtectedError:
            return Response(
                {"detail": "Cette catégorie est utilisée par des transactions et ne peut pas être supprimée."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

class TransactionListCreate(generics.ListCreateAPIView):
    serializer_class = TransactionSerializer
    def get_queryset(self):
        qs = Transaction.objects.filter(user=self.request.user).select_related("category")
        kind = self.request.query_params.get("kind")
        if kind in ("expense", "income"): qs = qs.filter(kind=kind)
        month = self.request.query_params.get("month")
        if month == "current":
            today = timezone.localdate()
            qs = qs.filter(date__year=today.year, date__month=today.month)
        return qs

    def perform_create(self, serializer):
        transaction = serializer.save(user=self.request.user)
        notify_transaction_created(transaction)

class TransactionDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TransactionSerializer
    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user).select_related("category")

    def perform_update(self, serializer):
        previous_state = _transaction_state(serializer.instance)
        transaction = serializer.save()
        notify_transaction_updated(transaction, previous_state)

    def perform_destroy(self, instance):
        user = instance.user
        previous_state = _transaction_state(instance)
        category_name = instance.category.name
        instance.delete()
        notify_transaction_deleted(user, previous_state, category_name)

class BudgetListCreate(generics.ListCreateAPIView):
    serializer_class = BudgetSerializer
    def get_queryset(self):
        today = timezone.localdate()
        period_type = self.request.query_params.get("period_type", Budget.MONTHLY)
        if period_type not in (Budget.DAILY, Budget.MONTHLY, Budget.YEARLY):
            raise serializers.ValidationError({"period_type": "Choisissez 'daily', 'monthly' ou 'yearly'."})
        try:
            year = int(self.request.query_params.get("year", today.year))
        except (TypeError, ValueError):
            raise serializers.ValidationError({"year": "Fournissez une année valide."})
        if not 1 <= year <= 32767:
            raise serializers.ValidationError({"year": "L'année doit être comprise entre 1 et 32767."})
        filters = {"user": self.request.user, "period_type": period_type, "year": year}
        if period_type == Budget.DAILY:
            date_value = self.request.query_params.get("date") or str(today)
            try:
                from datetime import datetime
                filters["date"] = datetime.strptime(date_value, "%Y-%m-%d").date()
            except ValueError:
                raise serializers.ValidationError({"date": "Fournissez une date valide au format YYYY-MM-DD."})
        elif period_type == Budget.MONTHLY:
            try:
                month = int(self.request.query_params.get("month", today.month))
            except (TypeError, ValueError):
                raise serializers.ValidationError({"month": "Fournissez un mois valide entre 1 et 12."})
            if not 1 <= month <= 12:
                raise serializers.ValidationError({"month": "Le mois doit être compris entre 1 et 12."})
            filters["month"] = month
        return Budget.objects.filter(**filters).select_related("category")
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class BudgetDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BudgetSerializer
    def get_queryset(self):
        return Budget.objects.filter(user=self.request.user).select_related("category")

@api_view(["GET"])
def dashboard_view(request):
    today = timezone.localdate()
    qs = Transaction.objects.filter(user=request.user, date__year=today.year, date__month=today.month)
    expenses = qs.filter(kind="expense").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    incomes = qs.filter(kind="income").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    budgets = Budget.objects.filter(user=request.user, month=today.month, year=today.year)
    budget_total = budgets.aggregate(v=Sum("amount"))["v"] or Decimal("0")
    spent = expenses
    cats = []
    for row in qs.filter(kind="expense").values("category__name", "category__color", "category__icon").annotate(total=Sum("amount")).order_by("-total"):
        cats.append({"name": row["category__name"], "color": row["category__color"], "icon": row["category__icon"], "amount": float(row["total"])})
    monthly = []
    for offset in range(11, -1, -1):
        m = today.month - offset
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        total = Transaction.objects.filter(user=request.user, kind="expense", date__year=y, date__month=m).aggregate(v=Sum("amount"))["v"] or 0
        monthly.append({"month": month_abbr[m].capitalize(), "amount": float(total)})
    p = profile_for(request.user)
    return Response({
        "expenses": float(expenses), "incomes": float(incomes), "balance": float(incomes-expenses),
        "budget_total": float(budget_total), "budget_spent": float(spent),
        "budget_percentage": round(float(spent / budget_total * 100), 1) if budget_total else 0,
        "categories": cats, "monthly": monthly,
        "recent": TransactionSerializer(Transaction.objects.filter(user=request.user).select_related("category")[:6], many=True, context={"request": request}).data,
        "currency": p.currency,
    })

@api_view(["GET"])
def reports_view(request):
    try: months = max(1, min(int(request.query_params.get("months", 6)), 24))
    except ValueError: months = 6
    today = timezone.localdate()
    results = []
    for offset in range(months-1, -1, -1):
        m, y = today.month-offset, today.year
        while m <= 0:
            m += 12; y -= 1
        total = Transaction.objects.filter(user=request.user, kind="expense", date__year=y, date__month=m).aggregate(v=Sum("amount"))["v"] or 0
        results.append({"month": month_abbr[m].capitalize(), "year": y, "amount": float(total)})
    return Response({"results": results})

@api_view(["GET", "PATCH"])
def profile_view(request):
    p = profile_for(request.user)
    if request.method == "GET":
        return Response(ProfileSerializer(p).data)
    serializer = ProfileSerializer(p, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    changed_fields = [
        field for field, value in serializer.validated_data.items()
        if getattr(p, field) != value
    ]
    serializer.save()
    if changed_fields:
        create_user_notification(
            request.user,
            "Paramètres du compte modifiés",
            "Les paramètres de votre compte DepensePro ont été modifiés.",
            "security_profile",
        )
    return Response({"ok": True, "profile": serializer.data})
