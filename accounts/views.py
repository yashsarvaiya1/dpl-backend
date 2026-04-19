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
from bmatches.models import TicketTransaction
from .models import User
from .serializers import (
    UserSerializer, CreateUserSerializer,
    CheckMobileSerializer, LoginSerializer,
    SetPasswordSerializer, LogoutSerializer,
)
from .permissions import IsSuperUser, IsAdminOrSuperUser
from django.db import transaction as db_transaction
from django.db.models import Sum, Count, Q
from django.utils.timezone import now
from datetime import timedelta


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
    queryset = User.objects.all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_staff', 'is_active', 'is_superuser']
    search_fields = ['username', 'mobile_number']
    ordering_fields = ['created_at', 'username', 'tickets']
    ordering = ['-created_at']

    def get_permissions(self):
        # Any authenticated user can fetch their own profile
        if self.action == 'retrieve':
            return [IsAuthenticated()]
        # All other read/write requires admin
        if self.action in [
            'list', 'create', 'update', 'partial_update', 'destroy',
            'clear_password', 'deactivate', 'activate',
            'add_tickets', 'remove_tickets', 'dashboard',
        ]:
            return [IsAdminOrSuperUser()]
        return [IsAuthenticated()]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Normal users can ONLY fetch their own profile
        if not request.user.is_staff and not request.user.is_superuser:
            if instance.id != request.user.id:
                return Response(
                    {'detail': 'You can only view your own profile.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

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

    @action(detail=True, methods=['post'], url_path='add-tickets')
    def add_tickets(self, request, pk=None):
        user = self.get_object()
        amount = request.data.get('amount')

        if not amount or int(amount) <= 0:
            return Response(
                {"detail": "Amount must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST
            )

        amount = int(amount)

        with db_transaction.atomic():
            user.tickets = (user.tickets or 0) + amount
            user.save(update_fields=['tickets'])

            TicketTransaction.objects.create(
                user=user,
                transaction_type='credit',
                amount=amount,
                reason='admin_add',
                created_by=request.user
            )

        return Response({"detail": f"{amount} tickets added.", "tickets": user.tickets})


    @action(detail=True, methods=['post'], url_path='remove-tickets')
    def remove_tickets(self, request, pk=None):
        user = self.get_object()
        amount = request.data.get('amount')

        if not amount or int(amount) <= 0:
            return Response(
                {"detail": "Amount must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST
            )

        amount = int(amount)

        with db_transaction.atomic():
            user.tickets = max((user.tickets or 0) - amount, 0)
            user.save(update_fields=['tickets'])

            TicketTransaction.objects.create(
                user=user,
                transaction_type='debit',
                amount=amount,
                reason='admin_remove',
                created_by=request.user
            )

        return Response({"detail": f"{amount} tickets removed.", "tickets": user.tickets})

    @action(detail=False, methods=['get'], url_path='dashboard', permission_classes=[IsAdminOrSuperUser])
    def dashboard(self, request):
        from bmatches.models import BMatch, BRoom, TicketTransaction
        from bmatches.serializers import BMatchSerializer
        from django.db.models.functions import TruncDate
        from django.db.models import Value, IntegerField
        from django.db.models.functions import Coalesce

        today = now()
        month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        week_ago = today - timedelta(days=7)

        # ── Users ──────────────────────────────────────────────
        user_stats = User.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            new_this_month=Count('id', filter=Q(created_at__gte=month_start)),
        )

        # ── BMatches (use all_objects to avoid soft-delete manager issues) ──
        bmatch_stats = BMatch.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='active')),
            upcoming=Count('id', filter=Q(status='upcoming')),
            closed=Count('id', filter=Q(status='closed')),
            completed=Count('id', filter=Q(status='completed')),
            cancelled=Count('id', filter=Q(status='cancelled')),
        )

        # ── Rooms ──────────────────────────────────────────────
        room_stats = BRoom.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='active')),
            ongoing=Count('id', filter=Q(status='ongoing')),
            completed=Count('id', filter=Q(status='completed')),
            cancelled=Count('id', filter=Q(status='cancelled')),
        )

        # ── Tickets ────────────────────────────────────────────
        # Coalesce handles NULL from Sum when no rows exist
        ticket_stats = TicketTransaction.objects.aggregate(
            total_credited=Coalesce(
                Sum('amount', filter=Q(transaction_type='credit')),
                0, output_field=IntegerField()
            ),
            total_debited=Coalesce(
                Sum('amount', filter=Q(transaction_type='debit')),
                0, output_field=IntegerField()
            ),
        )

        # Sum of tickets across all active users — Coalesce handles NULL
        total_in_circulation = User.objects.aggregate(
            total=Coalesce(Sum('tickets'), 0, output_field=IntegerField())
        )['total']

        # ── Transactions last 7 days (chart data) ──────────────
        tx_last_7_days = (
            TicketTransaction.objects
            .filter(created_at__gte=week_ago)
            .annotate(day=TruncDate('created_at'))
            .values('day', 'transaction_type')
            .annotate(total=Coalesce(Sum('amount'), 0, output_field=IntegerField()))
            .order_by('day')
        )

        chart_map: dict = {}
        for row in tx_last_7_days:
            day_str = str(row['day'])
            if day_str not in chart_map:
                chart_map[day_str] = {'date': day_str, 'credit': 0, 'debit': 0}
            chart_map[day_str][row['transaction_type']] = row['total']

        chart_data = []
        for i in range(7):
            day = (week_ago + timedelta(days=i + 1)).strftime('%Y-%m-%d')
            chart_data.append(chart_map.get(day, {'date': day, 'credit': 0, 'debit': 0}))

        # ── Recent BMatches ────────────────────────────────────
        recent_bmatches = BMatch.objects.select_related(
            'match__team_1', 'match__team_2'
        ).order_by('-created_at')[:5]

        return Response({
            'users': user_stats,
            'bmatches': bmatch_stats,
            'rooms': room_stats,
            'tickets': {
                'total_in_circulation': total_in_circulation,
                'total_credited': ticket_stats['total_credited'],
                'total_debited': ticket_stats['total_debited'],
            },
            'chart': chart_data,
            'recent_bmatches': BMatchSerializer(
                recent_bmatches, many=True, context={'request': request}
            ).data,
        })
