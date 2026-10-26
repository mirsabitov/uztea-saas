from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('app', '0006_dynamic_membership_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='membership',
            name='is_pending_payment',
            field=models.BooleanField(
                db_index=True,
                default=False,
                editable=False,
                help_text='Controls whether this application is shown in the Pending Payment admin section.',
            ),
        ),
        migrations.CreateModel(
            name='PendingPayment',
            fields=[],
            options={
                'verbose_name': 'Pending Payment',
                'verbose_name_plural': 'Pending Payments',
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('app.membership',),
        ),
    ]
