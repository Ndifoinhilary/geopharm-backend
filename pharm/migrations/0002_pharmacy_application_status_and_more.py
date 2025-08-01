# Generated by Django 5.2.3 on 2025-07-03 22:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharm', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='pharmacy',
            name='application_status',
            field=models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', help_text='Status of the pharmacy application', max_length=20, verbose_name='Application Status'),
        ),
        migrations.AddField(
            model_name='pharmacy',
            name='rejection_reason',
            field=models.TextField(blank=True, default='incomplete files provided or invalid information or pharmavy is not legal', help_text='Reason for rejecting the pharmacy application', verbose_name='Rejection Reason'),
        ),
    ]
