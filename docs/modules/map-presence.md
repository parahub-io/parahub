# Map Presence

Real-time MMORPG-style avatars on the map. See who else is exploring nearby areas.

## How It Works

When you have the map open, your viewport position (not GPS) is shared with other users viewing the same area. You appear as a pixel-art avatar that others can see, and you see their avatars too.

This is viewport-based presence — the system tracks what part of the map you're looking at, not where you physically are. Think of it like seeing other cursors in a shared Google Doc, but on a map.

## Features

### Avatars
Each user appears as an animated pixel-art character (LPC sprite style) on the map canvas. Avatars walk, idle, jump, sit, and emote.

### States and Actions
You can change your avatar's state:
- **Idle**: Standing still
- **Walking**: Moving across the map
- **Jumping**: Quick expressive animation
- **Sitting**: Resting position
- **Emoting**: Expressive animation

### Speech Bubbles
Send a short message that appears as a speech bubble above your avatar, visible to everyone nearby.

### Tile-Based Updates
The map is divided into tiles. You only receive updates about avatars in your visible area (your tile plus 8 surrounding tiles). This keeps the system efficient even with many users online.

### Click Interaction
Click on another user's avatar to see their profile information in the map panel.

## Privacy

- **Viewport only**: The system tracks what map area you're looking at, not your physical location
- **Auto-cleanup**: Your presence is removed after 5 minutes of inactivity
- **No history**: Position data is ephemeral (Redis only, not stored in any database)
