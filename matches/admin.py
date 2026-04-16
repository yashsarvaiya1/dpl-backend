# matches/admin.py

from django.contrib import admin
from .models import Team, Player, Match, MatchPosition

admin.site.register(Team)
admin.site.register(Player)
admin.site.register(Match)
admin.site.register(MatchPosition)
