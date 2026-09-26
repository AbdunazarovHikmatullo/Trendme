# Generated migration for SourceDocument.categories field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("parser", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sourcedocument",
            name="categories",
            field=models.JSONField(default=list, blank=True),
        ),
    ]
