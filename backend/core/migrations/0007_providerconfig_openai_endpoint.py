from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_providerconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="providerconfig",
            name="openai_base_url",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="providerconfig",
            name="openai_model",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
