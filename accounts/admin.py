from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, UserProfile, BlockedUser
admin.site.register(User, UserAdmin)
admin.site.register(UserProfile)
admin.site.register(BlockedUser)
