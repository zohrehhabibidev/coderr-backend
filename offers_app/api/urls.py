from django.urls import path

from .views import (
    OfferListCreateView,
    OfferDetailView,
    OfferPackageDetailView,
)

urlpatterns = [
    path('offers/', OfferListCreateView.as_view(), name='offer-list'),
    path('offers/<int:pk>/', OfferDetailView.as_view(), name='offer-detail'),
    path(
        'offerdetails/<int:pk>/',
        OfferPackageDetailView.as_view(),
        name='offer-package-detail'
    ),
]
