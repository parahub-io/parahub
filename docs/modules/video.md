# Video

Parahub has a self-hosted video platform powered by [PeerTube](https://joinpeertube.org/), accessible at [video.parahub.io](https://video.parahub.io). Videos are stored on Parahub infrastructure -- no third-party hosting.

## Uploading Videos

Any authenticated user can upload videos (up to 4 GB). The upload interface supports drag-and-drop with a real-time progress bar.

Videos are transcoded into multiple resolutions (360p, 480p, 720p, 1080p) using HLS adaptive bitrate streaming, so viewers get the best quality for their connection.

### Where videos can be attached

Videos can be attached to various objects across the platform:

- **Blog posts** -- embed in post content using `::video[uuid]` markdown syntax
- **Marketplace items** -- product demonstrations and reviews
- **Establishments** -- video tours of organizations and businesses
- **Profiles** -- personal video channels

### Upload flow

1. Click the video upload area on a supported page (blog editor, item detail, establishment settings)
2. Select or drag a video file (max 4 GB)
3. Wait for upload and server processing
4. The video is automatically linked to the relevant object

## Browsing Videos

Visit `/videos` to browse all published videos. Two tabs:

- **Trending** -- popular videos by view count
- **Recent** -- newest uploads first

Each video card shows a thumbnail, duration, title, author, view count, and upload date.

## Video Detail Page

Click any video to see the full player with:

- Embedded PeerTube player (adaptive HLS streaming)
- Title, description, tags
- View count and likes
- Author profile link
- Link to the video on PeerTube for additional features

## Embedding in Blog Posts

The blog editor has a video embed button in the toolbar. Insert a PeerTube video URL or UUID, and it becomes a responsive embedded player in the published post. The markdown syntax is:

```
::video[peertube-uuid-here]
```

This renders as a responsive 16:9 iframe in the published post.

## Single Sign-On

PeerTube uses OIDC (OpenID Connect) for authentication. Users log in with their existing Parahub account -- no separate registration required. Clicking "Login" on video.parahub.io redirects to Parahub's login page and back.

## Federation

PeerTube supports ActivityPub, enabling video federation with other PeerTube instances. Videos published on Parahub can be discovered and watched from other federated servers, and vice versa.

## Quotas

- **Total storage**: 5 GB per user
- **Daily upload limit**: 1 GB per user

## Live Streaming

RTMP live streaming is supported by the platform (port 1935). Maximum stream duration is 8 hours. Replays are saved automatically. Live transcoding provides adaptive quality from 360p to 1080p.
