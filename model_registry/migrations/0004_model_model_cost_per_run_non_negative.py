"""SEC-08: model prices cannot be negative.

Before this migration the update endpoint assigned `cost_per_run` without a
serializer, so a database can already hold negative rates. A negative rate is
never a valid price (it credites the consumer), and both SQLite's table rebuild
and PostgreSQL's `ALTER TABLE ... ADD CONSTRAINT` fail while a violating row
exists, so existing offenders are reset to 0 ("no charge") first.
"""

from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


def clamp_negative_prices(apps, schema_editor):
    """Repair rows the new constraint would reject.

    Reverse is a no-op: the original negative values are intentionally not kept
    anywhere, so a rollback leaves them at 0 rather than restoring bad data.
    """
    Model = apps.get_model("model_registry", "Model")

    Model.objects.filter(cost_per_run__lt=0).update(cost_per_run=Decimal("0"))


class Migration(migrations.Migration):

    dependencies = [
        ('model_registry', '0003_alter_model_cost_per_run'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(clamp_negative_prices, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='model',
            constraint=models.CheckConstraint(condition=models.Q(('cost_per_run__gte', 0)), name='model_cost_per_run_non_negative'),
        ),
    ]
