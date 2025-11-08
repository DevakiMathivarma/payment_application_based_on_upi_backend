# api/migrations/0009_create_transaction_model.py
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

class Migration(migrations.Migration):

    initial = False

    dependencies = [
        ('api', '0001_initial'),  # <-- REPLACE this with your last migration (e.g. '0003_auto_2025...'), keep quotes
    ]

    operations = [
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('timestamp', models.DateTimeField(default=django.utils.timezone.now)),
                ('status', models.CharField(choices=[('SUCCESS','Success'), ('FAILED','Failed')], default='SUCCESS', max_length=10)),
                ('reference', models.CharField(blank=True, max_length=128, null=True)),
                ('sender_account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sent_transactions', to='api.bankaccount')),
                ('receiver_account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='received_transactions', to='api.bankaccount')),
            ],
        ),
    ]
