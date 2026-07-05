# Recurring Support (Subscriptions)

Support a profile every month with a fixed Lightning amount. A non-custodial, no-escrow recurring-support primitive -- **the platform never holds funds and takes no cut**. Every cycle is a direct Lightning payment from supporter to recipient.

## Why It Works This Way

Lightning is **push, not pull** -- a non-custodial wallet can never be charged silently. So "recurring" is **reminder-driven**: each month the supporter gets a notification and re-pays in one tap. The trade-off is deliberate -- because there is no auto-billing, the recipient keeps ~100%, there are no chargebacks, and it never breaks the platform's no-escrow / client-side-keys principles.

## How It Works

1. **Subscribe** -- on any profile, click "Support monthly", choose an amount, and pay from your Lightning wallet. You become a supporter and the recipient gets a notification.
2. **Monthly reminder** -- a few days before the period ends you are reminded. One tap re-pays and extends your support for another month. There is no automatic charge.
3. **Lapse or cancel** -- if you do not renew, support quietly lapses. You can cancel anytime; access stays until the period you already paid for ends ("don't renew", not "revoke now").

## Subscribers-Only Content

A profile can mark blog posts as **subscribers only**. The title, excerpt, and cover image stay public as a teaser, but the body unlocks only for active supporters of the author. Everyone else sees a "Support to unlock" call-to-action. Gating happens on the server -- a locked post's body never reaches a non-supporter's browser.

## What You See

- **On a profile**: a "Support monthly" button, a supporter count, and -- if you already support -- your renew-by date with a Cancel option.
- **In a blog**: a lock badge on subscribers-only posts; the full post once you support the author.
- **Notifications**: a ping when someone starts supporting you, and a reminder before your own support is about to lapse.

## Access Control

| Action | Requirement |
|--------|------------|
| Subscribe / renew | Authenticated profile with a Lightning wallet |
| Receive support | Profile with a payment address |
| Read a subscribers-only post | The author, or an active supporter of the author |

## Boundaries (v1)

- Flat amount -- any amount unlocks the content; there are no graduated tiers or per-tier perks.
- Only the post **body** is gated; attached media is hidden in the UI on locked posts.
- Renewal is a manual one-tap each month -- there is no set-and-forget auto-renew yet.

## Technical Details

- **Models**: `finance/models.py` -- Subscription (subscriber/recipient profiles, amount, status, expiry), Payment (one row per paid cycle, replay-guarded by payment hash)
- **Service**: `finance/services.py` -- start/renew (idempotent on the payment hash), cancel, and the live-supporter gate
- **API**: `parahub/endpoints/subscriptions.py` -- subscribe/renew, cancel, "my"/"inbound" lists, public status
- **Content gating**: `cms/api.py` -- server-side body stripping for `Post.subscribers_only`
- **Lifecycle**: `finance/management/commands/process_subscriptions.py` -- a daily background job that lapses expired subscriptions and sends renewal reminders
- **Frontend**: `composables/useSubscriptions.ts`, `components/user/UserLightningPayModal.vue` (subscribe mode), plus the profile and blog views
