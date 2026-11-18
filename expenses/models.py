import secrets
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal

class Category(models.Model):
    EXPENSE = "expense"
    INCOME = "income"
    KIND_CHOICES = [(EXPENSE, "Dépense"), (INCOME, "Revenu")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=EXPENSE)
    color = models.CharField(max_length=7, default="#2563EB")
    icon = models.CharField(max_length=12, default="📦")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name", "kind"], name="uniq_category_user_name_kind")
        ]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class Transaction(models.Model):
    PAYMENT_CHOICES = [
        ("cash", "Espèces"), ("card", "Carte bancaire"),
        ("mobile_money", "Mobile Money"), ("transfer", "Virement"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="transactions")
    kind = models.CharField(max_length=10, choices=Category.KIND_CHOICES)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=5, default="FCFA")
    date = models.DateField(default=timezone.localdate)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default="cash")
    description = models.CharField(max_length=255, blank=True)
    receipt = models.ImageField(upload_to="receipts/%Y/%m/", blank=True, null=True)
    repeat_monthly = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["user", "date"]), models.Index(fields=["user", "kind"])]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount} {self.currency}"


class Budget(models.Model):
    DAILY = "daily"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    PERIOD_CHOICES = [(DAILY, "Journalier"), (MONTHLY, "Mensuel"), (YEARLY, "Annuel")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budgets")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="budgets")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    period_type = models.CharField(max_length=10, choices=PERIOD_CHOICES, default=MONTHLY)
    date = models.DateField(null=True, blank=True, default=timezone.localdate)
    month = models.PositiveSmallIntegerField(default=timezone.localdate().month, null=True, blank=True)
    year = models.PositiveSmallIntegerField(default=timezone.localdate().year)
    alert_thresholds = models.JSONField(default=dict, blank=True)
    notify_channels = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "category", "date"],
                condition=Q(period_type="daily"),
                name="uniq_daily_budget_period",
            ),
            models.UniqueConstraint(
                fields=["user", "category", "month", "year"],
                condition=Q(period_type="monthly"),
                name="uniq_monthly_budget_period",
            ),
            models.UniqueConstraint(
                fields=["user", "category", "year"],
                condition=Q(period_type="yearly"),
                name="uniq_yearly_budget_period",
            ),
        ]

    def __str__(self):
        return f"{self.category.name} — {self.amount}"


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_reset_otps")
    # otp_code est conservé pour compatibilité avec les anciennes lignes, mais reste vide.
    otp_code = models.CharField(max_length=6, blank=True, default="")
    otp_hash = models.CharField(max_length=128, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    @staticmethod
    def generate_otp_code():
        return f"{secrets.randbelow(900000) + 100000:06d}"

    def __str__(self):
        return f"OTP de réinitialisation pour {self.user.email}"


class UserProfile(models.Model):
    ROLE_CHOICES = [("user", "Utilisateur"), ("admin", "Administrateur"), ("super_admin", "Super administrateur")]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="user")
    THEME_CHOICES = [("light", "Clair"), ("dark", "Sombre")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="expense_profile")
    currency = models.CharField(max_length=5, default="FCFA")
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default="light")
    notifications_enabled = models.BooleanField(default=True)
    email_notifications_enabled = models.BooleanField(default=False)

    def __str__(self):
        return f"Profil {self.user.username}"


class Notification(models.Model):
    """Notification persistante appartenant à un utilisateur."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="expense_notifications",
    )
    title = models.CharField(max_length=160)
    message = models.TextField()
    kind = models.CharField(max_length=40, default="general")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} — {self.user}"


class GlobalCurrency(models.Model):
    code = models.CharField(max_length=8, unique=True)
    name = models.CharField(max_length=80)
    symbol = models.CharField(max_length=12, blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class PlatformSetting(models.Model):
    key = models.CharField(max_length=80, unique=True)
    value = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.key
