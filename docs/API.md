# API Quick Reference (full interactive docs at /api/docs/)

## Auth — /api/auth/
- POST `register/` — {username, email, password}
- POST `login/` — returns {access, refresh} JWT
- POST `refresh/`, POST `logout/` (blacklists refresh token)
- GET/PATCH `me/`, GET/PATCH `profile/` (multipart for avatar)
- GET `users/search/?q=aniket`
- GET/POST/DELETE `block/` — {user_id}

## Chat — /api/chat/
- GET/POST `conversations/` — POST {type:"private", member_ids:[2]} or {type:"group", title:"Team", member_ids:[2,3]}
- POST `conversations/{id}/add_member/` {user_id} — group admins only
- POST `conversations/{id}/remove_member/` {user_id} — group admins only
- POST `conversations/{id}/leave/`
- GET `messages/?conversation={id}&q=search` — history + message search
- POST `messages/` — {conversation, body, reply_to}
- PATCH/DELETE `messages/{id}/` — own messages only; delete is soft
- POST `messages/{id}/mark_read/`, POST `messages/mark_conversation_read/` {conversation}
- POST `messages/{id}/react/` {emoji}
- POST `attachments/` — multipart file upload (allow-list + 10 MB limit)

## Notifications — /api/notifications/
- GET ``, POST `{id}/read/`, POST `read-all/`, GET `unread-count/`

## WebSocket
`ws://localhost:8000/ws/chat/<conversation_id>/?token=<access_jwt>`
