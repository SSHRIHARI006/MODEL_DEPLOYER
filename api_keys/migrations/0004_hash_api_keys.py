"""SEC-07: store legacy API keys as digests only.

Existing rows are hashed in place and the plaintext column is removed, so after
this migration the database holds no reusable key material. Clients keep working
because verification hashes the presented value and looks it up by digest.
"""

import hashlib
import secrets

from django.db import migrations, models

KEY_PREFIX_LENGTH = 8
KEY_BYTES = 32


def hashed_fields(raw_key: str) -> dict[str, str]:
    """Kept inline on purpose: migrations must not import application code."""
    return {
        "key_hash": hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
        "key_prefix": raw_key[:KEY_PREFIX_LENGTH],
    }


def hash_existing_keys(apps, schema_editor):
    APIKey = apps.get_model("api_keys", "APIKey")

    for key in APIKey.objects.all().iterator():
        raw = key.key or ""
        if not raw:
            # A row with no usable plaintext is already unusable; give it an
            # unknown secret instead of failing the NOT NULL column.
            raw = secrets.token_hex(KEY_BYTES)
        for field, value in hashed_fields(raw).items():
            setattr(key, field, value)
        key.save(update_fields=["key_hash", "key_prefix"])


class Migration(migrations.Migration):

    dependencies = [
        ("api_keys", "0003_universalapikey"),
    ]

    operations = [
        migrations.AddField(
            model_name="apikey",
            name="key_hash",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="apikey",
            name="key_prefix",
            field=models.CharField(blank=True, default="", max_length=12),
        ),
        migrations.RunPython(hash_existing_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="apikey",
            name="key_hash",
            field=models.CharField(db_index=True, max_length=64, unique=True),
        ),
        migrations.RemoveField(model_name="apikey", name="key"),
    ]
