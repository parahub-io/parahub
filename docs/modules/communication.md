# Communication

End-to-end encrypted messaging via Matrix protocol, video calls via Jitsi, and real-time notifications.

## Matrix Chat

### Infrastructure
- **Synapse** homeserver, server name `parahub.io`
- **OIDC SSO** -- single sign-on, same credentials as Parahub
- **Username = Matrix ID**: `alice@parahub.io` = `@alice:parahub.io`

### Clients

Three Matrix clients, user-selectable:

| Client | Size | Strengths |
|--------|------|-----------|
| Element Web | 99MB | Full-featured, desktop-oriented, VoIP works |
| Cinny | 16MB | Lightweight, clean UI, VoIP works |
| FluffyChat | 42MB | Mobile-first design |

All embedded as iframes with Teleport to body (KeepAlive-compatible). Users set their preferred client in profile settings. Cookie-based instant redirect.

### Native Apps

The chat is standard Matrix, so dedicated Matrix apps connect to the same account -- Element X or SchildiChat Next on mobile, Element on desktop, and any other client that signs in through the browser:

1. Install the app and choose to enter a server address manually
2. Enter `parahub.io` as the server
3. The app opens a browser window -- sign in with your usual Parahub credentials and confirm

There is **no separate chat password**: sign-in always goes through the browser with the Parahub account. Apps that only offer a username/password form cannot connect.

**Second device via QR**: on a computer where you are already signed in (Element at `parahub.io/element`), open Settings → Sessions → "Link new device" → "Show QR code", then choose "Sign in with QR code" in the phone app and scan the screen. The devices verify each other automatically, so encrypted history stays readable.

Active sessions can be reviewed and revoked in the account console at `parahub.io/mas/account`.

### Features
- **E2E Encryption**: Megolm/Olm for all messages
- **Auto DM Creation**: `POST /api/v1/matrix/create-dm` creates a DM room between two users. Bot auto-accepts invites for both. Duplicate detection prevents room spam.
- **Context Messages**: DMs initiated from marketplace items or profiles include a context link
- **Unread Counter**: Real-time badge in navigation via Matrix sync API long-polling (30s)

### Auto-Login Flow
1. User navigates to `/chat`
2. The embedded client signs in via single sign-on with the existing Parahub session -- fully automatic, no separate Matrix credentials

## Video Calls

### Jitsi Meet
- JWT authentication (Parahub generates tokens)
- TURN server (coturn) for NAT traversal
- Fullscreen iframe with Teleport to body
- One-click calling from user profiles (`/call?target={profile_id}`)
- Named rooms for group calls (`/call?room={name}`)
- Incoming call notifications via WebSocket

## Notifications

### Dual-Channel Architecture

**WebSocket** (browser open):
- Authenticated: `/ws/v1/realtime/` -- partner events, contract updates, debt changes, verification, call incoming, Matrix unread
- Anonymous: `/ws/v1/public/` -- system broadcasts (deploy notifications)
- Toast notifications via `useToastStore`

**Web Push** (browser closed):
- Service Worker (`public/sw.js`)
- pywebpush + VAPID for server-side push
- i18n: notifications in user's preferred language (6 languages)
- Supported: Chrome, Firefox, Edge, Safari 16.4+
- Model: `PushSubscription` in `notifications/models.py`

### Notification Events
- Partner added/removed
- Contract created/updated/signed
- Debt created/updated
- Verification received
- Incoming video call
- Matrix unread count change
- AI analysis progress
- Poll created
- System deploy/version update

## Technical Details

- **Matrix**: `parahub/endpoints/matrix_auth.py` (DM creation, widget tokens), `parahub/endpoints/matrix_sso.py` (SSO)
- **Jitsi**: `parahub/endpoints/jitsi.py` (JWT token generation)
- **WebSocket**: `parahub/consumers/realtime.py` (unified), `parahub/consumers/public.py` (anonymous)
- **Push**: `notifications/services.py`, `notifications/api.py`
- **Frontend**: `pages/chat.vue`, `pages/call.vue`, `composables/useMatrixUnread.ts`, `composables/usePushNotifications.ts`
