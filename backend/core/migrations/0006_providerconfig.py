from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_approvalpolicy"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProviderConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "provider",
                    models.CharField(
                        choices=[("anthropic", "Anthropic (Claude)"), ("openai", "OpenAI (GPT)")],
                        default="anthropic",
                        max_length=20,
                    ),
                ),
                ("openai_key", models.TextField(blank=True, default="")),
                ("anthropic_key", models.TextField(blank=True, default="")),
                ("updated_by", models.CharField(blank=True, default="", max_length=150)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
