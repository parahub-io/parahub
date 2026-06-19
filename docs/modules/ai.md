# AI Features

## Image Analysis

Multi-provider AI vision system for validating marketplace item images.

### Providers
- Claude Haiku 4.5 (Anthropic)
- GPT-5 (OpenAI)
- Google Gemini Flash

Provider selection configurable via admin settings (AISettings singleton model).

### Quota System
Daily limits (Redis counter):
- 30 analyses/day per account
- Check before processing, consume after success

### Two-Step Process
1. Upload image -> AI analyzes content (safety, relevance, description)
2. User reviews AI assessment -> publishes if appropriate

Real-time progress updates via WebSocket (`ai.analysis_progress` event).

## Zenith AI Assistant

Personal AI assistant powered by Google Gemini API.

### Knowledge Base
Stored in Gitea repository. Context-aware responses about the platform, its features, and how to use them.

### Configuration
- `ZenithSettings` model (per-profile) for personal preferences
- `ZenithQueryLog` for audit trail
- API: `parahub/endpoints/zenith.py`

## Image Generation

For editorial content (blog illustrations, mascot poses, marketing visuals). Nano Banana Pro/2 prompting with style anchors for series consistency. Output saved as `ObjectPhoto` attachments on posts/establishments/profiles.

## Psycho-Hash (Voluntary Personality Profiling)

Users fill an "Inner Reality Map" questionnaire with an external AI chat (ChatGPT/Claude), ask for a 4-word summary, and paste it back as their public **Psycho-Hash** (4 words, cardinality 1000^4). Used for Web of Trust compatibility matching. Private `form3_data` (legacy 30-question form) retained in DB but no longer has UI. Model: `identity.PsychProfile`. UI: inline in `/profile` photo section.

## Support Voice (Anonymous Help)

Voice-to-voice support pipeline for end users. ElevenLabs STT (`scribe_v1`) -> Gemini Flash (knowledge lookup against `docs/`) -> ElevenLabs TTS (`eleven_multilingual_v2`). Anonymous (no login required).

## Technical Details

- **AI Vision**: `parahub/services/vision_ai.py`, `parahub/services/quota.py`
- **Zenith**: `parahub/services/zenith_service.py`, `parahub/endpoints/zenith.py`
- **Psycho-Hash**: `identity/models.py` (PsychProfile), `parahub/endpoints/profiles.py`
- **Support Voice**: `parahub/consumers/support_voice.py`
