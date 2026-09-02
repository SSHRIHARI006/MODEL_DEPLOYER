from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("deployments", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="deployment",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "PENDING"),
                    ("BUILDING", "BUILDING"),
                    ("RUNNING", "RUNNING"),
                    ("FAILED", "FAILED"),
                    ("STOPPED", "STOPPED"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="deployment",
            name="runtime_type",
            field=models.CharField(default="container", max_length=20),
        ),
        migrations.AddField(
            model_name="deployment",
            name="build_logs",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deployment",
            name="container_id",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name="deployment",
            name="container_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="deployment",
            name="image_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="deployment",
            name="internal_url",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deployment",
            name="last_error",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deployment",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deployment",
            name="stopped_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deployment",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
