from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('app', '0010_partner_teacherbank')]

    operations = [
        migrations.CreateModel(
            name='ConferenceRegistration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=255)),
                ('email', models.EmailField(max_length=254)),
                ('job_title', models.CharField(max_length=255)),
                ('organization', models.CharField(max_length=255, verbose_name='university or company name')),
                ('country', models.CharField(max_length=100)),
                ('mobile_phone', models.CharField(max_length=30)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'TESOL conference registration',
                'verbose_name_plural': 'TESOL conference registrations',
            },
        ),
    ]
