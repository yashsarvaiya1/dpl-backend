# matches/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Team, Player, Match, MatchPosition
from .serializers import (
    TeamSerializer, PlayerSerializer,
    MatchSerializer, MatchPositionSerializer
)
from .permissions import IsAdminOrSuperAdmin, IsAdminOrReadOnly
from bmatches.utils import sync_match_position_to_bmatches


class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['-created_at']

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlayerViewSet(viewsets.ModelViewSet):
    queryset = Player.objects.all()
    serializer_class = PlayerSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['team']
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['-created_at']

    # Hard delete for players — as per project rules
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MatchViewSet(viewsets.ModelViewSet):
    queryset = Match.objects.select_related('team_1', 'team_2').prefetch_related('positions')
    serializer_class = MatchSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['team_1', 'team_2', 'date']
    ordering_fields = ['date', 'start_time', 'created_at']
    ordering = ['-date']

    def perform_create(self, serializer):
        match = serializer.save()
        self._create_positions(match)

    def _create_positions(self, match):
        team1_slug = match.team_1.name.lower().replace(' ', '')[:6]
        team2_slug = match.team_2.name.lower().replace(' ', '')[:6]
        positions = []
        for i in range(1, 6):
            positions.append(MatchPosition(
                match=match,
                position_label=f"{team1_slug}-{i}"
            ))
            positions.append(MatchPosition(
                match=match,
                position_label=f"{team2_slug}-{i}"
            ))
        MatchPosition.objects.bulk_create(positions)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MatchPositionViewSet(viewsets.ModelViewSet):
    serializer_class = MatchPositionSerializer
    permission_classes = [IsAdminOrSuperAdmin]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['match']
    ordering = ['position_label']
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return MatchPosition.objects.select_related('player', 'match')

    def perform_update(self, serializer):
        old_instance = self.get_object()
        updated_fields = {}

        if 'player' in serializer.validated_data:
            updated_fields['player'] = serializer.validated_data['player']
        if 'score' in serializer.validated_data:
            updated_fields['score'] = serializer.validated_data['score']
        if 'is_no_player' in serializer.validated_data:
            updated_fields['is_no_player'] = serializer.validated_data['is_no_player']

        instance = serializer.save()

        # Surgical field-level sync to BMatchPositions
        if updated_fields:
            sync_match_position_to_bmatches(instance, updated_fields)
