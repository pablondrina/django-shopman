"""
Add CheckConstraints for positive monetary fields (_q suffix).

Ensures PaymentIntent.amount_q and PaymentTransaction.amount_q
are strictly positive (zero-value transactions are invalid).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payman", "0001_initial"),
    ]

    operations = [
        # PaymentIntent.amount_q > 0
        migrations.AddConstraint(
            model_name="paymentintent",
            constraint=models.CheckConstraint(
                condition=models.Q(amount_q__gt=0),
                name="pay_intent_amount_q_positive",
            ),
        ),
        # PaymentTransaction.amount_q > 0
        migrations.AddConstraint(
            model_name="paymenttransaction",
            constraint=models.CheckConstraint(
                condition=models.Q(amount_q__gt=0),
                name="pay_transaction_amount_q_positive",
            ),
        ),
    ]
