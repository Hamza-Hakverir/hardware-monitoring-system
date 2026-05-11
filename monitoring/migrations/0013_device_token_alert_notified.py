import secrets
from django.db import migrations, models


def _assign_tokens(apps, schema_editor):
    Device = apps.get_model('monitoring', 'Device')
    for device in Device.objects.filter(token__isnull=True):
        device.token = secrets.token_hex(32)
        device.save(update_fields=['token'])


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0012_hourly_aggregate'),
    ]

    operations = [
        # 1. token: önce nullable ekle (mevcut satırlar için SQL DEFAULT gerekmez)
        migrations.AddField(
            model_name='device',
            name='token',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        # 2. Mevcut cihazların her birine benzersiz token ata
        migrations.RunPython(_assign_tokens, migrations.RunPython.noop),
        # 3. null kaldır — tüm satırlar artık dolu
        migrations.AlterField(
            model_name='device',
            name='token',
            field=models.CharField(max_length=64, unique=True),
        ),
        # 4. Alert: e-posta bildirim durumu
        migrations.AddField(
            model_name='alert',
            name='notified',
            field=models.BooleanField(default=False),
        ),
    ]
