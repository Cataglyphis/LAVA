# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard_app', '0019_auto_20150702_1529'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bundle',
            name='uploaded_on',
            field=models.DateTimeField(default=datetime.datetime.now, verbose_name='Uploaded on', editable=False),
            preserve_default=True,
        ),
    ]
