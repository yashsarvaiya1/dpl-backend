# bmatches/utils.py

import random
from django.db import transaction as db_transaction


def sync_match_position_to_bmatches(match_position_instance, updated_fields: dict):
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
    Must be called inside transaction.atomic().
    Locks BRoom rows to prevent two users landing in same slot.
    """
    from .models import BRoom, BRoomEntry

    # Lock all active/ongoing brooms for this bmatch
    existing_brooms = BRoom.objects.select_for_update().filter(
        bmatch=bmatch,
        status__in=[BRoom.STATUS_ACTIVE, BRoom.STATUS_ONGOING]
    ).order_by('created_at')

    for broom in existing_brooms:
        # Re-count entries under the lock — NOT is_full property (uses cached count)
        entry_count = BRoomEntry.objects.filter(broom=broom).count()
        user_already_in = BRoomEntry.objects.filter(broom=broom, user=user).exists()
        if not user_already_in and entry_count < 10:
            return broom, False

    new_broom = BRoom.objects.create(bmatch=bmatch)
    return new_broom, True


def get_random_box_for_broom(broom):
    """
    Must be called inside transaction.atomic().
    Locks BRoomEntry rows to prevent duplicate box assignment.
    """
    from .models import BRoomEntry
    from matches.models import MatchPosition

    # Lock all existing entries for this broom
    claimed_boxes = list(
        BRoomEntry.objects.select_for_update().filter(
            broom=broom
        ).values_list('box_value', flat=True)
    )

    all_positions = list(
        MatchPosition.objects.filter(
            match=broom.bmatch.match
        ).values_list('position_label', flat=True)
    )

    available = [p for p in all_positions if p not in claimed_boxes]

    if not available:
        return None

    return random.choice(available)


def _build_effective_score_map(bmatch):
    """
    Returns {position_label: score} using BMatchPosition overrides first,
    falling back to MatchPosition. Single query each — no N+1.
    """
    from .models import BMatchPosition
    from matches.models import MatchPosition

    # Base scores from MatchPosition
    score_map = {
        mp.position_label: mp.score or 0
        for mp in MatchPosition.objects.filter(match=bmatch.match)
    }

    # Override with BMatchPosition scores where they exist
    for bp in BMatchPosition.objects.filter(bmatch=bmatch):
        if bp.score is not None:
            score_map[bp.position_label] = bp.score

    return score_map


def process_broom_completion(broom):
    """
    Called when bmatch → completed and broom is full (ongoing).
    Finds winner(s), creates win_reward transactions, updates user tickets.
    Splits pot equally among tied winners, remainder goes to first winner.
    """
    from .models import BRoomEntry, TicketTransaction, BRoom

    entries = list(BRoomEntry.objects.filter(broom=broom).select_related('user'))

    if not entries:
        return

    ticket_amount = broom.bmatch.ticket_amount or 0
    total_pot = ticket_amount * len(entries)   # full pot = all entries
    win_amount = ticket_amount * 9             # 9x entry fee (1 kept as platform fee)

    score_map = _build_effective_score_map(broom.bmatch)

    entry_scores = [
        (entry, score_map.get(entry.box_value, 0))
        for entry in entries
    ]

    if not entry_scores:
        return

    max_score = max(score for _, score in entry_scores)
    winners = [entry for entry, score in entry_scores if score == max_score]

    per_winner = win_amount // len(winners)
    remainder = win_amount % len(winners)

    with db_transaction.atomic():
        users_to_update = []
        for i, winner_entry in enumerate(winners):
            payout = per_winner + (remainder if i == 0 else 0)
            TicketTransaction.objects.create(
                user=winner_entry.user,
                transaction_type=TicketTransaction.TYPE_CREDIT,
                amount=payout,
                reason=TicketTransaction.REASON_WIN_REWARD,
                reference_bmatch=broom.bmatch,
                reference_broom=broom
            )
            winner_entry.user.tickets = (winner_entry.user.tickets or 0) + payout
            users_to_update.append(winner_entry.user)

        # Bulk update all winners at once
        if users_to_update:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            User.objects.bulk_update(users_to_update, ['tickets'])

        broom.status = BRoom.STATUS_COMPLETED
        broom.save(update_fields=['status'])


def process_broom_cancellation(broom):
    """
    Cancels a broom and refunds all participants.
    Uses bulk_update for efficiency.
    """
    from .models import BRoomEntry, TicketTransaction, BRoom

    entries = list(BRoomEntry.objects.filter(broom=broom).select_related('user'))
    ticket_amount = broom.bmatch.ticket_amount or 0

    with db_transaction.atomic():
        users_to_update = []
        for entry in entries:
            TicketTransaction.objects.create(
                user=entry.user,
                transaction_type=TicketTransaction.TYPE_CREDIT,
                amount=ticket_amount,
                reason=TicketTransaction.REASON_REFUND,
                reference_bmatch=broom.bmatch,
                reference_broom=broom
            )
            entry.user.tickets = (entry.user.tickets or 0) + ticket_amount
            users_to_update.append(entry.user)

        if users_to_update:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            User.objects.bulk_update(users_to_update, ['tickets'])

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
