# bmatches/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction as db_transaction

from .models import BMatch, BMatchPosition, BRoom, BRoomEntry, TicketTransaction
from .serializers import (
    BMatchSerializer, BMatchPositionSerializer,
    BRoomSerializer, BRoomDetailSerializer,
    TicketTransactionSerializer
)
from .permissions import IsAdminOrReadOnly, IsBMatchCreatorOrSuperAdmin, IsAdminOrSuperAdmin
from .utils import (
    get_or_create_broom_for_user,
    get_random_box_for_broom,
    handle_bmatch_completed,
    handle_bmatch_cancelled
)
from matches.models import MatchPosition


class BMatchViewSet(viewsets.ModelViewSet):
    serializer_class = BMatchSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'status': ['exact'],
        'match': ['exact'],
        'created_by': ['exact'],
        'match__date': ['exact', 'gte', 'lte'],   # ← date filter on the match
    }
    search_fields = ['note', 'match__team_1__name', 'match__team_2__name']
    ordering_fields = ['created_at', 'ticket_amount', 'match__date']
    ordering = ['-created_at']

    def get_queryset(self):
        return BMatch.objects.select_related(
            'match__team_1', 'match__team_2', 'created_by'
        ).prefetch_related('positions')

    def get_permissions(self):
        if self.action in ['create']:
            return [IsAdminOrSuperAdmin()]
        if self.action in ['update', 'partial_update', 'destroy', 'change_status', 'override_position']:
            return [IsBMatchCreatorOrSuperAdmin()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        with db_transaction.atomic():
            bmatch = serializer.save(created_by=self.request.user)
            self._create_bmatch_positions(bmatch)

    def _create_bmatch_positions(self, bmatch):
        """
        Mirror MatchPositions into BMatchPositions at creation time.
        All fields null — will be filled by MatchPosition sync or admin override.
        """
        match_positions = MatchPosition.objects.filter(match=bmatch.match)
        bm_positions = [
            BMatchPosition(
                bmatch=bmatch,
                position_label=mp.position_label,
                player=mp.player,
                score=mp.score,
                is_no_player=mp.is_no_player
            )
            for mp in match_positions
        ]
        BMatchPosition.objects.bulk_create(bm_positions)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='change-status')
    def change_status(self, request, pk=None):
        bmatch = self.get_object()
        new_status = request.data.get('status')

        valid_statuses = [
            BMatch.STATUS_UPCOMING,
            BMatch.STATUS_ACTIVE,
            BMatch.STATUS_CLOSED,
            BMatch.STATUS_COMPLETED,
            BMatch.STATUS_CANCELLED,
        ]

        # Irreversible statuses
        irreversible = [BMatch.STATUS_COMPLETED, BMatch.STATUS_CANCELLED]

        if bmatch.status in irreversible:
            return Response(
                {"detail": f"Cannot change status. BMatch is already {bmatch.status}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_status not in valid_statuses:
            return Response(
                {"detail": f"Invalid status. Valid: {valid_statuses}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with db_transaction.atomic():
            bmatch.status = new_status
            bmatch.save(update_fields=['status'])

            if new_status == BMatch.STATUS_COMPLETED:
                handle_bmatch_completed(bmatch)
            elif new_status == BMatch.STATUS_CANCELLED:
                handle_bmatch_cancelled(bmatch)

        serializer = self.get_serializer(bmatch)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='positions')
    def positions(self, request, pk=None):
        bmatch = self.get_object()
        positions = bmatch.positions.select_related('player').all()
        serializer = BMatchPositionSerializer(positions, many=True)
        return Response(serializer.data)

    @action(
        detail=True, methods=['patch'],
        url_path='positions/(?P<pos_id>[^/.]+)',
        permission_classes=[IsBMatchCreatorOrSuperAdmin]
    )
    def override_position(self, request, pk=None, pos_id=None):
        bmatch = self.get_object()
        try:
            position = BMatchPosition.objects.get(pk=pos_id, bmatch=bmatch)
        except BMatchPosition.DoesNotExist:
            return Response(
                {"detail": "Position not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = BMatchPositionSerializer(
            position, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='open-box')
    def open_box(self, request, pk=None):
        bmatch = self.get_object()
        user = request.user

        if bmatch.status != BMatch.STATUS_ACTIVE:
            return Response(
                {"detail": "BMatch is not active. Cannot open a box."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if (user.tickets or 0) < (bmatch.ticket_amount or 0):
            return Response(
                {"detail": "Insufficient tickets."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with db_transaction.atomic():
            broom, _ = get_or_create_broom_for_user(bmatch, user)
            box_value = get_random_box_for_broom(broom)

            if not box_value:
                return Response(
                    {"detail": "No available boxes in this room."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create entry
            entry = BRoomEntry.objects.create(
                broom=broom,
                user=user,
                box_value=box_value
            )

            # Deduct tickets
            user.tickets = (user.tickets or 0) - bmatch.ticket_amount
            user.save(update_fields=['tickets'])

            # Create debit transaction
            TicketTransaction.objects.create(
                user=user,
                transaction_type=TicketTransaction.TYPE_DEBIT,
                amount=bmatch.ticket_amount,
                reason=TicketTransaction.REASON_BOX_OPEN,
                reference_bmatch=bmatch,
                reference_broom=broom
            )

            # If broom is now full → mark ongoing
            if broom.is_full:
                broom.status = BRoom.STATUS_ONGOING
                broom.save(update_fields=['status'])

        serializer = BRoomDetailSerializer(broom, context={'request': request})
        return Response({
            "box_value": box_value,
            "room": serializer.data,
            "tickets_remaining": user.tickets
        })

    @action(detail=True, methods=['get'], url_path='my-rooms')
    def my_rooms(self, request, pk=None):
        bmatch = self.get_object()
        rooms = BRoom.objects.filter(
            bmatch=bmatch,
            entries__user=request.user
        ).distinct().order_by('created_at')
        serializer = BRoomDetailSerializer(
            rooms, many=True, context={'request': request}
        )
        return Response(serializer.data)


class BRoomViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['bmatch', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        return BRoom.objects.filter(
            entries__user=self.request.user
        ).distinct().select_related('bmatch__match__team_1', 'bmatch__match__team_2')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return BRoomDetailSerializer
        return BRoomSerializer


class TicketTransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TicketTransactionSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['transaction_type', 'reason', 'user', 'reference_bmatch']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        if self.action == 'create':
            return [IsAdminOrSuperAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return TicketTransaction.objects.select_related(
                'user', 'reference_bmatch', 'reference_broom', 'created_by'
            )
        return TicketTransaction.objects.filter(user=user).select_related(
            'user', 'reference_bmatch', 'reference_broom'
        )

    def perform_create(self, serializer):
        """
        Creates a transaction record only.
        Ticket balance is managed exclusively by
        add-tickets / remove-tickets actions on UserViewSet.
        This endpoint is for superadmin manual record injection only.
        """
        serializer.save(created_by=self.request.user)
