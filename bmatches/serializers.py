# bmatches/serializers.py

from rest_framework import serializers
from .models import BMatch, BMatchPosition, BRoom, BRoomEntry, TicketTransaction
from matches.serializers import MatchSerializer, TeamMinimalSerializer
from matches.models import MatchPosition


class BMatchPositionSerializer(serializers.ModelSerializer):
    player_name = serializers.CharField(source='player.name', read_only=True)

    class Meta:
        model = BMatchPosition
        fields = [
            'id', 'position_label', 'player', 'player_name',
            'score', 'is_no_player', 'updated_at'
        ]
        read_only_fields = ['id', 'position_label', 'updated_at']

    def validate(self, attrs):
        bmatch = self.instance.bmatch if self.instance else None
        player = attrs.get('player')

        if player and bmatch:
            qs = BMatchPosition.objects.filter(bmatch=bmatch, player=player)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"player": "This player is already assigned to another position in this bmatch."}
                )
        return attrs


class BRoomEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = BRoomEntry
        fields = ['id', 'box_value', 'created_at']
        read_only_fields = ['id', 'box_value', 'created_at']


class BRoomSerializer(serializers.ModelSerializer):
    entry_count = serializers.IntegerField(read_only=True)
    my_entry = serializers.SerializerMethodField()

    class Meta:
        model = BRoom
        fields = ['id', 'status', 'entry_count', 'my_entry', 'created_at']
        read_only_fields = fields

    def get_my_entry(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        entry = obj.entries.filter(user=request.user).first()
        if entry:
            return BRoomEntrySerializer(entry).data
        return None


class BRoomDetailSerializer(serializers.ModelSerializer):
    entries_count = serializers.IntegerField(source='entry_count', read_only=True)
    my_entry = serializers.SerializerMethodField()
    positions = serializers.SerializerMethodField()

    class Meta:
        model = BRoom
        fields = [
            'id', 'bmatch', 'status',
            'entries_count', 'my_entry',
            'positions', 'created_at'
        ]
        read_only_fields = fields

    def get_my_entry(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        entry = obj.entries.filter(user=request.user).first()
        if entry:
            return BRoomEntrySerializer(entry).data
        return None

    def get_positions(self, obj):
        """
        Returns effective positions — BMatchPosition if exists, else MatchPosition.
        """
        from matches.models import MatchPosition

        match = obj.bmatch.match
        bmatch = obj.bmatch

        match_positions = MatchPosition.objects.filter(
            match=match
        ).select_related('player')

        bmatch_positions = {
            bp.position_label: bp
            for bp in BMatchPosition.objects.filter(
                bmatch=bmatch
            ).select_related('player')
        }

        result = []
        for mp in match_positions:
            bp = bmatch_positions.get(mp.position_label)
            result.append({
                'position_label': mp.position_label,
                'player_id': bp.player_id if bp else mp.player_id,
                'player_name': (bp.player.name if bp and bp.player else (mp.player.name if mp.player else None)),
                'score': bp.score if bp else mp.score,
                'is_no_player': bp.is_no_player if bp else mp.is_no_player,
            })
        return result


class BMatchSerializer(serializers.ModelSerializer):
    match_detail = MatchSerializer(source='match', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    positions = BMatchPositionSerializer(many=True, read_only=True)

    class Meta:
        model = BMatch
        fields = [
            'id', 'match', 'match_detail',
            'ticket_amount', 'note', 'status',
            'created_by', 'created_by_name',
            'positions', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_by_name', 'created_at', 'updated_at']


class TicketTransactionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    mobile_number = serializers.CharField(source='user.mobile_number', read_only=True)

    class Meta:
        model = TicketTransaction
        fields = [
            'id', 'user', 'username', 'mobile_number',
            'transaction_type', 'amount', 'reason',
            'reference_bmatch', 'reference_broom',
            'created_by', 'created_at'
        ]
        read_only_fields = [
            'id', 'created_at',
            'username', 'mobile_number'
        ]
