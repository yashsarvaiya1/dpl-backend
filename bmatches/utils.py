# bmatches/utils.py

import random
from django.db import transaction as db_transaction
from django.db.models import Q


def sync_match_position_to_bmatches(match_position_instance, updated_fields: dict):
    """
    Surgically sync only changed fields from MatchPosition
    to all BMatchPositions of bmatches linked to this match.
    """
    from .models import BMatchPosition

    qs = BMatchPosition.objects.filter(
        bmatch__match=match_position_instance.match,
        position_label=match_position_instance.position_label
    )

    if not qs.exists():
        return

    update_kwargs = {}
    if 'player' in updated_fields:
        update_kwargs['player'] = updated_fields['player']
    if 'score' in updated_fields:
        update_kwargs['score'] = updated_fields['score']
    if 'is_no_player' in updated_fields:
        update_kwargs['is_no_player'] = updated_fields['is_no_player']

    if update_kwargs:
        qs.update(**update_kwargs)


def get_or_create_broom_for_user(bmatch, user):
    """
    Lazy broom assignment logic:
    - Find first broom where user is NOT present AND broom is NOT full
    - If none found, create a new broom
    Returns: (broom, created: bool)
    """
    from .models import BRoom, BRoomEntry

    existing_brooms = BRoom.objects.filter(
        bmatch=bmatch,
        status__in=[BRoom.STATUS_ACTIVE, BRoom.STATUS_ONGOING]
    ).order_by('created_at')

    for broom in existing_brooms:
        user_already_in = BRoomEntry.objects.filter(broom=broom, user=user).exists()
        if not user_already_in and not broom.is_full:
            return broom, False

    # No suitable broom found — create new one
    new_broom = BRoom.objects.create(bmatch=bmatch)
    return new_broom, True


def get_random_box_for_broom(broom):
    """
    Returns a random unclaimed box_value from this broom.
    Box values are derived from the bmatch match's position_labels.
    """
    from .models import BRoomEntry
    from matches.models import MatchPosition

    all_positions = list(
        MatchPosition.objects.filter(
            match=broom.bmatch.match
        ).values_list('position_label', flat=True)
    )

    claimed_boxes = list(
        BRoomEntry.objects.filter(broom=broom).values_list('box_value', flat=True)
    )

    available = [p for p in all_positions if p not in claimed_boxes]

    if not available:
        return None

    return random.choice(available)


def process_broom_completion(broom):
    """
    Called when bmatch → completed and broom is full (ongoing).
    Finds winner(s), creates win transactions, updates broom status.
    """
    from .models import BRoomEntry, BMatchPosition, TicketTransaction, BRoom
    from matches.models import MatchPosition
    from django.conf import settings
    from django.contrib.auth import get_user_model

    User = get_user_model()
    entries = BRoomEntry.objects.filter(broom=broom).select_related('user')

    if not entries.exists():
        return

    ticket_amount = broom.bmatch.ticket_amount or 0
    win_amount = ticket_amount * 9

    # Build effective score map for each position_label
    def get_effective_score(position_label):
        # BMatchPosition overrides first
        try:
            bmp = BMatchPosition.objects.get(
                bmatch=broom.bmatch,
                position_label=position_label
            )
            return bmp.score or 0
        except BMatchPosition.DoesNotExist:
            pass
        # Fall back to MatchPosition
        try:
            mp = MatchPosition.objects.get(
                match=broom.bmatch.match,
                position_label=position_label
            )
            return mp.score or 0
        except MatchPosition.DoesNotExist:
            return 0

    # Map each entry to its effective score
    entry_scores = []
    for entry in entries:
        score = get_effective_score(entry.box_value)
        entry_scores.append((entry, score))

    if not entry_scores:
        return

    max_score = max(score for _, score in entry_scores)
    winners = [entry for entry, score in entry_scores if score == max_score]

    # Divide win amount equally among winners
    per_winner = win_amount // len(winners)
    remainder = win_amount % len(winners)

    with db_transaction.atomic():
        for i, winner_entry in enumerate(winners):
            payout = per_winner + (remainder if i == 0 else 0)
            # Credit winner
            TicketTransaction.objects.create(
                user=winner_entry.user,
                transaction_type=TicketTransaction.TYPE_CREDIT,
                amount=payout,
                reason=TicketTransaction.REASON_WIN_REWARD,
                reference_bmatch=broom.bmatch,
                reference_broom=broom
            )
            # Update user tickets
            winner_entry.user.tickets = (winner_entry.user.tickets or 0) + payout
            winner_entry.user.save(update_fields=['tickets'])

        broom.status = BRoom.STATUS_COMPLETED
        broom.save(update_fields=['status'])


def process_broom_cancellation(broom):
    """
    Cancels a broom and refunds all participants.
    """
    from .models import BRoomEntry, TicketTransaction, BRoom

    entries = BRoomEntry.objects.filter(broom=broom).select_related('user')
    ticket_amount = broom.bmatch.ticket_amount or 0

    with db_transaction.atomic():
        for entry in entries:
            # Refund ticket
            TicketTransaction.objects.create(
                user=entry.user,
                transaction_type=TicketTransaction.TYPE_CREDIT,
                amount=ticket_amount,
                reason=TicketTransaction.REASON_REFUND,
                reference_bmatch=broom.bmatch,
                reference_broom=broom
            )
            entry.user.tickets = (entry.user.tickets or 0) + ticket_amount
            entry.user.save(update_fields=['tickets'])

        broom.status = BRoom.STATUS_CANCELLED
        broom.save(update_fields=['status'])


def handle_bmatch_completed(bmatch):
    """
    On bmatch → completed:
    - Full brooms (ongoing) → process winners
    - Incomplete brooms (active) → cancel + refund
    """
    from .models import BRoom

    rooms = BRoom.objects.filter(
        bmatch=bmatch,
        status__in=[BRoom.STATUS_ACTIVE, BRoom.STATUS_ONGOING]
    )

    for broom in rooms:
        if broom.is_full:
            process_broom_completion(broom)
        else:
            process_broom_cancellation(broom)


def handle_bmatch_cancelled(bmatch):
    """
    On bmatch → cancelled:
    - All active/ongoing brooms → cancel + refund
    """
    from .models import BRoom

    rooms = BRoom.objects.filter(
        bmatch=bmatch,
        status__in=[BRoom.STATUS_ACTIVE, BRoom.STATUS_ONGOING]
    )

    for broom in rooms:
        process_broom_cancellation(broom)
