# bmatches/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BMatchViewSet, BRoomViewSet, TicketTransactionViewSet

router = DefaultRouter()
router.register(r'transactions', TicketTransactionViewSet, basename='transaction')
router.register(r'rooms', BRoomViewSet, basename='broom')
router.register(r'', BMatchViewSet, basename='bmatch')

urlpatterns = [
    path('', include(router.urls)),
]
