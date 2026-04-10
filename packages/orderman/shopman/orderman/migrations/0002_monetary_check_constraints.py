"""
Add CheckConstraints for non-negative monetary fields (_q suffix).

Ensures Order.total_q, OrderItem.unit_price_q/line_total_q,
and SessionItem.unit_price_q/line_total_q cannot be negative.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orderman", "0001_initial"),
    ]

    operations = [
        # Order.total_q >= 0
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(total_q__gte=0),
                name="ord_order_total_q_non_negative",
            ),
        ),
        # OrderItem.unit_price_q >= 0
        migrations.AddConstraint(
            model_name="orderitem",
            constraint=models.CheckConstraint(
                condition=models.Q(unit_price_q__gte=0),
                name="ord_order_item_unit_price_q_non_negative",
            ),
        ),
        # OrderItem.line_total_q >= 0
        migrations.AddConstraint(
            model_name="orderitem",
            constraint=models.CheckConstraint(
                condition=models.Q(line_total_q__gte=0),
                name="ord_order_item_line_total_q_non_negative",
            ),
        ),
        # SessionItem.unit_price_q >= 0
        migrations.AddConstraint(
            model_name="sessionitem",
            constraint=models.CheckConstraint(
                condition=models.Q(unit_price_q__gte=0),
                name="ord_session_item_unit_price_q_non_negative",
            ),
        ),
        # SessionItem.line_total_q >= 0
        migrations.AddConstraint(
            model_name="sessionitem",
            constraint=models.CheckConstraint(
                condition=models.Q(line_total_q__gte=0),
                name="ord_session_item_line_total_q_non_negative",
            ),
        ),
    ]
