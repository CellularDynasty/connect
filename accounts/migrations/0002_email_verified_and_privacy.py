from django.db import migrations, models


def verify_existing_users(apps, schema_editor):
    """Accounts created before email verification existed are grandfathered in
    as verified - they should not suddenly be locked out."""
    User = apps.get_model("accounts", "User")
    User.objects.all().update(email_verified=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(verify_existing_users, migrations.RunPython.noop),
        migrations.AddField(
            model_name="userprofile",
            name="show_online_status",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="show_last_seen",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="send_read_receipts",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="discoverable",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="show_email",
            field=models.BooleanField(default=False),
        ),
    ]
