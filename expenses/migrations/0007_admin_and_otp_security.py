from django.db import migrations, models


def deactivate_legacy_otps(apps, schema_editor):
    PasswordResetOTP = apps.get_model("expenses", "PasswordResetOTP")
    PasswordResetOTP.objects.all().update(is_active=False, otp_code="")


class Migration(migrations.Migration):
    dependencies = [('expenses', '0006_notification')]

    operations = [
        migrations.AddField(
            model_name='passwordresetotp', name='otp_hash',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='passwordresetotp', name='attempts',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='passwordresetotp', name='otp_code',
            field=models.CharField(blank=True, default='', max_length=6),
        ),
        migrations.RunPython(deactivate_legacy_otps, migrations.RunPython.noop),
        migrations.AddField(
            model_name='userprofile', name='role',
            field=models.CharField(choices=[('user', 'Utilisateur'), ('admin', 'Administrateur'), ('super_admin', 'Super administrateur')], default='user', max_length=20),
        ),
        migrations.CreateModel(
            name='GlobalCurrency',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=8, unique=True)),
                ('name', models.CharField(max_length=80)),
                ('symbol', models.CharField(blank=True, max_length=12)),
                ('is_active', models.BooleanField(default=True)),
                ('is_default', models.BooleanField(default=False)),
            ],
            options={'ordering': ['-is_default', 'code']},
        ),
        migrations.CreateModel(
            name='PlatformSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=80, unique=True)),
                ('value', models.JSONField(blank=True, default=dict)),
            ],
        ),
    ]
