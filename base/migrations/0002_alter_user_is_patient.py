# Generated by Django 5.2.3 on 2025-07-03 22:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='is_patient',
            field=models.BooleanField(default=True, help_text='Designates whether the user is a patient.', verbose_name='is patient'),
        ),
    ]
