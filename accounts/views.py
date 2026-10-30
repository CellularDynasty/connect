from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import UserProfile, BlockedUser
from .serializers import RegisterSerializer, UserSerializer, ProfileSerializer, BlockSerializer

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    queryset = User.objects.all()

class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/auth/me/ and /api/auth/profile/"""
    serializer_class = UserSerializer
    def get_object(self):
        return self.request.user

class ProfileView(APIView):
    def get(self, request):
        return Response(ProfileSerializer(request.user.profile).data)
    def patch(self, request):
        ser = ProfileSerializer(request.user.profile, data=request.data, partial=True)
        ser.is_valid(raise_exception=True); ser.save()
        return Response(ser.data)

class UserSearchView(generics.ListAPIView):
    serializer_class = UserSerializer
    def get_queryset(self):
        q = self.request.query_params.get("q", "").strip()
        qs = User.objects.exclude(id=self.request.user.id).select_related("profile")
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) |
                           Q(first_name__icontains=q) | Q(last_name__icontains=q))
        return qs.order_by("username")[:50]

class BlockView(APIView):
    def get(self, request):
        return Response(BlockSerializer(BlockedUser.objects.filter(blocker=request.user), many=True).data)
    def post(self, request):
        blocked_id = request.data.get("user_id")
        if not blocked_id or int(blocked_id) == request.user.id:
            return Response({"detail": "Invalid user_id"}, status=400)
        obj, _ = BlockedUser.objects.get_or_create(blocker=request.user, blocked_id=blocked_id)
        return Response(BlockSerializer(obj).data, status=status.HTTP_201_CREATED)
    def delete(self, request):
        BlockedUser.objects.filter(blocker=request.user, blocked_id=request.data.get("user_id")).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
