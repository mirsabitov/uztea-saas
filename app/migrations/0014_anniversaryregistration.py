from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('app', '0013_conferenceregistration_accepted_terms')]

    operations = [
        migrations.CreateModel(
            name='AnniversaryRegistration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=255)),
                ('phone_number', models.CharField(max_length=30)),
                ('email', models.EmailField(max_length=254)),
                ('membership_status', models.CharField(choices=[('yes', 'Yes'), ('not_yet', 'Not yet')], max_length=10)),
                ('event_communication', models.BooleanField(default=False)),
                ('future_updates', models.BooleanField(default=False)),
                ('photos_videos', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name': '30th anniversary registration',
                'verbose_name_plural': '30th anniversary registrations',
            },
        ),
    ]
