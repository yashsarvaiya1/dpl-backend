# bmatches/admin.py

from django.contrib import admin
from .models import BMatch, BMatchPosition, BRoom, BRoomEntry, TicketTransaction

admin.site.register(BMatch)
admin.site.register(BMatchPosition)
admin.site.register(BRoom)
admin.site.register(BRoomEntry)
admin.site.register(TicketTransaction)
