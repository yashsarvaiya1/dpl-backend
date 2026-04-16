# accounts/views.py

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import User
from .serializers import (
    UserSerializer, CreateUserSerializer,
    CheckMobileSerializer, LoginSerializer,
    SetPasswordSerializer, LogoutSerializer,
)
from .permissions import IsSuperUser, IsAdminOrSuperUser


class AuthViewSet(viewsets.ViewSet):
    """
    Handles: check-mobile, login, set-password, logout
    """
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'], url_path='check-mobile')
    def check_mobile(self, request):
        serializer = CheckMobileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mobile_number = serializer.validated_data['mobile_number']

        try:
            user = User.objects.get(mobile_number=mobile_number)
            return Response({
                'exists': True,
                'has_password_set': user.has_password_set(),
                'is_active': user.is_active,
            })
        except User.DoesNotExist:
            return Response({'exists': False}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'], url_path='login')
    def login(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mobile_number = serializer.validated_data['mobile_number']
        password = serializer.validated_data['password']

        try:
            user = User.objects.get(mobile_number=mobile_number)
        except User.DoesNotExist:
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({'detail': 'Account is deactivated.'}, status=status.HTTP_403_FORBIDDEN)

        if not user.check_password(password):
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        })

    @action(detail=False, methods=['post'], url_path='set-password')
    def set_password(self, request):
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mobile_number = serializer.validated_data['mobile_number']
        password = serializer.validated_data['password']

        try:
            user = User.objects.get(mobile_number=mobile_number)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not user.is_active:
            return Response({'detail': 'Account is deactivated.'}, status=status.HTTP_403_FORBIDDEN)

        if user.has_password_set():
            return Response({'detail': 'Password already set. Use login.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save(update_fields=['password'])

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        })

    @action(detail=False, methods=['post'], url_path='logout', permission_classes=[IsAuthenticated])
    def logout(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data['refresh'])
            token.blacklist()
            return Response({'detail': 'Logged out successfully.'})
        except TokenError:
            return Response({'detail': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)


class UserViewSet(viewsets.ModelViewSet):
    """
    Handles: CRUD for users + clear-password + deactivate
    """
    queryset = User.objects.all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_staff', 'is_active', 'is_superuser']
    search_fields = ['username', 'mobile_number']
    ordering_fields = ['created_at', 'username', 'tickets']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAdminOrSuperUser()]
        if self.action == 'create':
            return [IsAdminOrSuperUser()]
        if self.action in ['update', 'partial_update', 'destroy', 'clear_password', 'deactivate']:
            return [IsAdminOrSuperUser()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return CreateUserSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        requesting_user = request.user
        is_staff_requested = request.data.get('is_staff', False)

        # Admin cannot create other admins
        if not requesting_user.is_superuser and is_staff_requested:
            return Response(
                {'detail': 'You do not have permission to create admin users.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        requesting_user = request.user

        # Soft delete only
        if instance.is_superuser:
            return Response({'detail': 'Superuser cannot be deleted.'}, status=status.HTTP_403_FORBIDDEN)

        # Admin cannot delete other admins
        if not requesting_user.is_superuser and instance.is_staff:
            return Response({'detail': 'You do not have permission to delete admin users.'}, status=status.HTTP_403_FORBIDDEN)

        instance.soft_delete()
        return Response({'detail': 'User deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='clear-password')
    def clear_password(self, request, pk=None):
        instance = self.get_object()
        requesting_user = request.user

        if instance.is_superuser:
            return Response({'detail': 'Cannot clear superuser password.'}, status=status.HTTP_403_FORBIDDEN)

        # Admin cannot clear password of other admins
        if not requesting_user.is_superuser and instance.is_staff:
            return Response({'detail': 'You do not have permission to clear admin password.'}, status=status.HTTP_403_FORBIDDEN)

        instance.set_unusable_password()
        instance.save(update_fields=['password'])
        return Response({'detail': 'Password cleared. User must set a new password on next login.'})

    @action(detail=True, methods=['post'], url_path='deactivate')
    def deactivate(self, request, pk=None):
        instance = self.get_object()
        requesting_user = request.user

        if instance.is_superuser:
            return Response({'detail': 'Cannot deactivate superuser.'}, status=status.HTTP_403_FORBIDDEN)

        # Admin cannot deactivate other admins
        if not requesting_user.is_superuser and instance.is_staff:
            return Response({'detail': 'You do not have permission to deactivate admin users.'}, status=status.HTTP_403_FORBIDDEN)

        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response({'detail': 'User deactivated successfully.'})

    @action(detail=True, methods=['post'], url_path='activate')
    def activate(self, request, pk=None):
        instance = self.get_object()
        requesting_user = request.user

        if not requesting_user.is_superuser and instance.is_staff:
            return Response({'detail': 'You do not have permission to activate admin users.'}, status=status.HTTP_403_FORBIDDEN)

        instance.is_active = True
        instance.save(update_fields=['is_active'])
        return Response({'detail': 'User activated successfully.'})
