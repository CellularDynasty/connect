from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, UserProfile, BlockedUser


class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ("email_verified",)
    list_filter = UserAdmin.list_filter + ("email_verified",)
    fieldsets = UserAdmin.fieldsets + (("Email verification", {"fields": ("email_verified",)}),)


admin.site.register(User, CustomUserAdmin)
admin.site.register(UserProfile)
admin.site.register(BlockedUser)
