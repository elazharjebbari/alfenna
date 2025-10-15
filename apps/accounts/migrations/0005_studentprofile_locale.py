from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_user_email_ci"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentprofile",
            name="locale",
            field=models.CharField(blank=True, default="", max_length=12),
        ),
    ]
