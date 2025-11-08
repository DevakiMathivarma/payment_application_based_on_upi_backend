# backend/api/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('pin-login/', views.pin_login_view, name='pin_login'),
    path('account/', views.account_view, name='account'),
    path('banks/', views.banks_view, name='banks'),
    path('add-balance/', views.add_balance_view, name='add_balance'),
    path('balance/', views.balance, name='balance'), 
    path("payees/search/", views.search_payees, name="api_search_payees"),
    path("payees/add_saved/", views.add_saved_payee, name="api_add_saved_payee"),
    path("payees/list_saved/", views.list_saved_payees, name="api_list_saved_payees"),
    path("transactions/make/", views.make_transaction, name="api_make_transaction"),
    path("transactions/list/", views.list_transactions, name="api_list_transactions"),
    path("bank/search/", views.search_bank_account, name="api_bank_search"),
    path("bank/add_saved/", views.add_bank_as_saved, name="api_bank_add_saved"),

path("qr/myqr/", views.my_qr_image, name="api_my_qr"),
path("bank/<int:pk>/", views.bank_account_detail, name="api_bank_detail"),
path("operators/", views.operators_list, name="operators"),
  path("plans/", views.plans_list, name="plans"),
  path("recharge/", views.create_recharge, name="recharge"),

path("bill/billers/", views.billers_list, name="billers-list"),
    path("bill/fetch/", views.fetch_bill, name="bill-fetch"),
    path("bill/pay/", views.pay_bill, name="bill-pay"),
    path("bill/history/", views.bill_history, name="bill-history"),
    path("transactions/stats/", views.transactions_stats, name="transactions-stats"),

   path('profile/', views.profile_detail, name='api-profile-detail'),
    path('profile/info/', views.profile_info, name='api-profile-info'),  # keep existing if you use it
    path('profile/change-password/', views.change_password, name='api-change-password'),
    path('profile/change-pin/', views.change_pin, name='api-change-pin'),

    # banks: list/create (existing) -> /api/banks/
    # add bank detail / delete:
    path('banks/<int:pk>/', views.bank_detail, name='api-bank-detail'),
    path('bank/pin-status/', views.pin_status, name='pin-status'),
    path('bank/set-pin/', views.set_pin, name='set-pin'),
    path('bank/verify-pin/', views.verify_pin, name='verify-pin'),
    path('transactions/', views.list_transactions, name='transactions-list-alias'),

]
