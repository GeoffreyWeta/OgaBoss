from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_image_generation"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposal",
            name="error",
            field=models.TextField(blank=True, default="", help_text="Why the last run failed, shown to the CEO"),
        ),
    ]
