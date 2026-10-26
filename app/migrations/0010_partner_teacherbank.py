from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('app', '0009_membership_is_pending_payment'),
    ]

    operations = [
        migrations.CreateModel(
            name='Partner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(blank=True, max_length=255, null=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('phone_number', models.CharField(blank=True, max_length=50, null=True)),
                ('position', models.CharField(blank=True, max_length=255, null=True)),
                ('company_name', models.CharField(blank=True, max_length=255, null=True)),
                ('country', models.CharField(blank=True, max_length=100, null=True)),
                ('source', models.CharField(blank=True, max_length=255, null=True)),
            ],
            options={
                'verbose_name': 'Partner',
                'verbose_name_plural': 'Partners List',
                'ordering': ('full_name', 'id'),
            },
        ),
        migrations.CreateModel(
            name='TeacherBank',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(blank=True, max_length=255, null=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('phone_number', models.CharField(blank=True, max_length=50, null=True)),
                ('source', models.CharField(blank=True, max_length=255, null=True)),
            ],
            options={
                'verbose_name': 'Teacher Bank Entry',
                'verbose_name_plural': 'Teachers Bank',
                'ordering': ('full_name', 'id'),
            },
        ),
    ]
