from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0016_alert_resolution_note'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='heartbeat_count',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
