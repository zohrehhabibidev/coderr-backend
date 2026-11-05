from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.generics import ListAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_app.models import Profile

from .serializers import (
    LoginSerializer,
    ProfileSerializer,
    RegistrationSerializer,
)


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
    """Retrieve by User ID; profile updates belong to a later card."""

    http_method_names = ['get', 'patch', 'options']
    queryset = Profile.objects.select_related("user")
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "user_id"
    lookup_url_kwarg = "pk"

    def patch(self, request, *args, **kwargs):
        """Keep the future PATCH route from enabling updates implicitly."""
        raise MethodNotAllowed("PATCH")


class BusinessProfileListView(ListAPIView):
    pass


class CustomerProfileListView(ListAPIView):
    pass
