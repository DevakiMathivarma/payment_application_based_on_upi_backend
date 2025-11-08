# backend/api/models.py
from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
import uuid

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    pin_hash = models.CharField(max_length=128, blank=True)
    pin_enabled = models.BooleanField(default=False)   # becomes True after first credential login
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def set_pin(self, raw_pin):
        self.pin_hash = make_password(raw_pin)
        self.save()

    def check_pin(self, raw_pin):
        return check_password(raw_pin, self.pin_hash)

    def __str__(self):
        return f"Profile({self.user.username})"


# backend/api/models.py (BankAccount model section)
# backend/api/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from decimal import Decimal
from django.db import models

class BankAccount(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bank_accounts')
    holder_name = models.CharField(max_length=150)
    bank_name = models.CharField(max_length=120)
    branch = models.CharField(max_length=120, blank=True)
    account_number = models.CharField(max_length=34)
    ifsc = models.CharField(max_length=11)
    mobile = models.CharField(max_length=20, blank=True)
    upi_id = models.CharField(max_length=64, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))  # <-- new
     # --- PIN fields ---
    pin_hash = models.CharField(max_length=128, blank=True)
    pin_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user', 'account_number')
        indexes = [
            models.Index(fields=['user', 'account_number']),
        ]

    def __str__(self):
        return f"{self.bank_name} - {self.holder_name}"
    def set_pin(self, raw_pin):
        print('coming2')
        self.pin_hash = make_password(raw_pin)
        self.pin_enabled = True
        self.save(update_fields=['pin_hash', 'pin_enabled'])

    def check_pin(self, raw_pin):
        if not self.pin_hash:
            return False
        return check_password(raw_pin, self.pin_hash)



class Payee(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True, null=True)
    upi_id = models.CharField(max_length=64, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # optional: link to registered user
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="payee_user")

    def __str__(self):
        return f"{self.name} — {self.upi_id or self.phone or self.email}"

class SavedPayee(models.Model):
    """
    Payees saved by a user (their payee list).
    """
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_payees")
    payee = models.ForeignKey(Payee, on_delete=models.CASCADE, related_name="saved_by")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("owner", "payee")

    def __str__(self):
        return f"{self.owner.username} -> {self.payee.name}"

from django.db import models
from django.utils import timezone

class Transaction(models.Model):
    """
    Transaction log between two BankAccounts.
    """
    TXN_STATUS = (
        ("SUCCESS", "Success"),
        ("FAILED", "Failed"),
    )

    sender_account = models.ForeignKey(
        "BankAccount",
        on_delete=models.CASCADE,
        related_name="sent_transactions"
    )
    # Make receiver optional (can be NULL if it's an external entity)
    receiver_account = models.ForeignKey(
        "BankAccount",
        on_delete=models.CASCADE,
        related_name="received_transactions",
        blank=True,
        null=True
    )

    # For cases where receiver is not a BankAccount (e.g., mobile number, merchant name)
    receiver_name = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=3)
    timestamp = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=10, choices=TXN_STATUS, default="SUCCESS")
    reference = models.CharField(max_length=128, blank=True, null=True)

    def __str__(self):
        return f"{self.sender_account.holder_name} → {self.receiver_account.holder_name} : ₹{self.amount} ({self.status})"


# recharge
from django.db import models
from django.conf import settings

class Operator(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=120)
    logo = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.name

class Plan(models.Model):
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="plans")
    category = models.CharField(max_length=40)   # data / 5g / topup / unlimited
    plan_code = models.CharField(max_length=120, blank=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    title = models.CharField(max_length=200, blank=True)
    validity = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.operator.name} {self.title or self.plan_code} ₹{self.amount}"

class MobileRecharge(models.Model):
    STATUS_CHOICES = (("PENDING","PENDING"),("SUCCESS","SUCCESS"),("FAILED","FAILED"))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    mobile = models.CharField(max_length=15)
    operator = models.ForeignKey(Operator, on_delete=models.SET_NULL, null=True)
    circle = models.CharField(max_length=80, blank=True)
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    provider_txn = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# bill payments
# api/models.py (append these)
from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

class Biller(models.Model):
    CATEGORY_CHOICES = (
        ("electricity", "Electricity"),
        ("water", "Water"),
        ("postpaid", "Postpaid Mobile"),
        ("dth", "DTH"),
        ("broadband", "Broadband"),
        ("gas", "Gas"),
    )
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    logo = models.URLField(blank=True, null=True)
    circle = models.CharField(max_length=64, blank=True, null=True)  # optional region

    def __str__(self):
        return f"{self.name} ({self.category})"


class BillPayment(models.Model):
    STATUS = (("PENDING", "Pending"), ("SUCCESS", "Success"), ("FAILED", "Failed"))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    biller = models.ForeignKey(Biller, on_delete=models.PROTECT)
    consumer_number = models.CharField(max_length=128)
    name_on_bill = models.CharField(max_length=128, blank=True, null=True)
    period = models.CharField(max_length=64, blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    due_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS, default="PENDING")
    provider_txn = models.CharField(max_length=128, blank=True, null=True)
    paid_on = models.DateTimeField(blank=True, null=True)
    reminder_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} → {self.biller.name} : ₹{self.amount} ({self.status})"

    class Meta:
        ordering = ["-created_at"]
