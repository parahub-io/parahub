# Bearer Bitcoin Notes (Printed Tips)

Small bearer notes you fund from your own wallet and give away -- as a link, or printed on paper. Whoever holds the note owns what is on it -- **nobody custodies it in between, not even the platform**. A note nobody claims comes back to you on its own.

Printing is one delivery channel, not the point. The other -- sending the note's link by message or email -- solves a problem paper does not: paying someone who has **no wallet and no address yet**, without the usual "send me your address" round trip.

## Why It Works This Way

A tip is a **bearer instrument**, like a banknote: the value belongs to whoever holds it -- the paper, or the link that carries the same secret. The obvious way to build that is to keep the coins in a house wallet and pay out on redemption -- which means custody, and custody is one of the things Parahub does not do.

Instead, every note is its own wallet, and the funding transfer is locked with a payment condition and an expiry. Three consequences follow:

- Only the note's secret can unlock the money.
- If the note is never claimed, the funds return to you automatically when the expiry passes.
- You **cannot** take the money back before then. Once handed over, the note is genuinely the holder's -- the sender has no cancel button.

The last two points are the same promise bctip.org made from 2013 to 2024 ("unclaimed tips come back to you"), except it no longer depends on anyone's honesty or on a server staying alive. That service, by the same author, kept your coins in its own wallet until somebody redeemed them; this one never holds them at all. Its domain now points at an explanation of what replaced it.

## How It Works

1. **Create a batch** -- choose how many notes, how many sats each, how long before unclaimed notes return, and an optional greeting. The fiat equivalent and the exchange rate are frozen at that moment and printed on the note.
2. **Funding** -- each note's secret is generated in your browser and funded from your wallet, one payment per note. Nothing is sent to the server.
3. **Give it away** -- either copy the note's link and send it (message, email, anything), or print the sheet: nine notes per A4 page with cut lines, each carrying a QR code and the same code in typeable form.
4. **The recipient opens it** -- link or QR, they land on a page that needs no account and no wallet of their own.
5. **Cash out** -- one tap unlocks the note into its own wallet, then the holder can send it anywhere: a Lightning invoice, a Lightning address, a Spark address, or an on-chain Bitcoin address. A receipt shows the amount, fee, and destination, and the payout address is remembered on the device, so someone given several notes types it once. Leaving it unclaimed on paper is also fine -- the paper *is* the wallet.

## Link or paper

Both channels carry exactly the same secret; the note does not know or care which one was used.

- **One link, one person.** A note is a single bearer secret -- if the same link goes to two people, the first to open it takes the money. Send each link to one recipient.
- **The link is the money.** It is only as private as the channel it travels through. A messenger's link-preview bot cannot take it, though: the secret rides in the URL fragment, which browsers never send to a server, so a bot fetching the URL gets the page without the money.
- **Face value drifts.** The fiat amount is frozen when the batch is minted; the note holds a fixed number of sats. A link opened weeks later is worth whatever bitcoin is worth that day. The batch page shows the value at issue next to today's.

## What Is on a Note

The greeting, the amount in sats with its fiat equivalent and the rate at issue time, a short line explaining what bitcoin is for someone who has never held any, the QR code and its typeable form, and the date after which an unclaimed note returns to the sender.

The code is printed **in the clear**. Anyone who can read the paper can claim it -- that is what a bearer note means. Treat a stack of printed notes like a stack of cash.

## Your Batches

Your list of batches is stored **in your browser**, not on the server -- the server never learns that a batch exists. Each note in a batch shows its live state: waiting, claimed, or returned. That state is read from the payment itself, not from a local flag, so a note claimed on someone else's phone shows up correctly on yours.

From the batch you can copy a single note's link, copy every link at once (one per line, labelled), hand a link straight to your phone's share sheet, or print the sheet. Each note also takes a private label -- who it is meant for -- which stays in your browser and is never printed or sent.

Clearing your browser storage loses only the ability to reprint or re-copy a link. It does not lose money: unclaimed notes still come back to you at expiry, and links already sent keep working.

## Boundaries

- The claim link opens a page, so the recipient needs a phone or a computer with a browser. There is no offline redemption.
- A note cannot be split or partly claimed, and there is no way to see whether a link was opened but not claimed -- with no server, there is nothing to count views.
- Cashing a small note out to an on-chain address can cost more in network fees than the note is worth; Lightning or Spark is the sensible route for small amounts.
- Notes cannot be topped up or re-issued. Print a new batch instead.

## Technical Details

- **Derivation**: `frontend/utils/tips.ts` -- one 128-bit secret per note, split by HKDF into a BIP39 seed (the note's wallet) and a preimage (the unlock secret). Everything is derived offline, in the browser.
- **Funding**: `composables/useLightning.ts` -- a Spark transfer locked to the note's payment hash with an expiry, sent from the sender's own wallet.
- **Claiming**: `composables/useTipWallet.ts` -- a separate wallet instance per note, isolated from the user's own wallet so the two never collide.
- **Batches**: `composables/useTipBatches.ts` -- browser-local storage, no backend model and no endpoint.
- **Pages**: `frontend/pages/tips/` (list, create, batch, printable sheet) and `frontend/pages/t.vue` (public claim page).
- **Claim URL**: `tipClaimUrl` in `utils/tips.ts` is the single definition of the link shape. The secret travels in the URL fragment, which browsers never send to a server -- so it cannot end up in a server log, and a link-preview bot fetching the URL gets the page without the money.
