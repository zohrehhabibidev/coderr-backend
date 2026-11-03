from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RegistrationSerializer


class RegistrationView(generics.CreateAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token = Token.objects.get(user=user)
        return Response(
            {
                "token": token.key,
                "username": user.username,
                "email": user.email,
                "user_id": user.id,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    pass


class ProfileDetailView(RetrieveUpdateAPIView):
    http_method_names = ['get', 'patch', 'options']


class BusinessProfileListView(ListAPIView):
    pass


class CustomerProfileListView(ListAPIView):
    pass
