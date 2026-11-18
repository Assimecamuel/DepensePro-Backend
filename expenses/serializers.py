from rest_framework import serializers
from django.contrib.auth.models import User
from django.db.models import Sum
from django.utils import timezone
from .models import Category, Transaction, Budget, UserProfile, PasswordResetOTP, Notification


class RegistrationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    password_confirmation = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        value = value.strip()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This email cannot be used for a username.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirmation"]:
            raise serializers.ValidationError({
                "password_confirmation": "Passwords do not match."
            })
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirmation")
        name = validated_data.pop("name").strip()
        email = validated_data.pop("email")
        password = validated_data.pop("password")
        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=name,
            password=password,
        )
        return user


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "kind", "color", "icon", "created_at"]
        read_only_fields = ["id", "created_at"]


class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_icon = serializers.CharField(source="category.icon", read_only=True)
    category_color = serializers.CharField(source="category.color", read_only=True)
    payment_label = serializers.CharField(source="get_payment_method_display", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "category", "category_name", "category_icon", "category_color",
            "kind", "amount", "currency", "date", "payment_method", "payment_label",
            "description", "receipt", "repeat_monthly", "created_at",
        ]
        read_only_fields = ["id", "currency", "created_at"]

    def validate_category(self, category):
        request = self.context["request"]
        if category.user_id != request.user.id:
            raise serializers.ValidationError("Cat?gorie non autoris?e.")
        return category

    def validate(self, attrs):
        category = attrs.get("category", getattr(self.instance, "category", None))
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        if category and kind and category.kind != kind:
            raise serializers.ValidationError({"category": "Le type de cat?gorie ne correspond pas ? la transaction."})
        return attrs

    def create(self, validated_data):
        profile, _ = UserProfile.objects.get_or_create(user=self.context["request"].user)
        validated_data["currency"] = profile.currency
        return super().create(validated_data)


class BudgetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_icon = serializers.CharField(source="category.icon", read_only=True)
    spent = serializers.SerializerMethodField()
    remaining = serializers.SerializerMethodField()
    percentage = serializers.SerializerMethodField()
    alert = serializers.SerializerMethodField()
    alert_thresholds = serializers.JSONField(required=False, default=dict)
    notify_channels = serializers.JSONField(required=False, default=list)

    class Meta:
        model = Budget
        fields = [
            "id", "category", "category_name", "category_icon", "amount",
            "period_type", "date", "month", "year", "spent", "remaining", "percentage", "alert",
            "alert_thresholds", "notify_channels",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        period_type = attrs.get("period_type", getattr(self.instance, "period_type", Budget.MONTHLY))
        category = attrs.get("category", getattr(self.instance, "category", None))
        year = attrs.get("year", getattr(self.instance, "year", timezone.localdate().year))
        month = attrs.get("month", getattr(self.instance, "month", timezone.localdate().month))
        date_value = attrs.get("date", getattr(self.instance, "date", timezone.localdate()))

        if period_type == Budget.DAILY:
            if date_value is None:
                raise serializers.ValidationError({"date": "La date est obligatoire pour un budget journalier."})
            attrs["month"] = date_value.month
            attrs["year"] = date_value.year
        elif period_type == Budget.MONTHLY:
            if month is None or not 1 <= month <= 12:
                raise serializers.ValidationError({"month": "Le mois doit ?tre compris entre 1 et 12 pour un budget mensuel."})
            attrs["date"] = None
        elif period_type == Budget.YEARLY:
            attrs["month"] = None
            attrs["date"] = None
        else:
            raise serializers.ValidationError({"period_type": "Choisissez 'daily', 'monthly' ou 'yearly'."})

        if category and (
            category.user_id != self.context["request"].user.id or category.kind != "expense"
        ):
            raise serializers.ValidationError({
                "category": "Choisissez une cat?gorie de d?pense qui vous appartient."
            })

        if category:
            filters = {
                "user": self.context["request"].user,
                "category": category,
                "period_type": period_type,
                "year": year,
            }
            if period_type == Budget.DAILY:
                filters["date"] = date_value
            elif period_type == Budget.MONTHLY:
                filters["month"] = month
            duplicate = Budget.objects.filter(**filters)
            if self.instance:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise serializers.ValidationError({
                    "category": "Un budget existe d?j? pour cette cat?gorie et cette p?riode."
                })
        return attrs

    def validate_category(self, category):
        if category.user_id != self.context["request"].user.id or category.kind != "expense":
            raise serializers.ValidationError("Choisissez une cat?gorie de d?pense qui vous appartient.")
        return category

    @staticmethod
    def get_spent_amount(obj):
        if hasattr(obj, "_budget_spent_amount"):
            return obj._budget_spent_amount
        transactions = Transaction.objects.filter(
            user=obj.user, category=obj.category, kind="expense",
            date__year=obj.year,
        )
        if obj.period_type == Budget.DAILY:
            transactions = transactions.filter(date=obj.date)
        elif obj.period_type == Budget.MONTHLY:
            transactions = transactions.filter(date__month=obj.month)
        spent = transactions.aggregate(total=Sum("amount"))["total"] or 0
        obj._budget_spent_amount = spent
        return spent

    def get_spent(self, obj):
        return self.get_spent_amount(obj)

    def get_remaining(self, obj):
        return max(obj.amount - self.get_spent_amount(obj), 0)

    def get_percentage(self, obj):
        spent = self.get_spent_amount(obj)
        return round(float(spent / obj.amount * 100), 1) if obj.amount else 0

    def get_alert(self, obj):
        percentage = self.get_percentage(obj)
        thresholds = obj.alert_thresholds or {}
        warning_percent = thresholds.get("warning_percent") or 80
        critical_percent = thresholds.get("critical_percent") or 100
        if percentage >= float(critical_percent):
            return {
                "code": "BUDGET_100_PERCENT",
                "threshold": int(critical_percent),
                "message": "Le budget de cette cat?gorie est atteint ou d?pass?.",
            }
        if percentage >= float(warning_percent):
            return {
                "code": "BUDGET_80_PERCENT",
                "threshold": int(warning_percent),
                "message": "Vous avez utilis? au moins 80 % du budget de cette cat?gorie.",
            }
        low_threshold = thresholds.get("low_percent")
        if low_threshold is not None and percentage >= float(low_threshold):
            return {
                "code": "LOW_BUDGET",
                "threshold": int(low_threshold),
                "message": "Votre budget est d?j? ? un niveau de consommation faible mais significatif.",
            }
        return None


class ForgotPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=150)

    def validate_email(self, value):
        return value.strip()


class PasswordResetOTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=150)
    otp = serializers.CharField(min_length=6, max_length=6)

    def validate_email(self, value):
        return value.strip()

    def validate_otp(self, value):
        return value.strip()


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=150)
    otp = serializers.CharField(min_length=6, max_length=6)
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    password_confirmation = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        return value.strip()

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirmation"]:
            raise serializers.ValidationError({
                "password_confirmation": "Les mots de passe ne correspondent pas."
            })

        from django.contrib.auth.hashers import check_password
        user = User.objects.filter(email__iexact=attrs["email"]).first()
        otp_record = PasswordResetOTP.objects.filter(
            user=user, is_active=True, expires_at__gte=timezone.now(), attempts__lt=5,
        ).order_by("-created_at").first() if user else None
        if otp_record is None or not check_password(attrs["otp"], otp_record.otp_hash):
            if otp_record is not None:
                otp_record.attempts += 1
                if otp_record.attempts >= 5:
                    otp_record.is_active = False
                otp_record.save(update_fields=["attempts", "is_active"])
            raise serializers.ValidationError({"otp": "Le code OTP est invalide ou expiré."})
        attrs["user"] = user
        attrs["otp_record"] = otp_record
        return attrs


class ProfileSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)
    role = serializers.CharField(read_only=True)
    is_staff = serializers.BooleanField(source="user.is_staff", read_only=True)
    is_superuser = serializers.BooleanField(source="user.is_superuser", read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "name", "email", "currency", "theme", "notifications_enabled",
            "email_notifications_enabled", "role", "is_staff", "is_superuser",
        ]

    def get_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "message", "kind", "is_read", "created_at"]
        read_only_fields = ["id", "title", "message", "kind", "created_at"]


class AnnouncementSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    message = serializers.CharField(max_length=5000)
