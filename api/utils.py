# app/utils.py
from django.contrib.auth.hashers import check_password
from .models import BankAccount

def is_valid_transaction_pin(user, pin):
    """
    Returns True if the given PIN is correct for the user's account.
    Returns False otherwise.
    """
    try:
        account = BankAccount.objects.filter(user=user).first()
    except BankAccount.DoesNotExist:
        return False

    if not account.pin_enabled or not account.pin_hash:
        return False

    if not pin:
        return False

    # ✅ Compare entered PIN with stored hash
    return check_password(pin, account.pin_hash)
