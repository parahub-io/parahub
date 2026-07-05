"""
Activity-log signals — record the actor's OWN first-class actions.

post_save on the source models is the single choke point: the Activity row is
born in the same transaction as the action (no scattered emit calls, no drift).
Each handler builds a localized title/body in the actor's language and calls
``record_activity``, which persists the row and pushes ``activity.new`` over WS.

The per-model "build the activity kwargs from an instance" logic lives in the
``build_*_activity`` functions so the backfill command can reuse it (DRY) —
``ACTIVITY_BUILDERS`` is the single registry of ``(model, builder, ts_attr)``
triples. ``ts_attr`` names the field holding *when the action happened* — the
timestamp the backfill backdates each row to. It is ``created_at`` for rows
written once, but ``Verification`` re-affirms in place (``verified_at`` is bumped
on re-verify while ``created_at`` stays frozen at first insert), so its action
time is ``verified_at``.

v1 first-class actions: poll vote, WoT verification, market listing, contract
creation. Re-actions that update an existing row instead of creating one
(re-verify after revoke, re-vote) don't fire on ``created`` — acceptable for v1.

Caveat: signals do not fire on ``bulk_create`` / ``QuerySet.update()`` / raw SQL.
First-class actions are single ORM creates, so they are logged.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from governance.models import PollVote
from identity.models import Verification
from contracts.models import Contract
from market.models import Item

from .services import record_activity, _pick_lang

logger = logging.getLogger(__name__)


# ── Localized title strings, keyed by verb then language ──────────────────
_TITLES = {
    'voted': {
        'en': 'You voted', 'ru': 'Вы проголосовали', 'pt': 'Você votou',
        'es': 'Has votado', 'fr': 'Vous avez voté', 'de': 'Sie haben abgestimmt',
    },
    'verified': {
        'en': 'You verified a member', 'ru': 'Вы верифицировали участника',
        'pt': 'Você verificou um membro', 'es': 'Has verificado a un miembro',
        'fr': 'Vous avez vérifié un membre', 'de': 'Sie haben ein Mitglied verifiziert',
    },
    'listed_item': {
        'en': 'You posted a listing', 'ru': 'Вы разместили объявление',
        'pt': 'Você publicou um anúncio', 'es': 'Has publicado un anuncio',
        'fr': 'Vous avez publié une annonce', 'de': 'Sie haben eine Anzeige veröffentlicht',
    },
    'created_contract': {
        'en': 'You created a contract', 'ru': 'Вы создали контракт',
        'pt': 'Você criou um contrato', 'es': 'Has creado un contrato',
        'fr': 'Vous avez créé un contrat', 'de': 'Sie haben einen Vertrag erstellt',
    },
}


def _title(verb: str, lang: str) -> str:
    langs = _TITLES[verb]
    return langs.get(lang, langs['en'])


# ── Builders: (source instance) → kwargs for record_activity ──────────────
# Shared by the live signal handlers and the backfill command.

def build_poll_vote_activity(instance) -> dict:
    actor = instance.voter
    poll = instance.poll
    return dict(
        actor=actor.account, verb='voted', obj=instance, category='governance',
        title=_title('voted', _pick_lang(actor)), body=poll.title,
        url=f'/governance/polls/{poll.id}',
        data={'poll_id': poll.id, 'option_id': instance.option_id},
    )


def build_verification_activity(instance) -> dict:
    actor = instance.verifier
    verified = instance.verified_profile
    name = verified.display_name or verified.local_name or verified.hna
    return dict(
        actor=actor.account, verb='verified', obj=instance, category='social',
        title=_title('verified', _pick_lang(actor)), body=name,
        url=f'/u/{verified.id}',
        data={'verified_id': verified.id, 'method': instance.verification_method},
    )


def build_item_activity(instance) -> dict:
    actor = instance.owner
    return dict(
        actor=actor.account, verb='listed_item', obj=instance, category='market',
        title=_title('listed_item', _pick_lang(actor)), body=instance.title,
        url=f'/market/{instance.id}',
        data={'item_id': instance.id, 'type': instance.type},
    )


def build_contract_activity(instance) -> dict:
    actor = instance.creator
    return dict(
        actor=actor.account, verb='created_contract', obj=instance, category='contracts',
        title=_title('created_contract', _pick_lang(actor)), body=instance.title,
        url='/contracts',
        data={'contract_id': instance.id, 'partner_id': instance.partner_id},
    )


# Registry consumed by the backfill management command.
# (model, builder, ts_attr) — ts_attr is the field the backfill backdates to (see
# module docstring). Verification's action time is verified_at, not created_at.
ACTIVITY_BUILDERS = [
    (PollVote, build_poll_vote_activity, 'created_at'),
    (Verification, build_verification_activity, 'verified_at'),
    (Item, build_item_activity, 'created_at'),
    (Contract, build_contract_activity, 'created_at'),
]


# ── Live signal handlers ──────────────────────────────────────────────────

@receiver(post_save, sender=PollVote)
def log_poll_vote(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        record_activity(**build_poll_vote_activity(instance))
    except Exception as e:
        logger.warning(f"activity log_poll_vote failed: {e}")


@receiver(post_save, sender=Verification)
def log_verification(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        record_activity(**build_verification_activity(instance))
    except Exception as e:
        logger.warning(f"activity log_verification failed: {e}")


@receiver(post_save, sender=Item)
def log_item_listed(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        record_activity(**build_item_activity(instance))
    except Exception as e:
        logger.warning(f"activity log_item_listed failed: {e}")


@receiver(post_save, sender=Contract)
def log_contract_created(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        record_activity(**build_contract_activity(instance))
    except Exception as e:
        logger.warning(f"activity log_contract_created failed: {e}")
