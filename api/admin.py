# backend/api/admin.py
from django.contrib import admin
from .models import Profile, BankAccount

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'pin_enabled')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('pin_hash',)

@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'bank_name', 'account_number', 'upi_id', 'amount', 'created_at')
    search_fields = ('user__username', 'account_number', 'upi_id')
    list_filter = ('bank_name',)
    fields = ('user','holder_name','bank_name','branch','account_number','ifsc','mobile','upi_id','amount','created_at')
    readonly_fields = ('upi_id','created_at')
