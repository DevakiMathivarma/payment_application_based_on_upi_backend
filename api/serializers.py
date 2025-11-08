# backend/api/serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile,BankAccount

class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    pin = serializers.CharField(write_only=True, min_length=4, max_length=6)
    confirm_pin = serializers.CharField(write_only=True, min_length=4, max_length=6)

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        if data['pin'] != data['confirm_pin']:
            raise serializers.ValidationError("PINs do not match.")
        return data

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

class PinLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    pin = serializers.CharField(write_only=True, min_length=4, max_length=6)

class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Profile
        fields = ['username', 'email', 'pin_enabled', 'balance']
# backend/api/serializers.py

class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ['id', 'holder_name', 'bank_name', 'branch', 'account_number', 'ifsc', 'mobile', 'upi_id', 'created_at','amount']
        read_only_fields = ['upi_id', 'created_at','amount']

    def validate(self, data):
        # Basic checks
        acc = data.get('account_number', '')
        ifsc = data.get('ifsc', '')
        if len(acc) < 6:
            raise serializers.ValidationError("Account number seems too short.")
        if len(ifsc) != 11:
            raise serializers.ValidationError("IFSC should be 11 characters (e.g. ABCD0123456).")

        # If we have a request user, check duplicate
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            user = request.user
            # If updating an existing instance, skip check if same instance
            instance = getattr(self, 'instance', None)
            exists = BankAccount.objects.filter(user=user, account_number=acc)
            if instance:
                exists = exists.exclude(pk=instance.pk)
            if exists.exists():
                raise serializers.ValidationError("This account number is already linked to your profile.")
        return data


# serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile, Payee, SavedPayee, Transaction

class PayeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payee
        fields = ["id", "name", "phone", "upi_id", "email", "created_at"]

class SavedPayeeSerializer(serializers.ModelSerializer):
    payee = PayeeSerializer(read_only=True)
    payee_id = serializers.PrimaryKeyRelatedField(source="payee", write_only=True, queryset=Payee.objects.all())

    class Meta:
        model = SavedPayee
        fields = ["id", "owner", "payee", "payee_id", "added_at"]
        read_only_fields = ["owner", "added_at"]

class TransactionSerializer(serializers.ModelSerializer):
    sender_account = BankAccountSerializer(read_only=True)
    receiver_account = BankAccountSerializer(read_only=True)
    type = serializers.SerializerMethodField()
    class Meta:
        model = Transaction
        fields = [
            "id", "sender_account", "receiver_account",
            "amount", "timestamp", "status", "reference","type"
        ]
    def get_type(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        user = request.user
        user_accounts = BankAccount.objects.filter(user=user).values_list("id", flat=True)

        # if the user's account sent the transaction → Debited
        if obj.sender_account_id in user_accounts:
            return "Debited"
        # if the user's account received → Credited
        elif obj.receiver_account_id in user_accounts:
            return "Credited"
        return None

# recharge
from rest_framework import serializers
from .models import Operator, Plan, MobileRecharge

class OperatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Operator
        fields = ["id","code","name","logo"]

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id","category","plan_code","amount","title","validity","description"]

class MobileRechargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileRecharge
        fields = "__all__"


# bill payments
# api/serializers.py (append)
from rest_framework import serializers
from .models import Biller, BillPayment
from .models import Transaction  # existing

class BillerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Biller
        fields = ["id", "code", "name", "category", "logo", "circle"]


class BillPaymentSerializer(serializers.ModelSerializer):
    biller = BillerSerializer(read_only=True)
    type = serializers.SerializerMethodField()

    class Meta:
        model = BillPayment
        fields = [
            "id", "biller", "consumer_number", "name_on_bill", "period",
            "amount", "due_date", "status", "provider_txn", "paid_on",
            "reminder_date", "created_at", "type"
        ]

    def get_type(self, obj):
        # Convenience: treat as "Paid" or "Pending"
        if obj.status == "SUCCESS":
            return "Paid"
        if obj.status == "PENDING":
            return "Pending"
        return obj.status
# app/serializers.py
from rest_framework import serializers

class SetPinSerializer(serializers.Serializer):
    pin = serializers.CharField(min_length=4, max_length=8)
    confirm_pin = serializers.CharField(min_length=4, max_length=8)

    def validate(self, data):
        if data['pin'] != data['confirm_pin']:
            raise serializers.ValidationError("PIN and confirmation do not match.")
        # optionally validate numeric-only
        if not data['pin'].isdigit():
            raise serializers.ValidationError("PIN must contain only digits.")
        return data

class VerifyPinSerializer(serializers.Serializer):
    pin = serializers.CharField(min_length=4, max_length=8)
