# bmatches/serializers.py

from rest_framework import serializers
from .models import BMatch, BMatchPosition, BRoom, BRoomEntry, TicketTransaction
from matches.models import Match, MatchPosition


# ── Inline match summary (avoids importing full MatchSerializer) ──────────────
class MatchSummarySerializer(serializers.ModelSerializer):
    team_1_name = serializers.CharField(source='team_1.name', read_only=True)
    team_2_name = serializers.CharField(source='team_2.name', read_only=True)

    class Meta:
        model = Match
        fields = ['id', 'team_1', 'team_1_name', 'team_2', 'team_2_name',
                  'date', 'start_time', 'end_time']


# ── BMatchPosition ─────────────────────────────────────────────────────────────
class BMatchPositionSerializer(serializers.ModelSerializer):
    player_name = serializers.CharField(source='player.name', read_only=True, default=None)

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


# ── BMatch ─────────────────────────────────────────────────────────────────────
class BMatchSerializer(serializers.ModelSerializer):
    # Use inline summary — not MatchSerializer to avoid circular imports
    match_detail = MatchSummarySerializer(source='match', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default=None)
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


# ── BRoomEntry ─────────────────────────────────────────────────────────────────
class BRoomEntrySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True, default=None)
    mobile_number = serializers.CharField(source='user.mobile_number', read_only=True, default=None)

    class Meta:
        model = BRoomEntry
        fields = ['id', 'user', 'username', 'mobile_number', 'box_value', 'created_at']
        read_only_fields = ['id', 'box_value', 'created_at']


# ── BRoom (list) ───────────────────────────────────────────────────────────────
class BRoomSerializer(serializers.ModelSerializer):
    entry_count = serializers.IntegerField(read_only=True)
    my_entry = serializers.SerializerMethodField()
    bmatch_detail = BMatchSerializer(source='bmatch', read_only=True)

    class Meta:
        model = BRoom
        fields = ['id', 'bmatch', 'bmatch_detail', 'status', 'entry_count', 'my_entry', 'created_at']
        read_only_fields = ['id', 'status', 'entry_count', 'created_at']

    def get_my_entry(self, obj) -> dict | None:
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        entry = obj.entries.filter(user=request.user).first()
        return BRoomEntrySerializer(entry).data if entry else None


# ── BRoom (detail) ─────────────────────────────────────────────────────────────
class BRoomDetailSerializer(serializers.ModelSerializer):
    entries_count = serializers.IntegerField(source='entry_count', read_only=True)
    my_entry = serializers.SerializerMethodField()
    positions = serializers.SerializerMethodField()
    bmatch_detail = BMatchSerializer(source='bmatch', read_only=True)
    is_winner = serializers.SerializerMethodField()

    class Meta:
        model = BRoom
        fields = [
            'id', 'bmatch', 'bmatch_detail', 'status',
            'entries_count', 'my_entry', 'positions',
            'is_winner', 'created_at'
        ]
        read_only_fields = ['id', 'status', 'entries_count', 'created_at']

    def get_my_entry(self, obj) -> dict | None:
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        entry = obj.entries.filter(user=request.user).first()
        return BRoomEntrySerializer(entry).data if entry else None

    def get_positions(self, obj) -> list:
        """
        Returns effective positions — BMatchPosition if exists, else MatchPosition.
        Ensures consistent structure always.
        """
        match = obj.bmatch.match
        bmatch = obj.bmatch

        match_positions = MatchPosition.objects.filter(
            match=match
        ).select_related('player').order_by('position_label')

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
                'player_name': (
                    bp.player.name if bp and bp.player
                    else (mp.player.name if mp.player else None)
                ),
                'score': bp.score if bp is not None else mp.score,
                'is_no_player': bp.is_no_player if bp is not None else mp.is_no_player,
            })
        return result

    def get_is_winner(self, obj) -> bool:
        """
        User wins if their box_value matches the position_label with the highest score.
        Only relevant when room is completed.
        """
        request = self.context.get('request')
        if not request or obj.status != BRoom.STATUS_COMPLETED:
            return False

        entry = obj.entries.filter(user=request.user).first()
        if not entry or not entry.box_value:
            return False

        # Get winning position labels (highest score, handles ties)
        positions = BMatchPosition.objects.filter(
            bmatch=obj.bmatch,
            score__isnull=False,
            is_no_player=False
        ).order_by('-score')

        if not positions.exists():
            return False

        top_score = positions.first().score
        winning_labels = set(
            positions.filter(score=top_score).values_list('position_label', flat=True)
        )

        return entry.box_value in winning_labels


# ── TicketTransaction ──────────────────────────────────────────────────────────
class TicketTransactionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True, default=None)
    mobile_number = serializers.CharField(source='user.mobile_number', read_only=True, default=None)
    # Always return int, never null
    amount = serializers.SerializerMethodField()

    class Meta:
        model = TicketTransaction
        fields = [
            'id', 'user', 'username', 'mobile_number',
            'transaction_type', 'amount', 'reason',
            'reference_bmatch', 'reference_broom',
            'created_by', 'created_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'username',
            'mobile_number', 'amount'
        ]

    def get_amount(self, obj) -> int:
        return obj.amount or 0
