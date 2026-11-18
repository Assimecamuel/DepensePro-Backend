from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from datetime import date
from decimal import Decimal
from smtplib import SMTPException
from unittest.mock import patch
import re
from django.contrib.auth.hashers import check_password
from expenses.models import (
    Budget, Category, PasswordResetOTP, Transaction, Notification, UserProfile,
)
from rest_framework.test import APITestCase


class RegistrationTests(APITestCase):
    def test_registration_creates_account_and_account_can_login(self):
        response = self.client.post("/api/auth/register/", {
            "name": "Alex Doe",
            "email": "alex@example.com",
            "password": "StrongPassword123!",
            "password_confirmation": "StrongPassword123!",
        }, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["user"]["name"], "Alex Doe")
        self.assertEqual(response.data["user"]["email"], "alex@example.com")
        user = User.objects.get(email="alex@example.com")
        self.assertTrue(user.check_password("StrongPassword123!"))

        response = self.client.post("/api/auth/login/", {
            "email": "alex@example.com",
            "password": "StrongPassword123!",
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["token"])

    def test_registration_rejects_duplicate_email_case_insensitively(self):
        User.objects.create_user(
            username="alex@example.com",
            email="alex@example.com",
            password="StrongPassword123!",
        )

        response = self.client.post("/api/auth/register/", {
            "name": "Alex Doe",
            "email": "ALEX@example.com",
            "password": "StrongPassword123!",
            "password_confirmation": "StrongPassword123!",
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_registration_rejects_mismatched_passwords(self):
        response = self.client.post("/api/auth/register/", {
            "name": "Alex Doe",
            "email": "alex@example.com",
            "password": "StrongPassword123!",
            "password_confirmation": "DifferentPassword123!",
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("password_confirmation", response.data)


class CorsHeadersTests(APITestCase):
    def test_flutter_web_origins_receive_cors_headers_on_preflight_and_login(self):
        for origin in (
            "http://localhost:54321",
            "http://127.0.0.1:54321",
            "http://192.168.100.132:54321",
        ):
            with self.subTest(origin=origin):
                preflight = self.client.options(
                    "/api/auth/login/",
                    HTTP_ORIGIN=origin,
                    HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
                    HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
                )
                self.assertEqual(
                    preflight.get("Access-Control-Allow-Origin"),
                    origin,
                )

                response = self.client.post(
                    "/api/auth/login/",
                    {},
                    format="json",
                    HTTP_ORIGIN=origin,
                )
                self.assertEqual(
                    response.get("Access-Control-Allow-Origin"),
                    origin,
                )


class PasswordResetEmailTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reset@example.com",
            email="reset@example.com",
            password="OriginalPassword123!",
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        DEBUG=False,
    )
    def test_forgot_password_sends_email_then_otp_resets_password(self):
        response = self.client.post(
            "/api/auth/password/forgot/",
            {"email": self.user.email},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("debug_otp", response.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

        otp_record = PasswordResetOTP.objects.get(user=self.user, is_active=True)
        self.assertEqual(otp_record.otp_code, "")
        otp_code = re.search(r"(\d{6})", mail.outbox[0].body).group(1)
        self.assertTrue(check_password(otp_code, otp_record.otp_hash))
        response = self.client.post(
            "/api/auth/password/verify-otp/",
            {"email": self.user.email, "otp": otp_code},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["verified"])

        response = self.client.post(
            "/api/auth/password/reset/",
            {
                "email": self.user.email,
                "otp": otp_code,
                "password": "NewPassword123!",
                "password_confirmation": "NewPassword123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassword123!"))
        self.assertFalse(PasswordResetOTP.objects.get(user=self.user).is_active)

    @patch("expenses.views.send_password_reset_otp", side_effect=SMTPException("SMTP unavailable"))
    def test_smtp_failure_is_reported_and_otp_cannot_be_used(self, send_otp):
        response = self.client.post(
            "/api/auth/password/forgot/",
            {"email": self.user.email},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("debug_otp", response.data)
        self.assertFalse(PasswordResetOTP.objects.filter(user=self.user, is_active=True).exists())


class CategoryDetailTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="category-user", password="test-password")
        self.category = Category.objects.create(
            user=self.user, name="Transport", kind="expense",
        )
        self.client.force_authenticate(self.user)

    def test_category_can_be_retrieved_updated_and_deleted(self):
        response = self.client.get(f"/api/categories/{self.category.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Transport")

        response = self.client.patch(
            f"/api/categories/{self.category.id}/",
            {"name": "Transport public"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["name"], "Transport public")

        response = self.client.delete(f"/api/categories/{self.category.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Category.objects.filter(pk=self.category.id).exists())

    def test_category_cannot_be_accessed_or_changed_by_another_user(self):
        other_user = User.objects.create_user(username="other-category-user", password="test-password")
        self.client.force_authenticate(other_user)

        response = self.client.patch(
            f"/api/categories/{self.category.id}/",
            {"name": "Changed"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Transport")

    def test_category_with_transactions_cannot_be_deleted(self):
        Transaction.objects.create(
            user=self.user,
            category=self.category,
            kind="expense",
            amount=Decimal("10.00"),
            date=date(2026, 11, 12),
        )

        response = self.client.delete(f"/api/categories/{self.category.id}/")

        self.assertEqual(response.status_code, 409)
        self.assertTrue(Category.objects.filter(pk=self.category.id).exists())


class BudgetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="budget-user", password="test-password")
        self.category = Category.objects.create(user=self.user, name="Food", kind="expense")
        self.client.force_authenticate(self.user)

    def add_expense(self, amount, date_value):
        Transaction.objects.create(
            user=self.user,
            category=self.category,
            kind="expense",
            amount=Decimal(amount),
            date=date_value,
        )

    def test_monthly_budget_reports_spending_remaining_and_80_percent_alert(self):
        self.add_expense("80.00", date(2026, 11, 5))
        self.add_expense("50.00", date(2026, 10, 5))
        response = self.client.post("/api/budgets/", {
            "category": self.category.id,
            "amount": "100.00",
            "period_type": "monthly",
            "month": 11,
            "year": 2026,
        }, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data["spent"]), Decimal("80.00"))
        self.assertEqual(Decimal(response.data["remaining"]), Decimal("20.00"))
        self.assertEqual(response.data["percentage"], 80.0)
        self.assertEqual(response.data["alert"]["code"], "BUDGET_80_PERCENT")

    def test_yearly_budget_includes_all_months_and_alerts_at_100_percent(self):
        self.add_expense("60.00", date(2026, 1, 5))
        self.add_expense("40.00", date(2026, 11, 5))
        response = self.client.post("/api/budgets/", {
            "category": self.category.id,
            "amount": "100.00",
            "period_type": "yearly",
            "year": 2026,
        }, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data["month"])
        self.assertEqual(Decimal(response.data["spent"]), Decimal("100.00"))
        self.assertEqual(Decimal(response.data["remaining"]), Decimal("0.00"))
        self.assertEqual(response.data["alert"]["code"], "BUDGET_100_PERCENT")

    def test_budget_can_be_updated_and_deleted(self):
        budget = Budget.objects.create(
            user=self.user, category=self.category, amount="100.00",
            period_type=Budget.MONTHLY, month=11, year=2026,
        )
        response = self.client.patch(f"/api/budgets/{budget.id}/", {
            "amount": "200.00",
        }, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Decimal(response.data["amount"]), Decimal("200.00"))

        response = self.client.delete(f"/api/budgets/{budget.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Budget.objects.filter(pk=budget.id).exists())

    def test_budget_categories_must_belong_to_requesting_user(self):
        other_user = User.objects.create_user(username="other", password="test-password")
        other_category = Category.objects.create(user=other_user, name="Private", kind="expense")
        response = self.client.post("/api/budgets/", {
            "category": other_category.id,
            "amount": "100.00",
            "period_type": "yearly",
            "year": 2026,
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("category", response.data)


class NotificationAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="notify@example.com",
            email="notify@example.com",
            password="StrongPassword123!",
        )
        self.category = Category.objects.create(
            user=self.user,
            name="Alimentation",
            kind="expense",
        )
        from rest_framework.authtoken.models import Token
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")

    def test_creating_transaction_creates_persistent_notification(self):
        response = self.client.post("/api/transactions/", {
            "category": self.category.id,
            "kind": "expense",
            "amount": "15000.00",
            "date": "2026-11-13",
            "payment_method": "cash",
            "description": "Courses",
        }, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        notification = Notification.objects.get(user=self.user)
        self.assertEqual(notification.kind, "transaction")
        self.assertIn("Alimentation", notification.message)

        listing = self.client.get("/api/notifications/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["unread_count"], 1)
        self.assertEqual(len(listing.data["notifications"]), 1)

    def test_budget_warning_is_created_only_when_threshold_is_crossed(self):
        Budget.objects.create(
            user=self.user,
            category=self.category,
            amount=Decimal("100000.00"),
            period_type=Budget.MONTHLY,
            month=11,
            year=2026,
            alert_thresholds={"warning_percent": 80, "critical_percent": 100},
        )
        response = self.client.post("/api/transactions/", {
            "category": self.category.id,
            "kind": "expense",
            "amount": "85000.00",
            "date": "2026-11-13",
            "payment_method": "cash",
            "description": "Courses",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            Notification.objects.filter(user=self.user, kind="budget_warning").count(),
            1,
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_transaction_notifications_are_emailed_when_user_opted_in(self):
        UserProfile.objects.create(
            user=self.user,
            email_notifications_enabled=True,
        )
        response = self.client.post("/api/transactions/", {
            "category": self.category.id,
            "kind": "expense",
            "amount": "15000.00",
            "date": "2026-11-13",
            "payment_method": "cash",
            "description": "Courses",
        }, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Dépense enregistrée", mail.outbox[0].subject)

    def test_transaction_update_and_delete_create_notifications(self):
        Budget.objects.create(
            user=self.user,
            category=self.category,
            amount=Decimal("100.00"),
            period_type=Budget.MONTHLY,
            month=11,
            year=2026,
        )
        transaction = Transaction.objects.create(
            user=self.user,
            category=self.category,
            kind="expense",
            amount="70.00",
            date="2026-11-13",
        )
        response = self.client.patch(
            f"/api/transactions/{transaction.id}/",
            {"amount": "85.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(
            Notification.objects.filter(
                user=self.user,
                kind="transaction_updated",
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.user,
                kind="budget_warning",
            ).exists()
        )

        response = self.client.delete(f"/api/transactions/{transaction.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertTrue(
            Notification.objects.filter(
                user=self.user,
                kind="transaction_deleted",
            ).exists()
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_crossing_80_and_100_percent_sends_separate_budget_alerts(self):
        UserProfile.objects.create(
            user=self.user,
            email_notifications_enabled=True,
        )
        Budget.objects.create(
            user=self.user,
            category=self.category,
            amount=Decimal("100.00"),
            period_type=Budget.MONTHLY,
            month=11,
            year=2026,
        )
        for amount in ("85.00", "20.00"):
            response = self.client.post("/api/transactions/", {
                "category": self.category.id,
                "kind": "expense",
                "amount": amount,
                "date": "2026-11-13",
                "payment_method": "cash",
            }, format="json")
            self.assertEqual(response.status_code, 201, response.data)

        self.assertEqual(
            Notification.objects.filter(user=self.user, kind="budget_warning").count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(user=self.user, kind="budget_critical").count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 4)

    def test_email_notification_preference_can_be_updated(self):
        response = self.client.patch(
            "/api/profile/",
            {"email_notifications_enabled": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["profile"]["email_notifications_enabled"])
        self.assertTrue(
            UserProfile.objects.get(user=self.user).email_notifications_enabled
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_successful_login_creates_security_notification_and_email(self):
        UserProfile.objects.create(
            user=self.user,
            email_notifications_enabled=True,
        )
        self.client.credentials()

        response = self.client.post(
            "/api/auth/login/",
            {"email": self.user.email, "password": "StrongPassword123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(
            Notification.objects.filter(
                user=self.user,
                kind="security_login",
            ).exists()
        )
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_super_admin_announcement_reaches_in_app_and_opted_in_email_users(self):
        UserProfile.objects.create(
            user=self.user,
            email_notifications_enabled=True,
        )
        super_admin = User.objects.create_superuser(
            username="platform-admin",
            email="platform-admin@example.com",
            password="StrongPassword123!",
        )
        self.client.force_authenticate(super_admin)

        response = self.client.post(
            "/api/admin/announcements/",
            {"title": "Maintenance", "message": "Service update tonight."},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["notifications_created"], 2)
        self.assertEqual(response.data["emails_sent"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            Notification.objects.filter(
                user=self.user,
                kind="announcement",
                title="Maintenance",
            ).exists()
        )

    def test_non_super_admin_cannot_send_announcements(self):
        response = self.client.post(
            "/api/admin/announcements/",
            {"title": "Maintenance", "message": "Service update tonight."},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_mark_all_read_does_not_delete_notifications(self):
        Notification.objects.create(
            user=self.user,
            title="Test",
            message="Notification de test",
        )
        response = self.client.post("/api/notifications/mark-all-read/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.user, is_read=False).count(), 0)

    def test_notification_can_be_marked_read_individually(self):
        notification = Notification.objects.create(
            user=self.user,
            title="Test",
            message="Notification de test",
        )

        response = self.client.patch(
            f"/api/notifications/{notification.id}/",
            {"is_read": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)


class AdminAccessTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", email="admin@example.com", password="StrongPassword123!", is_staff=True)
        self.client.force_authenticate(self.admin)

    def test_admin_overview_returns_registered_user_counts(self):
        User.objects.create_user(username="ordinary", email="ordinary@example.com", password="StrongPassword123!")
        response = self.client.get("/api/admin/overview/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["stats"]["total_users"], 1)
        self.assertEqual(response.data["stats"]["active_users"], 1)

    def test_admin_can_list_and_create_users(self):
        response = self.client.post("/api/admin/users/", {
            "username": "created", "email": "created@example.com",
            "password": "StrongPassword123!", "role": "user", "is_active": True,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["role"], "user")
        response = self.client.get("/api/admin/users/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

    def test_regular_user_cannot_access_admin_overview(self):
        ordinary = User.objects.create_user(username="ordinary", password="StrongPassword123!")
        self.client.force_authenticate(ordinary)
        response = self.client.get("/api/admin/overview/")
        self.assertEqual(response.status_code, 403)
