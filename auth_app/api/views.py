from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer, RegistrationSerializer


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
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token = Token.objects.get_or_create(user=user)[0]
        return Response(
            self.get_response_data(user, token),
            status=status.HTTP_200_OK,
        )

    def get_response_data(self, user, token):
        return {
            "token": token.key,
            "username": user.username,
            "email": user.email,
            "user_id": user.id,
        }


class ProfileDetailView(RetrieveUpdateAPIView):
    http_method_names = ['get', 'patch', 'options']


class BusinessProfileListView(ListAPIView):
    pass


class CustomerProfileListView(ListAPIView):
    pass
