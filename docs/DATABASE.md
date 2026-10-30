# Database Design — read this before the models code

All models are normalized (3NF): no repeating groups, facts live in exactly one place,
and per-user / per-conversation state lives in through/join models instead of JSON blobs.

## Models and purpose

| Model | Purpose | Key relationships |
|---|---|---|
| **User** (`accounts.User`, extends `AbstractUser`) | Identity + credentials. Email is unique. Passwords are hashed by Django (PBKDF2), never stored in plaintext. | 1-to-1 with UserProfile; FK from almost everything else |
| **UserProfile** | Presentation & presence: display name, bio, avatar, `is_online`, `last_seen`. Split from User so auth queries stay lean and profile fields can evolve independently. Auto-created by a `post_save` signal. | 1-to-1 → User |
| **Conversation** | A container for messages. `type` = `private` or `group`. Groups also use `title`, `description`, `avatar`. Private chats have no title (UI derives it from the other member) and are de-duplicated in the API. | M2M → User *through* ConversationMember; 1-to-many → Message |
| **ConversationMember** | The M2M through model — this is where membership facts live: `role` (admin/member), `joined_at`, `is_muted`. Unique together on (conversation, user). Group permissions are checked against this row. | FK → Conversation, FK → User |
| **Message** | One message. `reply_to` is a self-FK for replies. `is_edited` / `is_deleted` support edit and *soft* delete (body cleared, row kept, so replies and receipts don't break). Indexed on (conversation, created_at) for fast history pages. | FK → Conversation, FK → sender (User), self-FK `reply_to` |
| **Attachment** | A file attached to a message. Validated by extension allow-list and max size (10 MB by default) in `validate_attachment`. `is_image` drives previews. | FK → Message, FK → uploader |
| **MessageRead** | One row per (message, recipient) with `status` = delivered/read and a timestamp. This is how delivery/read receipts and unread counts are computed with plain SQL — no array fields. Unique together on (message, user). | FK → Message, FK → User |
| **Notification** | A durable notification record (new message, group added, system), separate from the live WebSocket push so users can catch up after being offline. Indexed on (recipient, is_read, -created_at). | FK → recipient, FK → actor |
| **MessageReaction** (extra) | Emoji reactions, unique per (message, user, emoji) so toggling is idempotent. | FK → Message, FK → User |
| **BlockedUser** (extra) | Block list, unique per (blocker, blocked). Checked before creating a private conversation. | 2× FK → User |

## Relationship diagram

```
User 1───1 UserProfile
User 1───* ConversationMember *───1 Conversation 1───* Message
Message *───1 Message (reply_to, self-FK)
Message 1───* Attachment
Message 1───* MessageRead *───1 User
Message 1───* MessageReaction *───1 User
User 1───* Notification (as recipient and as actor)
User 1───* BlockedUser *───1 User
```

## Design choices worth mentioning in an interview / viva
- Through model for M2M (ConversationMember) instead of a plain M2M, because roles, mute and join date are data *about the membership*.
- Receipts as rows (MessageRead) instead of booleans on Message, because "read" is per-user in a group.
- Soft delete for messages, hard delete for memberships (leaving a group really leaves).
- Indexes follow the actual query shapes: conversation history, unread counts, user search.
