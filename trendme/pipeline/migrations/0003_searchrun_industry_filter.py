# Generated migration for SearchRun.industry_filter field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pipeline", "0002_technologycandidate_industry"),
    ]

    operations = [
        migrations.AddField(
            model_name="searchrun",
            name="industry_filter",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
    ]
