from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_providerconfig_openai_endpoint"),
    ]

    operations = [
        migrations.AddField(
            model_name="providerconfig",
            name="image_key",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="providerconfig",
            name="image_base_url",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="providerconfig",
            name="image_model",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="providerconfig",
            name="image_size",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AlterField(
            model_name="artifact",
            name="kind",
            field=models.CharField(
                choices=[("html", "html"), ("markdown", "markdown"), ("text", "text"), ("image", "image")],
                default="markdown",
                max_length=10,
            ),
        ),
    ]
