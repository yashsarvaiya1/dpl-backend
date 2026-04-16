# accounts/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['mobile_number', 'username', 'tickets', 'is_staff', 'is_superuser', 'is_active', 'created_at']
    list_filter = ['is_staff', 'is_superuser', 'is_active']
    search_fields = ['mobile_number', 'username']
    ordering = ['-created_at']

    fieldsets = (
        (None, {'fields': ('mobile_number', 'password')}),
        ('Personal', {'fields': ('username', 'tickets')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        ('Dates', {'fields': ('created_at', 'updated_at', 'deleted_at')}),
    )
    readonly_fields = ['created_at', 'updated_at']

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('mobile_number', 'username', 'password1', 'password2', 'is_staff', 'is_superuser'),
        }),
    )
