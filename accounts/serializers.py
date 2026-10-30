from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import UserProfile, BlockedUser

User = get_user_model()

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["display_name", "bio", "avatar", "is_online", "last_seen", "updated_at"]
        read_only_fields = ["is_online", "last_seen", "updated_at"]

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "profile", "date_joined"]
        read_only_fields = ["id", "date_joined"]

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "first_name", "last_name"]
    def create(self, validated_data):
        # create_user hashes the password securely - never store plaintext
        return User.objects.create_user(**validated_data)

class BlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlockedUser
        fields = ["id", "blocked", "created_at"]
