# accounts/models.py

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def create_user(self, mobile_number, password=None, **extra_fields):
        if not mobile_number:
            raise ValueError("Mobile number is required")
        user = self.model(mobile_number=mobile_number, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(mobile_number, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    username        = models.CharField(max_length=150, null=True, blank=True)
    mobile_number   = models.CharField(max_length=15, unique=True)
    tickets         = models.IntegerField(default=0, null=True, blank=True)
    is_staff        = models.BooleanField(default=False, null=True, blank=True)
    is_superuser    = models.BooleanField(default=False, null=True, blank=True)
    is_active       = models.BooleanField(default=True, null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at      = models.DateTimeField(auto_now=True, null=True, blank=True)
    deleted_at      = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'mobile_number'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = 'accounts_user'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.username or 'User'} ({self.mobile_number})"

    def has_password_set(self):
        return self.has_usable_password()

    def soft_delete(self):
        from django.utils import timezone
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save(update_fields=['deleted_at', 'is_active'])
