# matches/serializers.py

from rest_framework import serializers
from django.db import models
from .models import Team, Player, Match, MatchPosition


class PlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = ['id', 'name', 'team', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class TeamSerializer(serializers.ModelSerializer):
    players = PlayerSerializer(many=True, read_only=True)

    class Meta:
        model = Team
        fields = ['id', 'name', 'players', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class TeamMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['id', 'name']


class MatchPositionSerializer(serializers.ModelSerializer):
    player_name = serializers.CharField(source='player.name', read_only=True)

    class Meta:
        model = MatchPosition
        fields = [
            'id', 'position_label', 'player', 'player_name',
            'score', 'is_no_player', 'updated_at'
        ]
        read_only_fields = ['id', 'position_label', 'updated_at']

    def validate(self, attrs):
        match = self.instance.match if self.instance else None
        player = attrs.get('player')

        if player and match:
            # same player can't appear twice in same match
            qs = MatchPosition.objects.filter(
                match=match,
                player=player
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"player": "This player is already assigned to another position in this match."}
                )
        return attrs


class MatchSerializer(serializers.ModelSerializer):
    team_1_detail = TeamMinimalSerializer(source='team_1', read_only=True)
    team_2_detail = TeamMinimalSerializer(source='team_2', read_only=True)
    positions = MatchPositionSerializer(many=True, read_only=True)

    class Meta:
        model = Match
        fields = [
            'id', 'team_1', 'team_2', 'team_1_detail', 'team_2_detail',
            'date', 'start_time', 'end_time', 'positions',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        team_1 = attrs.get('team_1', getattr(self.instance, 'team_1', None))
        team_2 = attrs.get('team_2', getattr(self.instance, 'team_2', None))
        date = attrs.get('date', getattr(self.instance, 'date', None))

        if team_1 and team_2 and team_1 == team_2:
            raise serializers.ValidationError(
                {"team_2": "A match cannot have the same team twice."}
            )

        if team_1 and team_2 and date:
            # Check if either team already has a match on this date
            qs = Match.objects.filter(date=date).filter(
                models.Q(team_1=team_1) | models.Q(team_2=team_1) |
                models.Q(team_1=team_2) | models.Q(team_2=team_2)
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"date": "One or both teams already have a match on this date."}
                )
        return attrs
