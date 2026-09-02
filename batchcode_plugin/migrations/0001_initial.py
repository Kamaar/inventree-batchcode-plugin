"""Initial migration for the BatchCodePlugin plugin."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Create the BatchCounter model."""

    initial = True

    dependencies = [('part', '__first__'), ('stock', '__first__')]

    operations = [
        migrations.CreateModel(
            name='BatchCounter',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'key',
                    models.CharField(
                        editable=False,
                        help_text='Encoded scope this counter applies to',
                        max_length=250,
                        unique=True,
                        verbose_name='Scope Key',
                    ),
                ),
                (
                    'value',
                    models.PositiveIntegerField(
                        default=0,
                        help_text='Last value issued for this scope',
                        verbose_name='Value',
                    ),
                ),
                (
                    'period',
                    models.CharField(
                        blank=True,
                        help_text='Reset period this counter belongs to (empty if never reset)',
                        max_length=16,
                        verbose_name='Period',
                    ),
                ),
                (
                    'updated',
                    models.DateTimeField(auto_now=True, verbose_name='Updated'),
                ),
                (
                    'location',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='+',
                        to='stock.stocklocation',
                        verbose_name='Location',
                    ),
                ),
                (
                    'part',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='+',
                        to='part.part',
                        verbose_name='Part',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Batch Counter',
                'verbose_name_plural': 'Batch Counters',
                'ordering': ['key'],
            },
        )
    ]
