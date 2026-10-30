from django.contrib import admin
from .models import Conversation, ConversationMember, Message, Attachment, MessageRead, MessageReaction
for m in (Conversation, ConversationMember, Message, Attachment, MessageRead, MessageReaction):
    admin.site.register(m)
