# accounts/serializers.py

from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    has_password_set = serializers.SerializerMethodField()
    tickets = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'mobile_number', 'tickets',
            'is_staff', 'is_superuser', 'is_active',
            'has_password_set', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'has_password_set', 'tickets']

    def get_has_password_set(self, obj) -> bool:
        return obj.has_password_set()

    def get_tickets(self, obj) -> int:
        return obj.tickets or 0  # always int, never null


class CreateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'mobile_number', 'is_staff', 'is_active', 'tickets']
        read_only_fields = ['id']

    def validate_mobile_number(self, value):
        if User.objects.filter(mobile_number=value).exists():
            raise serializers.ValidationError("User with this mobile number already exists.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            mobile_number=validated_data['mobile_number'],
            username=validated_data.get('username'),
            is_staff=validated_data.get('is_staff', False),
            is_active=validated_data.get('is_active', True),
            tickets=validated_data.get('tickets', 0),
        )
        return user


class CheckMobileSerializer(serializers.Serializer):
    mobile_number = serializers.CharField(max_length=15)


class LoginSerializer(serializers.Serializer):
    mobile_number = serializers.CharField(max_length=15)
    password = serializers.CharField(write_only=True)


class SetPasswordSerializer(serializers.Serializer):
    mobile_number = serializers.CharField(max_length=15)
    password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True, min_length=6)

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
