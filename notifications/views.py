from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Notification
from .serializers import NotificationSerializer

class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

@api_view(["POST"])
def mark_read(request, pk):
    Notification.objects.filter(id=pk, recipient=request.user).update(is_read=True)
    return Response({"read": True})

@api_view(["POST"])
def mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return Response({"read": "all"})

@api_view(["GET"])
def unread_count(request):
    return Response({"unread": Notification.objects.filter(recipient=request.user, is_read=False).count()})
