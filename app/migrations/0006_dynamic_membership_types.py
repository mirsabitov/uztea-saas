from django.db import migrations, models


DEFAULT_NAMES = {
    'basic': 'Basic Membership',
    'student': 'Student / Early Career / Retired',
    'teacher': 'Individual Teacher',
    'institutional': 'Institutional Membership',
}


def populate_names(apps, schema_editor):
    MembershipTypeConfig = apps.get_model('app', 'MembershipTypeConfig')
    for config in MembershipTypeConfig.objects.all():
        config.name = DEFAULT_NAMES.get(
            config.membership_type,
            config.membership_type.replace('-', ' ').replace('_', ' ').title(),
        )
        config.save(update_fields=['name'])


class Migration(migrations.Migration):
    dependencies = [
        ('app', '0005_membershiptypeconfig_membership_member_2_email_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='membershiptypeconfig',
            name='name',
            field=models.CharField(blank=True, max_length=120, verbose_name='Display name'),
        ),
        migrations.RunPython(populate_names, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='membershiptypeconfig',
            name='name',
            field=models.CharField(max_length=120, verbose_name='Display name'),
        ),
        migrations.AlterField(
            model_name='membershiptypeconfig',
            name='membership_type',
            field=models.SlugField(
                help_text='Unique code, for example: premium or corporate-plan.',
                max_length=50,
                unique=True,
                verbose_name='Code',
            ),
        ),
        migrations.AlterField(
            model_name='membershiptypeconfig',
            name='price',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=12,
                verbose_name='Price (UZS)',
            ),
        ),
        migrations.AlterField(
            model_name='membership',
            name='membership_type',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterModelOptions(
            name='membershiptypeconfig',
            options={
                'ordering': ['name'],
                'verbose_name': 'Membership Type',
                'verbose_name_plural': 'Membership Types',
            },
        ),
    ]
