from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_email_verified_and_privacy"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="chat_wallpaper",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="wallpaper",
            field=models.ImageField(blank=True, null=True, upload_to="wallpapers/"),
        ),
    ]
