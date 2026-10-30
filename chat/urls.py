from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ConversationViewSet, MessageViewSet, AttachmentUploadView

router = DefaultRouter()
router.register("conversations", ConversationViewSet, basename="conversations")
router.register("messages", MessageViewSet, basename="messages")
router.register("attachments", AttachmentUploadView, basename="attachments")

urlpatterns = [path("", include(router.urls))]
