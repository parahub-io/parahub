"""
Tests for tickets endpoints: ticket type CRUD, purchase, confirm, validate, sign, my tickets.

Tests invariants that must never break:
- WoT / staff required to create ticket types
- WoT / staff required to purchase tickets
- Lightning address required for operators
- Operator-only update/delete of ticket types
- Category validation (EVENT requires event_id, TRANSIT requires route_id)
- Purchase flow: initiate → confirm with Lightning proof → use QR
- SHA256(preimage) == payment_hash verification
- Duplicate payment hash rejection
- Sold-out enforcement
- QR validation marks ticket as USED (one-time)
- Buyer/operator access control on ticket detail
- PGP signature attachment (buyer only)

WoT checks: create_ticket_type uses is_verified_wot (3+ verifications),
      purchase_ticket uses received_verifications count. Tests use is_staff=True for success paths.
"""

import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from ninja.errors import HttpError

from currency.models import ExchangeRate
from identity.models import Account, Profile
from core.models import Instance
from geo.models import (
    Place, TransitDataSource, Agency, Route, Event,
    Establishment, EstablishmentMembership,
)
from tickets.models import Ticket, TicketType
from tickets.api import (
    list_ticket_types, get_ticket_type, create_ticket_type,
    update_ticket_type, delete_ticket_type,
    purchase_ticket, confirm_payment, sign_ticket,
    my_tickets, get_ticket, validate_ticket,
    operator_contexts, operator_stats, operator_sales_csv,
    validate_sync, qr_pubkey, validable_types, operator_refunds,
    request_refund, cancel_refund_request, resolve_refund,
    TicketTypeCreateReq, TicketTypeUpdateReq,
    PurchaseReq, ConfirmReq, SignReq, ValidateReq,
    SyncReq, SyncItem, RefundRequestReq, RefundResolveReq,
)
from tickets.qr_signing import build_qr_payload, public_key_b64, QR_PREFIX


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_instance():
    return Instance.objects.create(
        domain='test.parahub.io', name='Test Instance', public_key='test-key',
    )


def _create_account(instance, username='alice', is_staff=False, **kwargs):
    return Account.objects.create_user(
        username=username,
        email=f'{username}@test.parahub.io',
        password='testpass123',
        instance=instance,
        is_staff=is_staff,
        **kwargs,
    )


def _create_profile(account, instance, local_name=None, **kwargs):
    local_name = local_name or account.username
    return Profile.objects.create(
        account=account, instance=instance,
        local_name=local_name, display_name=local_name.title(),
        is_primary=True,
        profile_type=kwargs.pop('profile_type', Profile.ProfileType.PERSONAL),
        **kwargs,
    )


def _make_request(factory, account, profile, method='get', path='/fake/', data=None):
    fn = getattr(factory, method)
    request = fn(path, data=data, content_type='application/json') if data else fn(path)
    request.user = account
    request.auth = profile
    request.auth_profile = profile
    request.session = SessionStore()
    request.session.create()
    return request


def _create_transit_chain():
    """Create Place → TransitDataSource → Agency → Route chain."""
    place = Place.objects.create(name='Test City', slug='test-city', country_code='PT')
    ds = TransitDataSource.objects.create(name='Test Source', format='gtfs')
    agency = Agency.objects.create(
        data_source=ds, source_id='TEST', name='Test Agency',
        timezone='Europe/Lisbon', lang='pt',
    )
    route = Route.objects.create(
        agency=agency, place=place, source_id='R1',
        short_name='1', long_name='Route 1', route_type=3,
    )
    return place, ds, agency, route


def _create_event(profile):
    return Event.objects.create(
        organizer=profile, title='Test Event', description='Test',
        event_type='OFFLINE', status='PUBLISHED',
        starts_at=timezone.now() + timedelta(days=7),
    )


def _make_preimage_pair():
    """Generate a valid preimage/payment_hash pair."""
    preimage = secrets.token_hex(32)
    payment_hash = hashlib.sha256(bytes.fromhex(preimage)).hexdigest()
    return preimage, payment_hash


# ---------------------------------------------------------------------------
# TicketType CRUD
# ---------------------------------------------------------------------------

class TicketTypeCRUDTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.acc = _create_account(self.inst, 'operator', is_staff=True)
        self.profile = _create_profile(self.acc, self.inst, ln_address='test@ln.io')
        self.place, self.ds, self.agency, self.route = _create_transit_chain()
        self.event = _create_event(self.profile)

    def _req(self, method='get', data=None):
        return _make_request(self.factory, self.acc, self.profile, method=method, data=data)

    def test_list_ticket_types_empty(self):
        result = list_ticket_types(self._req())
        self.assertEqual(len(result), 0)

    def test_list_ticket_types_active_only(self):
        TicketType.objects.create(
            category='EVENT', name='Active', price_sats=100,
            event=self.event, operator=self.profile,
        )
        TicketType.objects.create(
            category='TRANSIT', name='Inactive', price_sats=200,
            route=self.route, operator=self.profile, is_active=False,
        )
        result = list_ticket_types(self._req())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'Active')

    def test_list_filter_by_category(self):
        TicketType.objects.create(
            category='EVENT', name='Event TT', price_sats=100,
            event=self.event, operator=self.profile,
        )
        TicketType.objects.create(
            category='TRANSIT', name='Transit TT', price_sats=200,
            route=self.route, operator=self.profile,
        )
        result = list_ticket_types(self._req(), category='EVENT')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].category, 'EVENT')

    def test_list_filter_by_event(self):
        TicketType.objects.create(
            category='EVENT', name='Event TT', price_sats=100,
            event=self.event, operator=self.profile,
        )
        result = list_ticket_types(self._req(), event_id=self.event.id)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].event_id, str(self.event.id))

    def test_get_ticket_type_success(self):
        tt = TicketType.objects.create(
            category='EVENT', name='Concert', price_sats=500,
            event=self.event, operator=self.profile,
        )
        result = get_ticket_type(self._req(), tt.id)
        self.assertEqual(result.id, tt.id)
        self.assertEqual(result.name, 'Concert')
        self.assertEqual(result.object_type, 'ticket_type')

    def test_get_ticket_type_404(self):
        with self.assertRaises(HttpError) as ctx:
            get_ticket_type(self._req(), '01NONEXISTENT00000000000000')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_create_event_ticket_type(self):
        data = TicketTypeCreateReq(
            category='EVENT', name='VIP', price_sats=1000,
            event_id=self.event.id,
        )
        result = create_ticket_type(self._req('post'), data)
        self.assertEqual(result.category, 'EVENT')
        self.assertEqual(result.name, 'VIP')
        self.assertEqual(result.price_sats, 1000)

    def test_create_transit_ticket_type(self):
        data = TicketTypeCreateReq(
            category='TRANSIT', name='Day Pass', price_sats=500,
            route_id=self.route.id,
        )
        result = create_ticket_type(self._req('post'), data)
        self.assertEqual(result.category, 'TRANSIT')
        self.assertEqual(result.route_id, str(self.route.id))

    def test_create_requires_staff_or_wot(self):
        acc2 = _create_account(self.inst, 'lowwot')
        p2 = _create_profile(acc2, self.inst, ln_address='x@ln.io')
        req = _make_request(self.factory, acc2, p2, 'post')
        data = TicketTypeCreateReq(
            category='EVENT', name='VIP', price_sats=1000,
            event_id=self.event.id,
        )
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(req, data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_create_requires_lightning_address(self):
        acc2 = _create_account(self.inst, 'noln', is_staff=True)
        p2 = _create_profile(acc2, self.inst)  # no ln_address
        req = _make_request(self.factory, acc2, p2, 'post')
        data = TicketTypeCreateReq(
            category='EVENT', name='VIP', price_sats=1000,
            event_id=self.event.id,
        )
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(req, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_invalid_category(self):
        data = TicketTypeCreateReq(category='INVALID', name='Bad', price_sats=100)
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(self._req('post'), data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_event_without_event_id(self):
        data = TicketTypeCreateReq(category='EVENT', name='No Event', price_sats=100)
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(self._req('post'), data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_transit_without_route_id(self):
        data = TicketTypeCreateReq(category='TRANSIT', name='No Route', price_sats=100)
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(self._req('post'), data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_price_must_be_positive(self):
        data = TicketTypeCreateReq(
            category='EVENT', name='Free?', price_sats=0,
            event_id=self.event.id,
        )
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(self._req('post'), data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_update_owner_can_modify(self):
        tt = TicketType.objects.create(
            category='EVENT', name='Old', price_sats=100,
            event=self.event, operator=self.profile,
        )
        data = TicketTypeUpdateReq(name='New', price_sats=200)
        result = update_ticket_type(self._req('put'), tt.id, data)
        self.assertEqual(result.name, 'New')
        self.assertEqual(result.price_sats, 200)

    def test_update_non_owner_rejected(self):
        tt = TicketType.objects.create(
            category='EVENT', name='Original', price_sats=100,
            event=self.event, operator=self.profile,
        )
        acc2 = _create_account(self.inst, 'stranger')
        p2 = _create_profile(acc2, self.inst)
        req = _make_request(self.factory, acc2, p2, 'put')
        with self.assertRaises(HttpError) as ctx:
            update_ticket_type(req, tt.id, TicketTypeUpdateReq(name='Hacked'))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_update_invalid_price_rejected(self):
        tt = TicketType.objects.create(
            category='EVENT', name='X', price_sats=100,
            event=self.event, operator=self.profile,
        )
        with self.assertRaises(HttpError) as ctx:
            update_ticket_type(self._req('put'), tt.id, TicketTypeUpdateReq(price_sats=0))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_delete_soft_delete(self):
        tt = TicketType.objects.create(
            category='EVENT', name='ToDelete', price_sats=100,
            event=self.event, operator=self.profile,
        )
        result = delete_ticket_type(self._req('delete'), tt.id)
        self.assertEqual(result, {"ok": True})
        tt.refresh_from_db()
        self.assertFalse(tt.is_active)

    def test_delete_non_owner_rejected(self):
        tt = TicketType.objects.create(
            category='EVENT', name='Protected', price_sats=100,
            event=self.event, operator=self.profile,
        )
        acc2 = _create_account(self.inst, 'stranger')
        p2 = _create_profile(acc2, self.inst)
        req = _make_request(self.factory, acc2, p2, 'delete')
        with self.assertRaises(HttpError) as ctx:
            delete_ticket_type(req, tt.id)
        self.assertEqual(ctx.exception.status_code, 403)


# ---------------------------------------------------------------------------
# Purchase / Confirm / Validate flow
# ---------------------------------------------------------------------------

class TicketPurchaseFlowTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        # Operator (staff + LN address)
        self.op_acc = _create_account(self.inst, 'operator', is_staff=True)
        self.op_profile = _create_profile(self.op_acc, self.inst, ln_address='op@ln.io')
        # Buyer (staff for WoT bypass — see NOTE at top)
        self.buyer_acc = _create_account(self.inst, 'buyer', is_staff=True)
        self.buyer_profile = _create_profile(self.buyer_acc, self.inst)
        # Transit chain + ticket type
        self.place, self.ds, self.agency, self.route = _create_transit_chain()
        self.tt = TicketType.objects.create(
            category='TRANSIT', name='Single Ride', price_sats=100,
            route=self.route, operator=self.op_profile, max_capacity=10,
        )

    def _buyer_req(self, method='post'):
        return _make_request(self.factory, self.buyer_acc, self.buyer_profile, method)

    def _op_req(self, method='post'):
        return _make_request(self.factory, self.op_acc, self.op_profile, method)

    def test_purchase_creates_pending_ticket(self):
        result = purchase_ticket(self._buyer_req(), PurchaseReq(ticket_type_id=self.tt.id))
        self.assertEqual(result.status, 'PENDING_PAYMENT')
        self.assertEqual(result.ticket_type_id, self.tt.id)
        self.assertTrue(result.qr_token)

    def test_purchase_non_staff_non_wot_rejected(self):
        acc = _create_account(self.inst, 'nobody')
        p = _create_profile(acc, self.inst)
        req = _make_request(self.factory, acc, p, 'post')
        with self.assertRaises(HttpError) as ctx:
            purchase_ticket(req, PurchaseReq(ticket_type_id=self.tt.id))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_purchase_sold_out(self):
        self.tt.sold_count = 10  # max_capacity=10
        self.tt.save()
        with self.assertRaises(HttpError) as ctx:
            purchase_ticket(self._buyer_req(), PurchaseReq(ticket_type_id=self.tt.id))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_purchase_inactive_type_404(self):
        self.tt.is_active = False
        self.tt.save()
        with self.assertRaises(HttpError) as ctx:
            purchase_ticket(self._buyer_req(), PurchaseReq(ticket_type_id=self.tt.id))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_purchase_rate_limit(self):
        """Max 5 pending per hour."""
        for i in range(5):
            Ticket.objects.create(
                ticket_type=self.tt, buyer=self.buyer_profile,
                expires_at=timezone.now() + timedelta(minutes=15),
            )
        with self.assertRaises(HttpError) as ctx:
            purchase_ticket(self._buyer_req(), PurchaseReq(ticket_type_id=self.tt.id))
        self.assertEqual(ctx.exception.status_code, 429)

    def test_confirm_payment_success(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile,
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        preimage, payment_hash = _make_preimage_pair()
        result = confirm_payment(self._buyer_req(), ConfirmReq(
            ticket_id=ticket.id,
            ln_payment_hash=payment_hash,
            ln_preimage=preimage,
        ))
        self.assertEqual(result.status, 'ACTIVE')
        self.assertEqual(result.ln_payment_hash, payment_hash)
        self.assertEqual(result.amount_paid_sats, 100)
        # sold_count incremented
        self.tt.refresh_from_db()
        self.assertEqual(self.tt.sold_count, 1)

    def test_confirm_invalid_preimage(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile,
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        preimage, payment_hash = _make_preimage_pair()
        with self.assertRaises(HttpError) as ctx:
            confirm_payment(self._buyer_req(), ConfirmReq(
                ticket_id=ticket.id,
                ln_payment_hash=payment_hash,
                ln_preimage=secrets.token_hex(32),  # wrong preimage
            ))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_confirm_duplicate_payment_hash(self):
        preimage, payment_hash = _make_preimage_pair()
        Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile,
            status=Ticket.Status.ACTIVE, ln_payment_hash=payment_hash,
        )
        t2 = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile,
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        with self.assertRaises(HttpError) as ctx:
            confirm_payment(self._buyer_req(), ConfirmReq(
                ticket_id=t2.id,
                ln_payment_hash=payment_hash,
                ln_preimage=preimage,
            ))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_confirm_expired_ticket(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        preimage, payment_hash = _make_preimage_pair()
        with self.assertRaises(HttpError) as ctx:
            confirm_payment(self._buyer_req(), ConfirmReq(
                ticket_id=ticket.id,
                ln_payment_hash=payment_hash,
                ln_preimage=preimage,
            ))
        self.assertEqual(ctx.exception.status_code, 410)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.EXPIRED)

    def test_confirm_already_active_rejected(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile,
            status=Ticket.Status.ACTIVE,
        )
        preimage, payment_hash = _make_preimage_pair()
        with self.assertRaises(HttpError) as ctx:
            confirm_payment(self._buyer_req(), ConfirmReq(
                ticket_id=ticket.id,
                ln_payment_hash=payment_hash,
                ln_preimage=preimage,
            ))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_validate_success_marks_used(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile,
            status=Ticket.Status.ACTIVE,
        )
        result = validate_ticket(self._op_req(), ValidateReq(qr_token=ticket.qr_token))
        self.assertTrue(result.valid)
        self.assertEqual(result.ticket_id, ticket.id)
        self.assertEqual(result.message, 'Valid ticket')
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.USED)
        self.assertIsNotNone(ticket.used_at)

    def test_validate_already_used(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile,
            status=Ticket.Status.USED, used_at=timezone.now(),
        )
        result = validate_ticket(self._op_req(), ValidateReq(qr_token=ticket.qr_token))
        self.assertFalse(result.valid)
        self.assertIn('Already used', result.message)

    def test_validate_unknown_token(self):
        result = validate_ticket(self._op_req(), ValidateReq(qr_token='nonexistent' * 4))
        self.assertFalse(result.valid)
        self.assertEqual(result.message, 'Unknown ticket')

    def test_validate_non_operator_rejected(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile,
            status=Ticket.Status.ACTIVE,
        )
        acc3 = _create_account(self.inst, 'random')
        p3 = _create_profile(acc3, self.inst)
        req = _make_request(self.factory, acc3, p3, 'post')
        result = validate_ticket(req, ValidateReq(qr_token=ticket.qr_token))
        self.assertFalse(result.valid)
        self.assertIn('Not authorized', result.message)

    def test_validate_pending_ticket_rejected(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile,
            status=Ticket.Status.PENDING_PAYMENT,
        )
        result = validate_ticket(self._op_req(), ValidateReq(qr_token=ticket.qr_token))
        self.assertFalse(result.valid)
        self.assertIn('PENDING_PAYMENT', result.message)


# ---------------------------------------------------------------------------
# My tickets / Get ticket / Sign ticket
# ---------------------------------------------------------------------------

class TicketAccessTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.op_acc = _create_account(self.inst, 'operator', is_staff=True)
        self.op_profile = _create_profile(self.op_acc, self.inst, ln_address='op@ln.io')
        self.buyer_acc = _create_account(self.inst, 'buyer', is_staff=True)
        self.buyer_profile = _create_profile(self.buyer_acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()
        self.tt = TicketType.objects.create(
            category='TRANSIT', name='Test', price_sats=100,
            route=self.route, operator=self.op_profile,
        )

    def _buyer_req(self, method='get'):
        return _make_request(self.factory, self.buyer_acc, self.buyer_profile, method)

    def test_my_tickets_returns_buyer_only(self):
        Ticket.objects.create(ticket_type=self.tt, buyer=self.buyer_profile, status=Ticket.Status.ACTIVE)
        Ticket.objects.create(ticket_type=self.tt, buyer=self.buyer_profile, status=Ticket.Status.PENDING_PAYMENT)
        # Other user's ticket
        acc2 = _create_account(self.inst, 'other')
        p2 = _create_profile(acc2, self.inst)
        Ticket.objects.create(ticket_type=self.tt, buyer=p2, status=Ticket.Status.ACTIVE)

        result = my_tickets(self._buyer_req())
        self.assertEqual(len(result), 2)

    def test_my_tickets_filter_by_status(self):
        Ticket.objects.create(ticket_type=self.tt, buyer=self.buyer_profile, status=Ticket.Status.ACTIVE)
        Ticket.objects.create(ticket_type=self.tt, buyer=self.buyer_profile, status=Ticket.Status.PENDING_PAYMENT)
        result = my_tickets(self._buyer_req(), status='ACTIVE')
        self.assertEqual(len(result), 1)

    def test_get_ticket_buyer_access(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile, status=Ticket.Status.ACTIVE,
        )
        result = get_ticket(self._buyer_req(), ticket.id)
        self.assertEqual(result.id, ticket.id)
        self.assertEqual(result.object_type, 'ticket')

    def test_get_ticket_operator_access(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile, status=Ticket.Status.ACTIVE,
        )
        req = _make_request(self.factory, self.op_acc, self.op_profile)
        result = get_ticket(req, ticket.id)
        self.assertEqual(result.id, ticket.id)

    def test_get_ticket_stranger_rejected(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile, status=Ticket.Status.ACTIVE,
        )
        acc3 = _create_account(self.inst, 'stranger')
        p3 = _create_profile(acc3, self.inst)
        req = _make_request(self.factory, acc3, p3)
        with self.assertRaises(HttpError) as ctx:
            get_ticket(req, ticket.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_sign_ticket_success(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile, status=Ticket.Status.ACTIVE,
        )
        req = _make_request(self.factory, self.buyer_acc, self.buyer_profile, 'patch')
        result = sign_ticket(req, ticket.id, SignReq(pgp_signature='-----BEGIN PGP SIGNATURE-----'))
        self.assertEqual(result.pgp_signature, '-----BEGIN PGP SIGNATURE-----')

    def test_sign_used_ticket_rejected(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile, status=Ticket.Status.USED,
        )
        req = _make_request(self.factory, self.buyer_acc, self.buyer_profile, 'patch')
        with self.assertRaises(HttpError) as ctx:
            sign_ticket(req, ticket.id, SignReq(pgp_signature='test'))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_sign_non_buyer_rejected(self):
        ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile, status=Ticket.Status.ACTIVE,
        )
        acc3 = _create_account(self.inst, 'stranger')
        p3 = _create_profile(acc3, self.inst)
        req = _make_request(self.factory, acc3, p3, 'patch')
        with self.assertRaises(HttpError) as ctx:
            sign_ticket(req, ticket.id, SignReq(pgp_signature='test'))
        self.assertEqual(ctx.exception.status_code, 404)


# ---------------------------------------------------------------------------
# EUR pricing (sats quoted at purchase from currency.ExchangeRate BTC row)
# ---------------------------------------------------------------------------

class EurPricingTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.op_acc = _create_account(self.inst, 'operator', is_staff=True)
        self.op_profile = _create_profile(self.op_acc, self.inst, ln_address='op@ln.io')
        self.buyer_acc = _create_account(self.inst, 'buyer', is_staff=True)
        self.buyer_profile = _create_profile(self.buyer_acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()
        # 1 EUR = 0.00002 BTC → 2000 sats/EUR
        ExchangeRate.objects.create(currency='BTC', rate_to_eur=Decimal('0.00002'))
        self.eur_tt = TicketType.objects.create(
            category='TRANSIT', name='EUR Ride', price_eur=Decimal('1.50'),
            price_sats=None, route=self.route, operator=self.op_profile,
        )

    def _req(self, method='post'):
        return _make_request(self.factory, self.op_acc, self.op_profile, method)

    def _buyer_req(self, method='post'):
        return _make_request(self.factory, self.buyer_acc, self.buyer_profile, method)

    def test_create_eur_type(self):
        data = TicketTypeCreateReq(
            category='TRANSIT', name='EUR Pass', price_eur=Decimal('2.50'),
            route_id=self.route.id,
        )
        result = create_ticket_type(self._req(), data)
        self.assertEqual(result.price_eur, 2.5)
        self.assertEqual(result.price_sats, 5000)  # quote at 2000 sats/EUR

    def test_create_both_prices_rejected(self):
        data = TicketTypeCreateReq(
            category='TRANSIT', name='Bad', price_sats=100,
            price_eur=Decimal('1.00'), route_id=self.route.id,
        )
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(self._req(), data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_no_price_rejected(self):
        data = TicketTypeCreateReq(
            category='TRANSIT', name='Bad', route_id=self.route.id,
        )
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(self._req(), data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_listing_shows_eur_and_quote(self):
        result = get_ticket_type(self._req('get'), self.eur_tt.id)
        self.assertEqual(result.price_eur, 1.5)
        self.assertEqual(result.price_sats, 3000)

    def test_listing_quote_none_without_rate(self):
        ExchangeRate.objects.filter(currency='BTC').delete()
        result = get_ticket_type(self._req('get'), self.eur_tt.id)
        self.assertEqual(result.price_eur, 1.5)
        self.assertIsNone(result.price_sats)

    def test_purchase_eur_locks_quote(self):
        result = purchase_ticket(self._buyer_req(), PurchaseReq(ticket_type_id=self.eur_tt.id))
        self.assertEqual(result.amount_due_sats, 3000)
        self.assertEqual(result.price_eur, 1.5)
        ticket = Ticket.objects.get(id=result.id)
        self.assertEqual(ticket.amount_due_sats, 3000)
        self.assertEqual(ticket.price_eur, Decimal('1.50'))

    def test_confirm_eur_uses_locked_amount(self):
        purchased = purchase_ticket(self._buyer_req(), PurchaseReq(ticket_type_id=self.eur_tt.id))
        # Price change after purchase must NOT affect the locked quote
        self.eur_tt.price_eur = Decimal('99.00')
        self.eur_tt.save()
        preimage, payment_hash = _make_preimage_pair()
        result = confirm_payment(self._buyer_req(), ConfirmReq(
            ticket_id=purchased.id,
            ln_payment_hash=payment_hash,
            ln_preimage=preimage,
        ))
        self.assertEqual(result.status, 'ACTIVE')
        self.assertEqual(result.amount_paid_sats, 3000)

    def test_purchase_eur_stale_rate_rejected(self):
        ExchangeRate.objects.filter(currency='BTC').update(
            updated_at=timezone.now() - timedelta(days=3),
        )
        with self.assertRaises(HttpError) as ctx:
            purchase_ticket(self._buyer_req(), PurchaseReq(ticket_type_id=self.eur_tt.id))
        self.assertEqual(ctx.exception.status_code, 503)

    def test_purchase_eur_missing_rate_rejected(self):
        ExchangeRate.objects.filter(currency='BTC').delete()
        with self.assertRaises(HttpError) as ctx:
            purchase_ticket(self._buyer_req(), PurchaseReq(ticket_type_id=self.eur_tt.id))
        self.assertEqual(ctx.exception.status_code, 503)

    def test_purchase_sats_type_unaffected_by_rate(self):
        ExchangeRate.objects.filter(currency='BTC').delete()
        sats_tt = TicketType.objects.create(
            category='TRANSIT', name='Sats Ride', price_sats=100,
            route=self.route, operator=self.op_profile,
        )
        result = purchase_ticket(self._buyer_req(), PurchaseReq(ticket_type_id=sats_tt.id))
        self.assertEqual(result.amount_due_sats, 100)
        self.assertIsNone(result.price_eur)

    def test_update_switches_price_mode(self):
        sats_tt = TicketType.objects.create(
            category='TRANSIT', name='Switch', price_sats=100,
            route=self.route, operator=self.op_profile,
        )
        result = update_ticket_type(
            self._req('put'), sats_tt.id, TicketTypeUpdateReq(price_eur=Decimal('3.00')),
        )
        self.assertEqual(result.price_eur, 3.0)
        sats_tt.refresh_from_db()
        self.assertIsNone(sats_tt.price_sats)
        self.assertEqual(sats_tt.price_eur, Decimal('3.00'))

    def test_update_both_prices_rejected(self):
        with self.assertRaises(HttpError) as ctx:
            update_ticket_type(
                self._req('put'), self.eur_tt.id,
                TicketTypeUpdateReq(price_sats=100, price_eur=Decimal('1.00')),
            )
        self.assertEqual(ctx.exception.status_code, 400)


# ---------------------------------------------------------------------------
# Establishment-operated ticket types (org receives payment, members manage)
# ---------------------------------------------------------------------------

class EstablishmentOperatorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.staff_acc = _create_account(self.inst, 'staff', is_staff=True)
        self.staff_profile = _create_profile(self.staff_acc, self.inst, ln_address='staff@ln.io')
        self.buyer_acc = _create_account(self.inst, 'buyer', is_staff=True)
        self.buyer_profile = _create_profile(self.buyer_acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()

        self.est = Establishment.objects.create(
            name='Câmara Test', organization_type='GOVERNMENT',
            spark_address='sp1qtestestablishment',
        )

        def member(username, role, **profile_kwargs):
            acc = _create_account(self.inst, username)
            profile = _create_profile(acc, self.inst, **profile_kwargs)
            EstablishmentMembership.objects.create(
                profile=profile, establishment=self.est, role=role,
            )
            return acc, profile

        self.owner_acc, self.owner_profile = member('estowner', 'OWNER', is_verified_wot=True)
        self.admin_acc, self.admin_profile = member('estadmin', 'ADMIN')
        self.employee_acc, self.employee_profile = member('estemployee', 'EMPLOYEE')
        self.contractor_acc, self.contractor_profile = member('estcontractor', 'CONTRACTOR')
        self.member_acc, self.member_profile = member('estmember', 'MEMBER', is_verified_wot=True)

        self.outsider_acc = _create_account(self.inst, 'outsider')
        self.outsider_profile = _create_profile(
            self.outsider_acc, self.inst, is_verified_wot=True, ln_address='out@ln.io',
        )

        # Establishment-operated type; creator profile (staff) is NOT a member
        self.tt = TicketType.objects.create(
            category='TRANSIT', name='Org Ride', price_sats=100,
            route=self.route, operator=self.staff_profile,
            operator_establishment=self.est,
        )

    def _req(self, acc, profile, method='post'):
        return _make_request(self.factory, acc, profile, method)

    def test_create_with_establishment_by_owner(self):
        data = TicketTypeCreateReq(
            category='TRANSIT', name='Owner Created', price_sats=200,
            route_id=self.route.id, operator_establishment_id=self.est.id,
        )
        result = create_ticket_type(self._req(self.owner_acc, self.owner_profile), data)
        self.assertEqual(result.operator_establishment_id, self.est.id)
        self.assertEqual(result.operator_name, self.est.name)
        self.assertEqual(result.operator_spark_address, self.est.spark_address)

    def test_create_with_establishment_non_member_rejected(self):
        data = TicketTypeCreateReq(
            category='TRANSIT', name='Nope', price_sats=200,
            route_id=self.route.id, operator_establishment_id=self.est.id,
        )
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(self._req(self.outsider_acc, self.outsider_profile), data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_create_with_establishment_member_role_rejected(self):
        data = TicketTypeCreateReq(
            category='TRANSIT', name='Nope', price_sats=200,
            route_id=self.route.id, operator_establishment_id=self.est.id,
        )
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(self._req(self.member_acc, self.member_profile), data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_create_establishment_without_address_rejected(self):
        est2 = Establishment.objects.create(name='No Wallet Org')
        EstablishmentMembership.objects.create(
            profile=self.owner_profile, establishment=est2, role='OWNER',
        )
        data = TicketTypeCreateReq(
            category='TRANSIT', name='No Pay', price_sats=200,
            route_id=self.route.id, operator_establishment_id=est2.id,
        )
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(self._req(self.owner_acc, self.owner_profile), data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_payment_resolution_in_listing(self):
        result = get_ticket_type(self._req(self.buyer_acc, self.buyer_profile, 'get'), self.tt.id)
        self.assertEqual(result.operator_spark_address, self.est.spark_address)
        self.assertEqual(result.operator_name, self.est.name)
        self.assertEqual(result.operator_establishment_id, self.est.id)

    def test_update_by_admin_member(self):
        result = update_ticket_type(
            self._req(self.admin_acc, self.admin_profile, 'put'),
            self.tt.id, TicketTypeUpdateReq(name='Renamed'),
        )
        self.assertEqual(result.name, 'Renamed')

    def test_update_by_employee_rejected(self):
        with self.assertRaises(HttpError) as ctx:
            update_ticket_type(
                self._req(self.employee_acc, self.employee_profile, 'put'),
                self.tt.id, TicketTypeUpdateReq(name='Hacked'),
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_update_by_non_member_creator_rejected(self):
        """For establishment types the operator profile has no standalone rights."""
        self.tt.operator = self.outsider_profile
        self.tt.save(update_fields=['operator'])
        with self.assertRaises(HttpError) as ctx:
            update_ticket_type(
                self._req(self.outsider_acc, self.outsider_profile, 'put'),
                self.tt.id, TicketTypeUpdateReq(name='Mine?'),
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_delete_by_admin_member(self):
        result = delete_ticket_type(
            self._req(self.admin_acc, self.admin_profile, 'delete'), self.tt.id,
        )
        self.assertEqual(result, {"ok": True})

    def _active_ticket(self):
        return Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile, status=Ticket.Status.ACTIVE,
        )

    def test_validate_by_employee(self):
        ticket = self._active_ticket()
        result = validate_ticket(
            self._req(self.employee_acc, self.employee_profile),
            ValidateReq(qr_token=ticket.qr_token),
        )
        self.assertTrue(result.valid)

    def test_validate_by_contractor(self):
        ticket = self._active_ticket()
        result = validate_ticket(
            self._req(self.contractor_acc, self.contractor_profile),
            ValidateReq(qr_token=ticket.qr_token),
        )
        self.assertTrue(result.valid)

    def test_validate_by_member_role_rejected(self):
        ticket = self._active_ticket()
        result = validate_ticket(
            self._req(self.member_acc, self.member_profile),
            ValidateReq(qr_token=ticket.qr_token),
        )
        self.assertFalse(result.valid)
        self.assertIn('Not authorized', result.message)

    def test_validate_by_outsider_rejected(self):
        ticket = self._active_ticket()
        result = validate_ticket(
            self._req(self.outsider_acc, self.outsider_profile),
            ValidateReq(qr_token=ticket.qr_token),
        )
        self.assertFalse(result.valid)

    def test_get_ticket_establishment_validator_access(self):
        ticket = self._active_ticket()
        result = get_ticket(
            self._req(self.employee_acc, self.employee_profile, 'get'), ticket.id,
        )
        self.assertEqual(result.id, ticket.id)
        self.assertEqual(result.operator_name, self.est.name)


# ---------------------------------------------------------------------------
# Validity windows + agency (network-wide) tickets
# ---------------------------------------------------------------------------

class ValidityWindowTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.op_acc = _create_account(self.inst, 'operator', is_staff=True)
        self.op_profile = _create_profile(self.op_acc, self.inst, ln_address='op@ln.io')
        self.buyer_acc = _create_account(self.inst, 'buyer', is_staff=True)
        self.buyer_profile = _create_profile(self.buyer_acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()
        self.windowed_tt = TicketType.objects.create(
            category='TRANSIT', name='90min Ride', price_sats=100,
            validity_minutes=90, route=self.route, operator=self.op_profile,
        )
        self.oneshot_tt = TicketType.objects.create(
            category='TRANSIT', name='One Shot', price_sats=100,
            route=self.route, operator=self.op_profile,
        )

    def _op_req(self, method='post'):
        return _make_request(self.factory, self.op_acc, self.op_profile, method)

    def _ticket(self, tt, **kwargs):
        return Ticket.objects.create(
            ticket_type=tt, buyer=self.buyer_profile,
            status=kwargs.pop('status', Ticket.Status.ACTIVE), **kwargs,
        )

    def test_first_scan_activates_window(self):
        ticket = self._ticket(self.windowed_tt)
        result = validate_ticket(self._op_req(), ValidateReq(qr_token=ticket.qr_token))
        self.assertTrue(result.valid)
        self.assertIn('Valid until', result.message)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.VALIDATED)
        self.assertEqual(ticket.validation_count, 1)
        self.assertIsNotNone(ticket.used_at)
        expected = ticket.used_at + timedelta(minutes=90)
        self.assertAlmostEqual(
            ticket.valid_until.timestamp(), expected.timestamp(), delta=2,
        )

    def test_rescan_within_window_valid(self):
        ticket = self._ticket(
            self.windowed_tt, status=Ticket.Status.VALIDATED,
            valid_until=timezone.now() + timedelta(hours=1), validation_count=1,
        )
        result = validate_ticket(self._op_req(), ValidateReq(qr_token=ticket.qr_token))
        self.assertTrue(result.valid)
        self.assertEqual(result.validation_count, 2)
        ticket.refresh_from_db()
        self.assertEqual(ticket.validation_count, 2)
        self.assertEqual(ticket.status, Ticket.Status.VALIDATED)

    def test_scan_after_window_invalid(self):
        ticket = self._ticket(
            self.windowed_tt, status=Ticket.Status.VALIDATED,
            valid_until=timezone.now() - timedelta(minutes=1), validation_count=1,
        )
        result = validate_ticket(self._op_req(), ValidateReq(qr_token=ticket.qr_token))
        self.assertFalse(result.valid)
        self.assertIn('Validity window ended', result.message)
        ticket.refresh_from_db()
        self.assertEqual(ticket.validation_count, 1)  # not incremented

    def test_one_shot_unchanged(self):
        ticket = self._ticket(self.oneshot_tt)
        result = validate_ticket(self._op_req(), ValidateReq(qr_token=ticket.qr_token))
        self.assertTrue(result.valid)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.USED)
        result2 = validate_ticket(self._op_req(), ValidateReq(qr_token=ticket.qr_token))
        self.assertFalse(result2.valid)
        self.assertIn('Already used', result2.message)

    def test_create_agency_type(self):
        data = TicketTypeCreateReq(
            category='TRANSIT', name='Day Pass', price_sats=500,
            agency_id=self.agency.id, validity_minutes=1440,
        )
        result = create_ticket_type(self._op_req(), data)
        self.assertEqual(result.agency_id, self.agency.id)
        self.assertEqual(result.agency_name, self.agency.name)
        self.assertEqual(result.validity_minutes, 1440)
        self.assertIsNone(result.route_id)

    def test_create_transit_both_targets_rejected(self):
        data = TicketTypeCreateReq(
            category='TRANSIT', name='Bad', price_sats=100,
            route_id=self.route.id, agency_id=self.agency.id,
        )
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(self._op_req(), data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_zero_validity_rejected(self):
        data = TicketTypeCreateReq(
            category='TRANSIT', name='Bad', price_sats=100,
            route_id=self.route.id, validity_minutes=0,
        )
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(self._op_req(), data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_route_listing_includes_agency_types(self):
        TicketType.objects.create(
            category='TRANSIT', name='Network Pass', price_sats=500,
            agency=self.agency, operator=self.op_profile, validity_minutes=1440,
        )
        result = list_ticket_types(self._op_req('get'), route_id=self.route.id)
        names = {tt.name for tt in result}
        self.assertIn('90min Ride', names)
        self.assertIn('Network Pass', names)

    def test_update_validity_clear(self):
        result = update_ticket_type(
            self._op_req('put'), self.windowed_tt.id,
            TicketTypeUpdateReq(validity_minutes=0),
        )
        self.assertIsNone(result.validity_minutes)
        self.windowed_tt.refresh_from_db()
        self.assertIsNone(self.windowed_tt.validity_minutes)


# ---------------------------------------------------------------------------
# Operator dashboard (contexts, stats, CSV)
# ---------------------------------------------------------------------------

class OperatorDashboardTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.op_acc = _create_account(self.inst, 'operator', is_staff=True)
        self.op_profile = _create_profile(self.op_acc, self.inst, ln_address='op@ln.io')
        self.buyer_acc = _create_account(self.inst, 'buyer', is_staff=True)
        self.buyer_profile = _create_profile(self.buyer_acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()

        self.est = Establishment.objects.create(
            name='Bus Org', spark_address='sp1qorg',
        )
        self.mgr_acc = _create_account(self.inst, 'manager')
        self.mgr_profile = _create_profile(self.mgr_acc, self.inst)
        EstablishmentMembership.objects.create(
            profile=self.mgr_profile, establishment=self.est, role='OWNER',
        )

        # Personal type (op) + establishment type
        self.personal_tt = TicketType.objects.create(
            category='TRANSIT', name='Personal Ride', price_sats=100,
            route=self.route, operator=self.op_profile,
        )
        self.est_tt = TicketType.objects.create(
            category='TRANSIT', name='Org Ride', price_eur=Decimal('1.50'),
            price_sats=None, route=self.route,
            operator=self.op_profile, operator_establishment=self.est,
        )

        now = timezone.now()
        for _ in range(2):
            Ticket.objects.create(
                ticket_type=self.personal_tt, buyer=self.buyer_profile,
                status=Ticket.Status.ACTIVE, amount_due_sats=100,
                amount_paid_sats=100, paid_at=now,
            )
        Ticket.objects.create(
            ticket_type=self.est_tt, buyer=self.buyer_profile,
            status=Ticket.Status.USED, amount_due_sats=3000,
            amount_paid_sats=3000, price_eur=Decimal('1.50'), paid_at=now,
        )
        # Excluded: unpaid pending + old sale
        Ticket.objects.create(
            ticket_type=self.personal_tt, buyer=self.buyer_profile,
            status=Ticket.Status.PENDING_PAYMENT,
        )
        Ticket.objects.create(
            ticket_type=self.personal_tt, buyer=self.buyer_profile,
            status=Ticket.Status.ACTIVE, amount_paid_sats=100,
            paid_at=now - timedelta(days=100),
        )

    def _req(self, acc, profile):
        return _make_request(self.factory, acc, profile, 'get')

    def test_contexts_lists_personal_and_managed(self):
        result = operator_contexts(self._req(self.mgr_acc, self.mgr_profile))
        self.assertEqual(len(result), 2)
        self.assertIsNone(result[0].establishment_id)
        self.assertEqual(result[0].types_count, 0)
        self.assertEqual(result[1].establishment_id, self.est.id)
        self.assertEqual(result[1].name, 'Bus Org')
        self.assertEqual(result[1].types_count, 1)

    def test_stats_personal(self):
        result = operator_stats(self._req(self.op_acc, self.op_profile), days=30)
        self.assertEqual(result.total_sold, 2)
        self.assertEqual(result.revenue_sats, 200)
        self.assertEqual(result.revenue_eur, 0)
        self.assertEqual(len(result.daily), 1)
        self.assertEqual(result.daily[0].count, 2)
        self.assertEqual(len(result.by_type), 1)
        self.assertEqual(result.by_type[0].target, '1')  # route short_name

    def test_stats_personal_wide_range_includes_old(self):
        result = operator_stats(self._req(self.op_acc, self.op_profile), days=366)
        self.assertEqual(result.total_sold, 3)

    def test_stats_establishment_by_manager(self):
        result = operator_stats(
            self._req(self.mgr_acc, self.mgr_profile),
            days=30, establishment_id=self.est.id,
        )
        self.assertEqual(result.total_sold, 1)
        self.assertEqual(result.revenue_sats, 3000)
        self.assertEqual(result.revenue_eur, 1.5)

    def test_stats_establishment_non_manager_403(self):
        acc = _create_account(self.inst, 'rando')
        p = _create_profile(acc, self.inst)
        with self.assertRaises(HttpError) as ctx:
            operator_stats(self._req(acc, p), days=30, establishment_id=self.est.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_csv_export(self):
        response = operator_sales_csv(self._req(self.op_acc, self.op_profile), days=30)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        lines = content.strip().splitlines()
        self.assertEqual(len(lines), 3)  # header + 2 sales
        self.assertIn('paid_at', lines[0])
        self.assertIn('Personal Ride', content)

    def test_csv_establishment_non_manager_403(self):
        acc = _create_account(self.inst, 'rando2')
        p = _create_profile(acc, self.inst)
        with self.assertRaises(HttpError) as ctx:
            operator_sales_csv(self._req(acc, p), days=30, establishment_id=self.est.id)
        self.assertEqual(ctx.exception.status_code, 403)


# ---------------------------------------------------------------------------
# Signed QR + offline validation sync
# ---------------------------------------------------------------------------

class QrSigningTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.op_acc = _create_account(self.inst, 'operator', is_staff=True)
        self.op_profile = _create_profile(self.op_acc, self.inst, ln_address='op@ln.io')
        self.buyer_acc = _create_account(self.inst, 'buyer', is_staff=True)
        self.buyer_profile = _create_profile(self.buyer_acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()
        self.tt = TicketType.objects.create(
            category='TRANSIT', name='Windowed', price_sats=100,
            validity_minutes=90, concession_category='STUDENT',
            route=self.route, operator=self.op_profile,
        )
        self.ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile, status=Ticket.Status.ACTIVE,
        )

    def test_payload_format_and_signature(self):
        import base64
        import json
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        qr = build_qr_payload(self.ticket)
        prefix, payload_b64, sig_b64 = qr.split('.')
        self.assertEqual(prefix, QR_PREFIX)

        def unb64(s):
            return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))

        raw = unb64(payload_b64)
        payload = json.loads(raw)
        self.assertEqual(payload['tid'], self.ticket.id)
        self.assertEqual(payload['qr'], self.ticket.qr_token)
        self.assertEqual(payload['ty'], self.tt.id)
        self.assertEqual(payload['vm'], 90)
        self.assertEqual(payload['cc'], 'STUDENT')

        pub = Ed25519PublicKey.from_public_bytes(unb64(public_key_b64()))
        pub.verify(unb64(sig_b64), raw)  # raises on mismatch

    def test_ticket_out_includes_payload_for_active_only(self):
        req = _make_request(self.factory, self.buyer_acc, self.buyer_profile)
        result = get_ticket(req, self.ticket.id)
        self.assertTrue(result.qr_payload.startswith(QR_PREFIX + '.'))
        self.ticket.status = Ticket.Status.USED
        self.ticket.save()
        result = get_ticket(req, self.ticket.id)
        self.assertIsNone(result.qr_payload)

    def test_pubkey_endpoint(self):
        req = _make_request(self.factory, self.buyer_acc, self.buyer_profile)
        result = qr_pubkey(req)
        self.assertEqual(result['alg'], 'ed25519')
        self.assertTrue(result['key'])


class ValidateSyncTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.op_acc = _create_account(self.inst, 'operator', is_staff=True)
        self.op_profile = _create_profile(self.op_acc, self.inst, ln_address='op@ln.io')
        self.buyer_acc = _create_account(self.inst, 'buyer', is_staff=True)
        self.buyer_profile = _create_profile(self.buyer_acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()
        self.windowed_tt = TicketType.objects.create(
            category='TRANSIT', name='Windowed', price_sats=100,
            validity_minutes=90, route=self.route, operator=self.op_profile,
        )
        self.oneshot_tt = TicketType.objects.create(
            category='TRANSIT', name='OneShot', price_sats=100,
            route=self.route, operator=self.op_profile,
        )

    def _op_req(self):
        return _make_request(self.factory, self.op_acc, self.op_profile, 'post')

    def test_sync_retroactive_window(self):
        ticket = Ticket.objects.create(
            ticket_type=self.windowed_tt, buyer=self.buyer_profile,
            status=Ticket.Status.ACTIVE,
        )
        scanned = timezone.now() - timedelta(hours=2)
        results = validate_sync(self._op_req(), SyncReq(items=[
            SyncItem(qr_token=ticket.qr_token, scanned_at=scanned),
        ]))
        self.assertTrue(results[0].valid)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.VALIDATED)
        # Window anchored at the offline scan moment → already expired (90min < 2h)
        self.assertAlmostEqual(
            ticket.valid_until.timestamp(),
            (scanned + timedelta(minutes=90)).timestamp(), delta=2,
        )

    def test_sync_oneshot_double_scan(self):
        ticket = Ticket.objects.create(
            ticket_type=self.oneshot_tt, buyer=self.buyer_profile,
            status=Ticket.Status.ACTIVE,
        )
        now = timezone.now()
        results = validate_sync(self._op_req(), SyncReq(items=[
            SyncItem(qr_token=ticket.qr_token, scanned_at=now - timedelta(minutes=5)),
            SyncItem(qr_token=ticket.qr_token, scanned_at=now - timedelta(minutes=3)),
        ]))
        self.assertTrue(results[0].valid)
        self.assertFalse(results[1].valid)
        self.assertIn('Already used', results[1].message)

    def test_sync_orders_by_scanned_at(self):
        ticket = Ticket.objects.create(
            ticket_type=self.oneshot_tt, buyer=self.buyer_profile,
            status=Ticket.Status.ACTIVE,
        )
        now = timezone.now()
        # Later item listed first — sync must process oldest first
        results = validate_sync(self._op_req(), SyncReq(items=[
            SyncItem(qr_token=ticket.qr_token, scanned_at=now - timedelta(minutes=3)),
            SyncItem(qr_token=ticket.qr_token, scanned_at=now - timedelta(minutes=10)),
        ]))
        ticket.refresh_from_db()
        # used_at = the OLDEST scan
        self.assertAlmostEqual(
            ticket.used_at.timestamp(),
            (now - timedelta(minutes=10)).timestamp(), delta=2,
        )

    def test_sync_clamps_future_timestamp(self):
        ticket = Ticket.objects.create(
            ticket_type=self.windowed_tt, buyer=self.buyer_profile,
            status=Ticket.Status.ACTIVE,
        )
        results = validate_sync(self._op_req(), SyncReq(items=[
            SyncItem(qr_token=ticket.qr_token, scanned_at=timezone.now() + timedelta(days=2)),
        ]))
        self.assertTrue(results[0].valid)
        ticket.refresh_from_db()
        self.assertLessEqual(ticket.used_at, timezone.now())

    def test_sync_unauthorized_validator(self):
        ticket = Ticket.objects.create(
            ticket_type=self.oneshot_tt, buyer=self.buyer_profile,
            status=Ticket.Status.ACTIVE,
        )
        acc = _create_account(self.inst, 'rando')
        p = _create_profile(acc, self.inst)
        req = _make_request(self.factory, acc, p, 'post')
        results = validate_sync(req, SyncReq(items=[
            SyncItem(qr_token=ticket.qr_token, scanned_at=timezone.now()),
        ]))
        self.assertFalse(results[0].valid)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.ACTIVE)

    def test_sync_unknown_token(self):
        results = validate_sync(self._op_req(), SyncReq(items=[
            SyncItem(qr_token='f' * 64, scanned_at=timezone.now()),
        ]))
        self.assertFalse(results[0].valid)
        self.assertEqual(results[0].message, 'Unknown ticket')

    def test_validable_types(self):
        est = Establishment.objects.create(name='Org', spark_address='sp1q')
        est_tt = TicketType.objects.create(
            category='TRANSIT', name='Org Type', price_sats=100,
            route=self.route, operator=self.op_profile, operator_establishment=est,
        )
        emp_acc = _create_account(self.inst, 'emp')
        emp_profile = _create_profile(emp_acc, self.inst)
        EstablishmentMembership.objects.create(
            profile=emp_profile, establishment=est, role='EMPLOYEE',
        )
        req = _make_request(self.factory, emp_acc, emp_profile)
        result = validable_types(req)
        ids = {r.id for r in result}
        self.assertIn(est_tt.id, ids)
        self.assertNotIn(self.oneshot_tt.id, ids)  # personal type of someone else


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------

class RefundTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.op_acc = _create_account(self.inst, 'operator', is_staff=True)
        self.op_profile = _create_profile(self.op_acc, self.inst, ln_address='op@ln.io')
        self.buyer_acc = _create_account(self.inst, 'buyer', is_staff=True)
        self.buyer_profile = _create_profile(
            self.buyer_acc, self.inst, ln_address='buyer@ln.io',
        )
        self.place, self.ds, self.agency, self.route = _create_transit_chain()
        self.tt = TicketType.objects.create(
            category='TRANSIT', name='Refundable', price_sats=100,
            route=self.route, operator=self.op_profile, sold_count=1,
        )
        self.ticket = Ticket.objects.create(
            ticket_type=self.tt, buyer=self.buyer_profile,
            status=Ticket.Status.ACTIVE, amount_paid_sats=100,
            paid_at=timezone.now(),
        )

    def _buyer_req(self):
        return _make_request(self.factory, self.buyer_acc, self.buyer_profile, 'post')

    def _op_req(self):
        return _make_request(self.factory, self.op_acc, self.op_profile, 'post')

    def test_request_refund(self):
        result = request_refund(self._buyer_req(), self.ticket.id, RefundRequestReq(reason='Plans changed'))
        self.assertEqual(result.status, 'REFUND_REQUESTED')
        self.assertEqual(result.refund_reason, 'Plans changed')
        self.assertIsNotNone(result.refund_requested_at)
        self.assertIsNone(result.qr_payload)  # no QR while refund pending

    def test_request_refund_used_ticket_rejected(self):
        self.ticket.status = Ticket.Status.USED
        self.ticket.save()
        with self.assertRaises(HttpError) as ctx:
            request_refund(self._buyer_req(), self.ticket.id, RefundRequestReq())
        self.assertEqual(ctx.exception.status_code, 400)

    def test_request_refund_non_buyer_404(self):
        acc = _create_account(self.inst, 'other')
        p = _create_profile(acc, self.inst)
        req = _make_request(self.factory, acc, p, 'post')
        with self.assertRaises(HttpError) as ctx:
            request_refund(req, self.ticket.id, RefundRequestReq())
        self.assertEqual(ctx.exception.status_code, 404)

    def test_cancel_refund_request(self):
        request_refund(self._buyer_req(), self.ticket.id, RefundRequestReq(reason='x'))
        result = cancel_refund_request(self._buyer_req(), self.ticket.id)
        self.assertEqual(result.status, 'ACTIVE')
        self.assertEqual(result.refund_reason, '')

    def test_refund_requested_ticket_not_validatable(self):
        request_refund(self._buyer_req(), self.ticket.id, RefundRequestReq())
        result = validate_ticket(self._op_req(), ValidateReq(qr_token=self.ticket.qr_token))
        self.assertFalse(result.valid)
        self.assertIn('REFUND_REQUESTED', result.message)

    def test_resolve_refund(self):
        request_refund(self._buyer_req(), self.ticket.id, RefundRequestReq())
        result = resolve_refund(self._op_req(), self.ticket.id, RefundResolveReq(
            action='refund', payment_hash='ab' * 32,
        ))
        self.assertEqual(result.status, 'CANCELLED')
        self.assertIsNotNone(result.refunded_at)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.refund_payment_hash, 'ab' * 32)
        self.tt.refresh_from_db()
        self.assertEqual(self.tt.sold_count, 0)  # seat freed

    def test_resolve_reject(self):
        request_refund(self._buyer_req(), self.ticket.id, RefundRequestReq())
        result = resolve_refund(self._op_req(), self.ticket.id, RefundResolveReq(action='reject'))
        self.assertEqual(result.status, 'ACTIVE')
        self.tt.refresh_from_db()
        self.assertEqual(self.tt.sold_count, 1)  # unchanged

    def test_resolve_requires_manage(self):
        request_refund(self._buyer_req(), self.ticket.id, RefundRequestReq())
        acc = _create_account(self.inst, 'rando')
        p = _create_profile(acc, self.inst)
        req = _make_request(self.factory, acc, p, 'post')
        with self.assertRaises(HttpError) as ctx:
            resolve_refund(req, self.ticket.id, RefundResolveReq(action='refund'))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_resolve_invalid_action(self):
        request_refund(self._buyer_req(), self.ticket.id, RefundRequestReq())
        with self.assertRaises(HttpError) as ctx:
            resolve_refund(self._op_req(), self.ticket.id, RefundResolveReq(action='maybe'))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_operator_refunds_list(self):
        request_refund(self._buyer_req(), self.ticket.id, RefundRequestReq(reason='Plans changed'))
        req = _make_request(self.factory, self.op_acc, self.op_profile)
        result = operator_refunds(req)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticket_id, self.ticket.id)
        self.assertEqual(result[0].buyer_ln_address, 'buyer@ln.io')
        self.assertEqual(result[0].amount_paid_sats, 100)
        self.assertEqual(result[0].reason, 'Plans changed')


class ConcessionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.op_acc = _create_account(self.inst, 'operator', is_staff=True)
        self.op_profile = _create_profile(self.op_acc, self.inst, ln_address='op@ln.io')
        self.buyer_acc = _create_account(self.inst, 'buyer', is_staff=True)
        self.buyer_profile = _create_profile(self.buyer_acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()

    def _op_req(self, method='post'):
        return _make_request(self.factory, self.op_acc, self.op_profile, method)

    def test_create_with_concession(self):
        data = TicketTypeCreateReq(
            category='TRANSIT', name='Student', price_sats=50,
            route_id=self.route.id, concession_category='STUDENT',
        )
        result = create_ticket_type(self._op_req(), data)
        self.assertEqual(result.concession_category, 'STUDENT')

    def test_create_invalid_concession_rejected(self):
        data = TicketTypeCreateReq(
            category='TRANSIT', name='Bad', price_sats=50,
            route_id=self.route.id, concession_category='ALIEN',
        )
        with self.assertRaises(HttpError) as ctx:
            create_ticket_type(self._op_req(), data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_validate_result_carries_concession(self):
        tt = TicketType.objects.create(
            category='TRANSIT', name='Senior', price_sats=50,
            route=self.route, operator=self.op_profile, concession_category='SENIOR',
        )
        ticket = Ticket.objects.create(
            ticket_type=tt, buyer=self.buyer_profile, status=Ticket.Status.ACTIVE,
        )
        result = validate_ticket(self._op_req(), ValidateReq(qr_token=ticket.qr_token))
        self.assertTrue(result.valid)
        self.assertEqual(result.concession_category, 'SENIOR')

    def test_update_clears_concession(self):
        tt = TicketType.objects.create(
            category='TRANSIT', name='Student', price_sats=50,
            route=self.route, operator=self.op_profile, concession_category='STUDENT',
        )
        result = update_ticket_type(
            self._op_req('put'), tt.id, TicketTypeUpdateReq(concession_category=''),
        )
        self.assertEqual(result.concession_category, '')
