from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token
from expenses.models import Category, Transaction, Budget, UserProfile

class Command(BaseCommand):
    help = "Crée le compte de démonstration et quelques données."
    def handle(self, *args, **kwargs):
        user, created = User.objects.get_or_create(
            username="demo",
            defaults={"email": "demo@depensepro.local", "first_name": "Jean", "last_name": "Dupont"}
        )
        if created:
            user.set_password("Demo2026!")
            user.save()
        Token.objects.get_or_create(user=user)
        UserProfile.objects.get_or_create(user=user)
        definitions = [
            ("Logement", "expense", "#ef4444", "🏠"),
            ("Alimentation", "expense", "#f59e0b", "🍴"),
            ("Transport", "expense", "#10b981", "🚌"),
            ("Loisirs", "expense", "#8b5cf6", "🎮"),
            ("Salaire", "income", "#10b981", "💰"),
            ("Autres revenus", "income", "#2563eb", "📈"),
        ]
        cats = {}
        for name, kind, color, icon in definitions:
            cats[name], _ = Category.objects.get_or_create(
                user=user, name=name, kind=kind, defaults={"color": color, "icon": icon}
            )
        today = timezone.localdate()
        if not Transaction.objects.filter(user=user).exists():
            examples = [
                ("expense", 15000, "Alimentation", 0, "card", "Restaurant"),
                ("income", 320000, "Salaire", 1, "transfer", "Salaire mensuel"),
                ("expense", 10000, "Transport", 2, "mobile_money", "Transport"),
                ("expense", 120000, "Logement", 3, "transfer", "Loyer"),
                ("expense", 25000, "Alimentation", 5, "cash", "Courses"),
            ]
            for kind, amount, category, days, payment, description in examples:
                Transaction.objects.create(
                    user=user, category=cats[category], kind=kind, amount=Decimal(amount),
                    date=today-timedelta(days=days), payment_method=payment, description=description
                )
        for name, amount in [("Alimentation", 300000), ("Transport", 150000), ("Loisirs", 100000), ("Logement", 200000)]:
            Budget.objects.get_or_create(
                user=user, category=cats[name], month=today.month, year=today.year,
                defaults={"amount": Decimal(amount)}
            )
        self.stdout.write(self.style.SUCCESS("Démo prête : demo@depensepro.local / Demo2026!"))
