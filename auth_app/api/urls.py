from django.urls import path

from .views import (
    RegistrationView,
    LoginView,
    ProfileDetailView,
    BusinessProfileListView,
    CustomerProfileListView,
)

urlpatterns = [
    path('registration/', RegistrationView.as_view(), name='registration'),
    path('login/', LoginView.as_view(), name='login'),
    path(
        'profile/<int:pk>/', ProfileDetailView.as_view(),
        name='profile-detail',
    ),
    path(
        'profiles/business/', BusinessProfileListView.as_view(),
        name='business-profiles',
    ),
    path(
        'profiles/customer/', CustomerProfileListView.as_view(),
        name='customer-profiles',
    ),
]
