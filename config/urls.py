# config/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('rest_framework.urls')),
    path('api/accounts/', include('accounts.urls')),
    path('api/matches/', include('matches.urls')),
    path('api/bmatches/', include('bmatches.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
