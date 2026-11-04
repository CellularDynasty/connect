from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0002_conversationmember_cleared_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="kind",
            field=models.CharField(
                choices=[("text", "Text"), ("location", "Location")],
                default="text", max_length=10),
        ),
        migrations.AddField(
            model_name="message",
            name="latitude",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="message",
            name="longitude",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="message",
            name="location_live_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
