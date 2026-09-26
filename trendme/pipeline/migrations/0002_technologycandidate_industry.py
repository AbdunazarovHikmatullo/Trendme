# Generated migration for TechnologyCandidate.industry field

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pipeline", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="technologycandidate",
            name="industry",
            field=models.CharField(
                blank=True,
                choices=[
                    ("industrial_ai", "Индустриальный ИИ"),
                    ("robotics", "Робототехника"),
                    ("infrastructure", "Инфраструктура ИИ"),
                    ("fintech", "Финтех"),
                    ("ai_security", "Защита ИИ"),
                    ("edge", "Edge Computing"),
                    ("semiconductor", "Полупроводники"),
                    ("energy", "Энергетика"),
                    ("health", "Здравоохранение / Биотех"),
                    ("other", "Другое"),
                ],
                default="other",
                max_length=32,
            ),
        ),
        migrations.AddIndex(
            model_name="technologycandidate",
            index=models.Index(fields=["run", "industry"], name="pipeline_te_industry_idx"),
        ),
    ]
