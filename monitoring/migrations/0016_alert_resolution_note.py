from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0015_tag_device_tags_net_per_nic'),
    ]

    operations = [
        migrations.AddField(
            model_name='alert',
            name='resolution_note',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='alert',
            name='resolved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
