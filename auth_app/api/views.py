from rest_framework.generics import ListAPIView, RetrieveUpdateAPIView
from rest_framework.views import APIView


class RegistrationView(APIView):
    pass


class LoginView(APIView):
    pass


class ProfileDetailView(RetrieveUpdateAPIView):
    http_method_names = ['get', 'patch', 'options']


class BusinessProfileListView(ListAPIView):
    pass


class CustomerProfileListView(ListAPIView):
    pass
