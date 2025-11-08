# backend/api/views.py
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from .serializers import RegisterSerializer, LoginSerializer, PinLoginSerializer, ProfileSerializer
from .utils import is_valid_transaction_pin
@api_view(['POST'])
def register_view(request):
    """Register new user and create profile."""
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        data = serializer.validated_data
        username = data['username']
        email = data['email']
        password = data['password']
        pin = data['pin']

        if User.objects.filter(username=username).exists():
            return Response({"error": "Username already exists."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(username=username, email=email, password=password)
        profile = user.profile
        profile.set_pin(pin)
        profile.save()

        return Response(
            {"message": "Registered successfully! Please login to continue."},
            status=status.HTTP_201_CREATED
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def login_view(request):
    """Login using username/password."""
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        data = serializer.validated_data
        user = authenticate(username=data['username'], password=data['password'])
        if user:
            profile = user.profile
            profile.pin_enabled = True
            profile.save()
            token, _ = Token.objects.get_or_create(user=user)
            prof_ser = ProfileSerializer(profile)
            return Response({
                "message": "Login successful.",
                "token": token.key,
                "profile": prof_ser.data
            })
        return Response({"error": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def pin_login_view(request):
    """Login using PIN."""
    serializer = PinLoginSerializer(data=request.data)
    if serializer.is_valid():
        data = serializer.validated_data
        try:
            user = User.objects.get(username=data['username'])
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        profile = user.profile
        if not profile.pin_enabled:
            return Response({"error": "PIN login not enabled yet. Please login with password first."},
                            status=status.HTTP_403_FORBIDDEN)
        if profile.check_pin(data['pin']):
            token, _ = Token.objects.get_or_create(user=user)
            prof_ser = ProfileSerializer(profile)
            return Response({
                "message": "PIN login successful.",
                "token": token.key,
                "profile": prof_ser.data
            })
        return Response({"error": "Invalid PIN."}, status=status.HTTP_401_UNAUTHORIZED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Dashboard - protected view
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def account_view(request):
    """Return profile details for dashboard."""
    profile = request.user.profile
    ser = ProfileSerializer(profile)
    return Response(ser.data)

# backend/api/views.py
import random
import string
from django.utils import timezone

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .serializers import BankAccountSerializer
from .models import BankAccount

# Helper to generate a UPI id (simple format): <username>.<bankabbr><random4>@gapy
def generate_upi_id(username: str, bank_name: str):
    uname = ''.join(ch for ch in username.lower() if ch.isalnum())[:12]
    bankabbr = ''.join(ch for ch in bank_name.lower() if ch.isalpha())[:4]
    rand = ''.join(random.choices(string.digits, k=4))
    candidate = f"{uname}.{bankabbr}{rand}@gapy"
    # ensure uniqueness; if collision add timestamp
    if BankAccount.objects.filter(upi_id=candidate).exists():
        candidate = f"{uname}.{bankabbr}{rand}{int(timezone.now().timestamp())}@gapy"
    return candidate

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.response import Response
import re
@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def banks_view(request):
    """
    GET:
      - if no query params: list user's bank accounts
      - if ?account_number=... (optionally &bank_name=...), return that account (with balance/amount)
    POST:
      - add a new bank account (generate upi_id server-side)
      - if same account_number already linked for this user, return the existing record (HTTP 200)
    """
    user = request.user
    
    if request.method == 'GET':
        acc_num = request.query_params.get('account_number')
        bank_name = request.query_params.get('bank_name')
        if acc_num:
            # find that account for this user only
            account = BankAccount.objects.filter(user=user, account_number=acc_num)
            if not account:
                return Response(
                    {"detail": "Account not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
            # decide what to return — full serialized object including balance
            ser = BankAccountSerializer(account)
            
            return Response(ser.data, status=status.HTTP_200_OK)

        # default: list all accounts for user (existing behaviour)
        qs = BankAccount.objects.filter(user=user).order_by('-created_at')
        ser = BankAccountSerializer(qs, many=True)
        return Response(ser.data)

    # POST - create
    acc_num = request.data.get('account_number')
    if acc_num:
        existing = BankAccount.objects.filter(user=user, account_number=acc_num)
        if existing:
            # Return existing record instead of creating duplicate
            existing_ser = BankAccountSerializer(existing)
            return Response({
                "message": "This account is already linked to your profile.",
                "bank": existing_ser.data
            }, status=status.HTTP_200_OK)

    ser = BankAccountSerializer(data=request.data, context={'request': request})
    if ser.is_valid():
        upi = generate_upi_id(user.username, ser.validated_data['bank_name'])
        pin=request.data.get('pin')
        account = BankAccount.objects.create(
            user=user,
            holder_name=ser.validated_data['holder_name'],
            bank_name=ser.validated_data['bank_name'],
            branch=ser.validated_data.get('branch', ''),
            account_number=ser.validated_data['account_number'],
            ifsc=ser.validated_data['ifsc'],
            mobile=ser.validated_data.get('mobile', ''),
            upi_id=upi
        )
        # Validate: must be exactly 4–6 digits
        if not re.fullmatch(r"\d{4,6}", pin):
            return Response(
            {"error": "PIN must be 4–6 digits and cannot contain letters or symbols."},
            status=400
        )
        account.set_pin(pin)
        print('coming2')

        out = BankAccountSerializer(account).data
        return Response(out, status=status.HTTP_201_CREATED)

    return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)



from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from .models import BankAccount

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def balance(request):
    """
    POST: Check balance for a given bank name and account number
    Example payload: {"bank_name": "State Bank of India", "account_number": "1234567890"}
    """
    bank_name = request.data.get("bank_name")
    account_number = request.data.get("account_number")

    if not bank_name or not account_number:
        return Response({"error": "Missing bank_name or account_number"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        account = BankAccount.objects.get(
            user=request.user,
            bank_name__iexact=bank_name.strip(),
            account_number=account_number.strip()
        )
        return Response({
            "bank_name": account.bank_name,
            "account_number": account.account_number,
            "amount": account.amount,
            "upi_id": account.upi_id
        }, status=status.HTTP_200_OK)
    except BankAccount.DoesNotExist:
        return Response({"error": "Account not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_balance_view(request):
    """
    POST: Add dummy money to user's account
    Body: { "amount": 500 }
    """
    profile = Profile.objects.get(user=request.user)
    try:
        amount = float(request.data.get('amount', 0))
    except ValueError:
        return Response({"error": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST)

    if amount <= 0:
        return Response({"error": "Amount must be positive"}, status=status.HTTP_400_BAD_REQUEST)

    profile.balance += amount
    profile.save()
    return Response({
        "message": f"₹{amount} added successfully",
        "new_balance": str(profile.balance)
    }, status=status.HTTP_200_OK)



# pay anyone
# views.py (append to your existing file)
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.contrib.auth.models import User

from .models import Payee, SavedPayee, Transaction, Profile
from .serializers import PayeeSerializer, SavedPayeeSerializer, TransactionSerializer

# SEARCH payees by name/phone/upi
@api_view(["GET"])
def search_payees(request):
    
    q = request.GET.get("q", "").strip()
    print(q)
    if not q:
        return Response([], status=status.HTTP_200_OK)
    matches = BankAccount.objects.filter(
        Q(holder_name__icontains=q) | Q(mobile__icontains=q) | Q(upi_id__icontains=q)
    )[:50]
    serializer = BankAccountSerializer(matches, many=True)
    return Response(serializer.data)

# ADD payee into user's saved list
@api_view(["POST"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_saved_payee(request):
    user = request.user
    payee_id = request.data.get("payee_id")
    if not payee_id:
        return Response({"detail": "payee_id required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        payee = Payee.objects.get(id=payee_id)
    except Payee.DoesNotExist:
        return Response({"detail": "payee not found"}, status=status.HTTP_404_NOT_FOUND)
    saved, created = SavedPayee.objects.get_or_create(owner=user, payee=payee)
    serializer = SavedPayeeSerializer(saved)
    return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

# LIST saved payees
@api_view(["GET"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def list_saved_payees(request):
    user = request.user
    qs = SavedPayee.objects.filter(owner=user).select_related("payee")
    serializer = SavedPayeeSerializer(qs, many=True)
    return Response(serializer.data)

#from decimal import Decimal, InvalidOperation
from django.db import transaction as db_transaction
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.response import Response
from rest_framework import status

from decimal import Decimal, InvalidOperation
from django.db import transaction as db_transaction
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.response import Response
from rest_framework import status

from .models import BankAccount, Transaction
from .serializers import TransactionSerializer


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def make_transaction(request):
    """
    Expects JSON:
      {
        "payee_id": <receiver_bank_account_id>,
        "amount": "100.00",
        "pin": "1234",
        "reference": "optional message"
      }

    Flow:
    1. Verify transaction PIN.
    2. Get current user’s BankAccount (sender).
    3. Get receiver BankAccount (payee_id).
    4. Debit sender's account, credit receiver's account.
    5. Create Transaction record.
    """
    user = request.user
 
    print(request.data)

    payee_id = request.data.get("payee_id")
    id = request.data.get("id")
    amount = request.data.get("amount")
    pin = request.data.get("pin")
    reference = request.data.get("reference", "")


    # Parse amount safely
    try:
        amount_dec = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return Response({"detail": "Invalid amount format"}, status=status.HTTP_400_BAD_REQUEST)
    if amount_dec <= 0:
        return Response({"detail": "Amount must be positive"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        sender_account = BankAccount.objects.select_for_update().get(
        id=id,
        user=request.user  # optional, for security
    )
    except BankAccount.DoesNotExist:
        return Response(
        {"error": "Bank account not found."},
        status=status.HTTP_404_NOT_FOUND
    )
    if not check_password(str(pin), sender_account.pin_hash):
        return Response({'valid': False, 'detail': 'Invalid PIN'}, status=status.HTTP_403_FORBIDDEN)


    # Get receiver’s bank account (payee)
    try:
        receiver_account = BankAccount.objects.select_for_update().get(id=payee_id)
    except BankAccount.DoesNotExist:
        return Response({"detail": "Receiver account not found"}, status=status.HTTP_404_NOT_FOUND)
    print(sender_account)
    print(receiver_account)

    # Prevent sending to same account
    if sender_account.id == receiver_account.id:
        return Response({"detail": "Cannot send money to the same account"}, status=status.HTTP_400_BAD_REQUEST)

    # Perform debit + credit atomically
    with db_transaction.atomic():
        sender_balance = Decimal(str(sender_account.amount or 0))
        receiver_balance = Decimal(str(receiver_account.amount or 0))

        # Check balance
        if sender_balance < amount_dec:
            txn = Transaction.objects.create(
                sender_account=sender_account,
                receiver_account=receiver_account,
                amount=amount_dec,
                status="FAILED",
                reference=reference
            )
            serializer = TransactionSerializer(txn)
            return Response(
                {"detail": "Insufficient balance", "transaction": serializer.data},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Debit sender, credit receiver
        sender_account.amount = sender_balance - amount_dec
        receiver_account.amount = receiver_balance + amount_dec

        sender_account.save()
        receiver_account.save()

        # Record transaction
        txn = Transaction.objects.create(
            sender_account=sender_account,
            receiver_account=receiver_account,
            amount=amount_dec,
            status="SUCCESS",
            reference=reference
        )

    serializer = TransactionSerializer(txn)
    return Response({"detail": "Transaction successful", "transaction": serializer.data},
                    status=status.HTTP_201_CREATED)


from django.db.models import Q
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.response import Response
from .models import BankAccount, Transaction
from .serializers import TransactionSerializer

@api_view(["GET"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def list_transactions(request):
    user = request.user

    # optional filters
    month = request.GET.get("month")
    year = request.GET.get("year")

    # get all bank accounts that belong to this user
    accounts = BankAccount.objects.filter(user=user)

    # if user has no linked accounts, return empty list
    if not accounts.exists():
        return Response([])

    # fetch transactions where user is sender OR receiver
    qs = Transaction.objects.filter(
        Q(sender_account__in=accounts) | Q(receiver_account__in=accounts)
    ).order_by("-timestamp")

    # apply optional date filters
    if year:
        qs = qs.filter(timestamp__year=year)
    if month:
        qs = qs.filter(timestamp__month=month)

    serializer = TransactionSerializer(qs, many=True, context={"request": request})
    print(serializer.data)
    return Response(serializer.data)


# bank transfer
# views.py additions
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q

from .models import BankAccount, Payee, SavedPayee
from .serializers import BankAccountSerializer, SavedPayeeSerializer

@api_view(["POST"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def search_bank_account(request):
    print("✅ search_bank_account called!")  # For debugging purposes
    acct = (request.data.get("account_number") or "").strip()
    ifsc = (request.data.get("ifsc") or "").strip()

    if not acct or not ifsc:
        return Response({"detail": "account_number and ifsc required"}, status=status.HTTP_400_BAD_REQUEST)

    qs = BankAccount.objects.filter(
        Q(account_number__icontains=acct),
        Q(ifsc__iexact=ifsc)
    )[:30]
    serializer = BankAccountSerializer(qs, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)



@api_view(["POST"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_bank_as_saved(request):
    """
    Create a Payee row (if not exists) from a BankAccount and add to SavedPayee for the user.
    POST { "bank_account_id": <id> }
    """
    user = request.user
    bank_id = request.data.get("bank_account_id")
    if not bank_id:
        return Response({"detail": "bank_account_id required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        bank = BankAccount.objects.get(id=bank_id)
    except BankAccount.DoesNotExist:
        return Response({"detail": "bank account not found"}, status=status.HTTP_404_NOT_FOUND)

    # create or get Payee from this bank (link by upi or account number)
    payee, created = Payee.objects.get_or_create(
        upi_id=bank.upi_id or None,
        defaults={
            "name": bank.holder_name,
            "phone": bank.mobile or "",
            "email": bank.email or "",
            "upi_id": bank.upi_id or "",
        }
    )
    saved, created2 = SavedPayee.objects.get_or_create(owner=user, payee=payee)
    serializer = SavedPayeeSerializer(saved)
    return Response(serializer.data, status=status.HTTP_201_CREATED if created2 else status.HTTP_200_OK)


# qr
# api/views.py (append these)
import qrcode
from io import BytesIO
from django.http import HttpResponse, JsonResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.response import Response
from rest_framework import status
from .models import BankAccount
from .serializers import BankAccountSerializer

@api_view(["GET"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def my_qr_image(request):
    """
    Returns a PNG image of a QR code that encodes a simple URL payload
    that the scanner can decode. Payload example:
      gapy://bank?bank_id=123
    """
    user = request.user
    # find a bank account for the user (pick first)
    print('hey')
    bank = BankAccount.objects.filter(holder_name__icontains=user.username).first()
    print('hey')
    print(bank.id)
    print(bank.holder_name)

    payload = f"gapy://bank?bank_id={bank.id}&name={bank.holder_name}"
    qr = qrcode.QRCode(box_size=8, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return HttpResponse(buffer.getvalue(), content_type="image/png")

@api_view(["GET"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def bank_account_detail(request, pk):
    """
    Get bank account info (used by scanner after decoding bank_id).
    """

    try:
        b = BankAccount.objects.get(id=pk)
    except BankAccount.DoesNotExist:
        return Response({"detail": "Bank account not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = BankAccountSerializer(b)
    return Response(serializer.data)


# recharge
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Operator, Plan, MobileRecharge
from .serializers import OperatorSerializer, PlanSerializer, MobileRechargeSerializer
import uuid
import time

@api_view(["GET"])
def operators_list(request):
    qs = Operator.objects.all()
    serializer = OperatorSerializer(qs, many=True)
    return Response(serializer.data)

@api_view(["GET"])
def plans_list(request):
    operator = request.GET.get("operator")
    circle = request.GET.get("circle")
    rech_type = request.GET.get("type", "prepaid")
    if not operator:
        return Response({"plans":{}}, status=status.HTTP_200_OK)
    ops = Operator.objects.filter(code=operator).first()
    if not ops:
        return Response({"plans":{}}, status=status.HTTP_200_OK)
    qs = Plan.objects.filter(operator=ops)
    # optionally filter by category/type via query param
    grouped = {}
    for p in qs:
        grouped.setdefault(p.category, []).append(PlanSerializer(p).data)
    return Response({"plans": grouped})

import time, uuid
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import Operator, Plan, MobileRecharge, BankAccount, Transaction


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_recharge(request):
    """
    Create a recharge record, debit user's account, and log a transaction.
    """
    user = request.user
    data = request.data
    id=data.get("bank_id")
    mobile = data.get("mobile")
    operator_code = data.get("operator")
    circle = data.get("circle")
    plan_id = data.get("plan_id")
    amount = data.get("amount")
    pin=data.get("pin")
    print('cominghere')
    # Validation
    if not mobile or not operator_code or not amount:
        return Response(
            {"status": "ERROR", "message": "Missing fields"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        amount = Decimal(amount)
    except ValueError:
        return Response(
            {"status": "ERROR", "message": "Invalid amount"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Find operator
    op = Operator.objects.filter(code=operator_code).first()
    if not op:
        return Response(
            {"status": "ERROR", "message": "Invalid operator"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Find plan if provided
    plan = None
    if plan_id:
        try:
            plan = Plan.objects.get(id=plan_id)
        except Plan.DoesNotExist:
            plan = None
    print(id)
    # Get user's first linked bank account (sender)
    try:
        sender_account = BankAccount.objects.select_for_update().get(
        id=id,
        user=request.user  # optional, for security
    )
    except BankAccount.DoesNotExist:
        return Response(
        {"error": "Bank account not found."},
        status=status.HTTP_404_NOT_FOUND
    )
    print(sender_account.bank_name)
    if not check_password(str(pin), sender_account.pin_hash):
        return Response({'valid': False, 'detail': 'Invalid PIN Provided'}, status=status.HTTP_403_FORBIDDEN)


    # Check sufficient balance
    if sender_account.amount < amount:
        return Response(
            {"status": "ERROR", "message": "Insufficient balance"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create pending recharge record
    rec = MobileRecharge.objects.create(
        user=user,
        mobile=mobile,
        operator=op,
        circle=circle or "",
        plan=plan,
        amount=amount,
        status="PENDING",
    )

    # Deduct amount (simulate immediate debit)
    sender_account.amount -= amount
    sender_account.save()

    # Simulate provider recharge delay
    time.sleep(0.8)
    provider_txn = f"MOCK-{uuid.uuid4().hex[:10]}"

    # Mark recharge success
    rec.provider_txn = provider_txn
    rec.status = "SUCCESS"
    rec.save()

    # Log transaction (Debited)
    Transaction.objects.create(
        sender_account=sender_account,
        receiver_name=f"{op.name} Recharge - {mobile}",
        amount=amount,
        status="SUCCESS",
        reference=f"Mobile Recharge ({op.name})"
    )

    return Response(
        {
            "status": "SUCCESS",
            "txn_id": provider_txn,
            "message": f"Recharge successful for {mobile}",
            "recharge_id": rec.id,
            "debited_from": sender_account.bank_name,
            "remaining_balance": sender_account.amount,
        },
        status=status.HTTP_200_OK,
    )


# bill payments
# api/views.py (append)
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from decimal import Decimal
import uuid, datetime, time

from .models import Biller, BillPayment, Transaction, BankAccount
from .serializers import BillerSerializer, BillPaymentSerializer

@api_view(["GET"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def billers_list(request):
    """
    List billers. Optional query param ?category=electricity
    """
    category = request.GET.get("category")
    qs = Biller.objects.all()
    if category:
        qs = qs.filter(category=category)
    data = BillerSerializer(qs, many=True).data
    return Response(data)

@api_view(["POST"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def fetch_bill(request):
    """
    Mock fetch bill details for the given consumer_number + biller_code.
    Returns sample amount, due_date, name, period.
    """
    biller_code = request.data.get("biller_code")
    consumer = request.data.get("consumer_number")
    if not biller_code or not consumer:
        return Response({"detail":"Missing fields"}, status=status.HTTP_400_BAD_REQUEST)
    biller = Biller.objects.filter(code=biller_code).first()
    if not biller:
        return Response({"detail":"Biller not found"}, status=status.HTTP_404_NOT_FOUND)

    # MOCK: create plausible bill data
    # Amount generation: deterministic-ish using consumer substring to show variety
    seed = sum([ord(c) for c in consumer[-4:]]) if len(consumer) >= 4 else len(consumer)*7
    amount = Decimal( (50 + (seed % 100)) ).quantize(Decimal("0.01"))  # 50..149.00
    due_date = datetime.date.today() + datetime.timedelta(days=7)
    name_on_bill = f"{request.user.get_full_name() or request.user.username}"
    period = f"{(datetime.date.today() - datetime.timedelta(days=30)).strftime('%b %Y')}"

    resp = {
        "biller": {"code": biller.code, "name": biller.name, "id": biller.id},
        "consumer_number": consumer,
        "name_on_bill": name_on_bill,
        "period": period,
        "amount": str(amount),
        "due_date": due_date.isoformat()
    }
    return Response({"status":"SUCCESS","bill":resp})

@api_view(["POST"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def pay_bill(request):
    """
    Pay a bill (mock): expects biller_code, consumer_number, amount, pin, reminder(optional)
    - Deducts from user's first linked BankAccount
    - Creates BillPayment and Transaction (receiver_account null, receiver_name = biller + consumer)
    """
    user = request.user
    data = request.data
    id=data.get("bank_id")
    biller_code = data.get("biller_code")
    consumer = data.get("consumer_number")
    amount = data.get("amount")
    pin = data.get("pin")
    reminder_date = data.get("reminder_date")  # optional yyyy-mm-dd

    if not biller_code or not consumer or not amount or not pin:
        return Response({"status":"ERROR","message":"Missing fields"}, status=status.HTTP_400_BAD_REQUEST)

    biller = Biller.objects.filter(code=biller_code).first()
    if not biller:
        return Response({"status":"ERROR","message":"Unknown biller"}, status=status.HTTP_400_BAD_REQUEST)

    # find user's bank account (first linked) - adapt if you support multiple
    try:
        sender_account = BankAccount.objects.select_for_update().get(
        id=id,
        user=request.user  # optional, for security
    )
    except BankAccount.DoesNotExist:
        return Response(
        {"error": "Bank account not found."},
        status=status.HTTP_404_NOT_FOUND
    )
    if not check_password(str(pin), sender_account.pin_hash):
        return Response({'valid': False, 'detail': 'Invalid PIN'}, status=status.HTTP_403_FORBIDDEN)

    try:
        amt = Decimal(str(amount))
    except Exception:
        return Response({"status":"ERROR","message":"Invalid amount"}, status=status.HTTP_400_BAD_REQUEST)
    print("DEBUG USER:", request.user.username)
    print("DEBUG ACCOUNT:", sender_account.id, sender_account.holder_name, sender_account.amount)
    print("DEBUG AMOUNT:", amount)
    if sender_account.amount < amt:
        return Response({"status":"ERROR","message":"Insufficient balance"}, status=status.HTTP_400_BAD_REQUEST)

    # Create pending billpayment
    bp = BillPayment.objects.create(
        user=user, biller=biller, consumer_number=consumer,
        amount=amt, status="PENDING", due_date=datetime.date.today()+datetime.timedelta(days=7)
    )

    # Deduct immediately from user's account (mock)
    sender_account.amount -= amt
    sender_account.save()

    # Simulate provider call
    time.sleep(0.6)  # small delay to mimic external call

    provider_txn = f"MOCK-BILL-{uuid.uuid4().hex[:10]}"
    bp.provider_txn = provider_txn
    bp.status = "SUCCESS"
    bp.paid_on = datetime.datetime.utcnow()
    if reminder_date:
        try:
            bp.reminder_date = datetime.date.fromisoformat(reminder_date)
        except Exception:
            bp.reminder_date = None
    bp.save()

    # Create Transaction record (receiver_account is NULL)
    Transaction.objects.create(
        sender_account=sender_account,
        receiver_account=None,
        receiver_name=f"{biller.name} - {consumer}",
        amount=amt,
        status="SUCCESS",
        reference=f"Bill Payment ({biller.name})"
    )

    # return bill payment & updated balance for frontend
    return Response({
        "status":"SUCCESS",
        "message":"Bill paid",
        "provider_txn": provider_txn,
        "billpayment": BillPaymentSerializer(bp).data,
        "remaining_balance": str(sender_account.amount)
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def bill_history(request):
    qs = BillPayment.objects.filter(user=request.user).order_by("-created_at")
    data = BillPaymentSerializer(qs, many=True).data
    return Response(data)


# transaction stats
# --- append at bottom of api/views.py (imports near top may already exist) ---
from django.db.models import Sum, Q
from django.db.models.functions import TruncMonth
from decimal import Decimal
import calendar
import datetime

@api_view(["GET"])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def transactions_stats(request):
    """
    Returns summary and monthly trend for the current user.
    Response JSON:
    {
      "total_debited": "123.45",
      "total_credited": "67.00",
      "net_change": "-56.45",
      "pie": {"debited": "123.45", "credited": "67.00"},
      "monthly": [
         {"month":"2025-06","label":"Jun 2025","debited":"100.00","credited":"50.00"},
         ...
      ]
    }
    Optional query params:
      - months=6   (how many months in trend; default 6)
    """
    user = request.user
    months = 6
    try:
        months = int(request.GET.get("months", months))
        if months <= 0:
            months = 6
    except Exception:
        months = 6

    # get all accounts for user
    accounts = BankAccount.objects.filter(user=user)
    if not accounts.exists():
        # no accounts -> zeroed response
        zero = Decimal("0.00")
        return Response({
            "total_debited": str(zero),
            "total_credited": str(zero),
            "net_change": str(zero),
            "pie": {"debited": str(zero), "credited": str(zero)},
            "monthly": []
        })

    # totals (only consider SUCCESS transactions for totals)
    total_debited = Transaction.objects.filter(
        sender_account__in=accounts,
        status="SUCCESS"
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    total_credited = Transaction.objects.filter(
        receiver_account__in=accounts,
        status="SUCCESS"
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    net_change = (total_credited - total_debited)

    # build monthly trend for last N months (including current)
    today = datetime.date.today()
    # create list of month starts (year, month) descending
    months_list = []
    y = today.year
    m = today.month
    for i in range(months):
        # compute year/month working backwards
        months_list.append((y, m))
        # decrement month
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    # reverse to chronological ascending (oldest first)
    months_list.reverse()

    # get aggregated values per month using TruncMonth for the date range
    first_year, first_month = months_list[0]
    start_date = datetime.date(first_year, first_month, 1)
    # end_date = end of last month in months_list
    last_year, last_month = months_list[-1]
    last_day = calendar.monthrange(last_year, last_month)[1]
    end_date = datetime.date(last_year, last_month, last_day)

    qs = Transaction.objects.filter(
        Q(sender_account__in=accounts) | Q(receiver_account__in=accounts),
        timestamp__date__gte=start_date,
        timestamp__date__lte=end_date,
        status="SUCCESS"
    ).annotate(month=TruncMonth("timestamp")).values("month").annotate(
        debited=Sum("amount", filter=Q(sender_account__in=accounts, status="SUCCESS")),
        credited=Sum("amount", filter=Q(receiver_account__in=accounts, status="SUCCESS"))
    ).order_by("month")

    # convert qs to dict keyed by YYYY-MM
    month_map = {}
    for row in qs:
        key = row["month"].strftime("%Y-%m")
        month_map[key] = {
            "debited": str( (row.get("debited") or Decimal("0.00")) ),
            "credited": str( (row.get("credited") or Decimal("0.00")) )
        }

    monthly = []
    for (yy, mm) in months_list:
        key = f"{yy}-{mm:02d}"
        label = f"{calendar.month_abbr[mm]} {yy}"
        vals = month_map.get(key, {"debited": str(Decimal("0.00")), "credited": str(Decimal("0.00"))})
        monthly.append({
            "month": key,
            "label": label,
            "debited": vals["debited"],
            "credited": vals["credited"]
        })

    resp = {
        "total_debited": str(total_debited),
        "total_credited": str(total_credited),
        "net_change": str(net_change),
        "pie": {
            "debited": str(total_debited),
            "credited": str(total_credited)
        },
        "monthly": monthly
    }
    return Response(resp)


# profilefrom django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password, make_password
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils.timezone import localtime
from .models import Profile, BankAccount  # import your models


# -----------------------------------------------
# GET Profile Info
# -----------------------------------------------
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def profile_info(request):
    user = request.user
    try:
        profile = Profile.objects.get(user=user)
        banks_count = BankAccount.objects.filter(user=user).count() if BankAccount.objects.filter(user=user).exists() else 0

        data = {
            "username": user.username,
            "email": user.email,
            "joined": localtime(user.date_joined).strftime("%d %b %Y"),
            "banks_count": banks_count,
            "balance": float(profile.balance),
            "pin_enabled": profile.pin_enabled,
        }
        return Response(data)
    except Profile.DoesNotExist:
        return Response({"error": "Profile not found"}, status=404)


# -----------------------------------------------
# POST Change Password
# -----------------------------------------------
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def change_password(request):
    user = request.user
    old_password = request.data.get("old_password")
    new_password = request.data.get("new_password")

    if not old_password or not new_password:
        return Response({"error": "Both old and new passwords are required"}, status=400)

    if not user.check_password(old_password):
        return Response({"error": "Old password is incorrect"}, status=400)

    user.password = make_password(new_password)
    user.save()
    return Response({"message": "Password updated successfully"})


# -----------------------------------------------
# POST Change Login PIN (Profile.pin_hash)
# -----------------------------------------------
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def change_pin(request):
    user = request.user
    old_pin = request.data.get("old_pin")
    new_pin = request.data.get("new_pin")

    if not old_pin or not new_pin:
        return Response({"error": "Both old and new PINs are required"}, status=400)
    if len(new_pin) != 4:
        return Response({"error": "PIN must be 4 digits"}, status=400)

    try:
        profile = Profile.objects.get(user=user)
    except Profile.DoesNotExist:
        return Response({"error": "Profile not found"}, status=404)

    # Verify existing PIN
    if not profile.check_pin(old_pin):
        return Response({"error": "Old PIN is incorrect"}, status=400)

    # Set new PIN
    profile.set_pin(new_pin)
    profile.pin_enabled = True
    profile.save()

    return Response({"message": "PIN updated successfully"})


# api/views.py  (append these imports at top if not present)
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.utils.timezone import localtime

from .models import Profile, BankAccount
from .serializers import ProfileSerializer, BankAccountSerializer
# Profile detail / update (GET, PATCH) at /api/profile/
@api_view(['GET', 'PATCH'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def profile_detail(request):
    """
    GET: return detailed profile + user fields (for frontend display)
    PATCH: partial update of user fields (first_name, last_name, email)
           and optionally profile fields if needed.
    """
    user = request.user
    try:
        profile = Profile.objects.get(user=user)
    except Profile.DoesNotExist:
        return Response({"detail": "Profile not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        # Compose a reasonably complete response (user + profile)
        prof_ser = ProfileSerializer(profile, context={'request': request})
        # include some user fields for convenience
        data = prof_ser.data
        data.update({
            "username": user.username,
            "email": user.email,
            "joined": localtime(user.date_joined).strftime("%d %b %Y"),
        })
        return Response(data, status=status.HTTP_200_OK)

    # PATCH — allow partial updates to user and profile
    if request.method == 'PATCH':
        payload = request.data or {}
        changed = False

        # Update User fields (first_name, last_name, email)
        first_name = payload.get('first_name')
        last_name = payload.get('last_name')
        email = payload.get('email')
        if first_name is not None:
            user.first_name = first_name.strip()
            changed = True
        if last_name is not None:
            user.last_name = last_name.strip()
            changed = True
        if email is not None:
            user.email = email.strip()
            changed = True

        if changed:
            user.save()

        # If you want to permit other profile updates in future, you can handle them here.
        # For now we only update user fields to match frontend usage (first_name/last_name).

        prof_ser = ProfileSerializer(profile, context={'request': request})
        out = prof_ser.data
        out.update({
            "username": user.username,
            "email": user.email,
            "joined": localtime(user.date_joined).strftime("%d %b %Y"),
        })
        return Response(out, status=status.HTTP_200_OK)
# Bank detail / delete (GET, DELETE) at /api/banks/<pk>/
@api_view(['GET', 'DELETE'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def bank_detail(request, pk):
    """
    GET  -> return single bank account detail (includes amount, upi_id etc.)
    DELETE -> unlink (delete) a bank account **only if it belongs to requesting user**
    """
    user = request.user
    try:
        bank = BankAccount.objects.get(pk=pk)
    except BankAccount.DoesNotExist:
        return Response({"detail": "Bank account not found"}, status=status.HTTP_404_NOT_FOUND)

    # Ensure the bank belongs to the requesting user
    if bank.user_id != user.id:
        return Response({"detail": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        ser = BankAccountSerializer(bank, context={'request': request})
        return Response(ser.data, status=status.HTTP_200_OK)

    if request.method == 'DELETE':
        bank.delete()
        return Response({"detail": "Bank account removed"}, status=status.HTTP_204_NO_CONTENT)
def get_user_bank_account(user):
    # This example chooses the first account. Change as needed.
    return BankAccount.objects.filter(user=user)
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def pin_status(request):
    account = get_user_bank_account(request.user)
    if account is None:
        return Response({"detail": "No bank account."}, status=status.HTTP_404_NOT_FOUND)
    return Response({"pin_enabled": account.pin_enabled})
from .serializers import SetPinSerializer, VerifyPinSerializer

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def set_pin(request):
    serializer = SetPinSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    account = get_user_bank_account(request.user)
    if account is None:
        return Response({"detail": "No bank account found."}, status=status.HTTP_404_NOT_FOUND)

    # If pin already enabled, deny or allow update depending on requirements.
    if account.pin_enabled:
        return Response({"detail": "PIN is already set."}, status=status.HTTP_400_BAD_REQUEST)

    pin = serializer.validated_data['pin']
    account.set_pin(pin)
    return Response({"detail": "PIN set successfully."}, status=status.HTTP_200_OK)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def verify_pin(request):
    id = request.data.get('payload', {}).get('id')
    pin = request.data.get('payload', {}).get('pin')
    print(id)
    print(pin)
    try:
        account = BankAccount.objects.get(id=id, user=request.user)
    except BankAccount.DoesNotExist:
        return Response({"error": "Account not found"}, status=404)
    serializer = VerifyPinSerializer(data={"pin": pin})

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    pin = serializer.validated_data['pin']
    if account.check_pin(pin):
        return Response({"verified": True})
    else:
        return Response({"verified": False}, status=status.HTTP_400_BAD_REQUEST)
    



