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

from django.test import TestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from ninja.errors import HttpError

from identity.models import Account, Profile
from core.models import Instance
from geo.models import Place, TransitDataSource, Agency, Route, Event
from tickets.models import Ticket, TicketType
from tickets.api import (
    list_ticket_types, get_ticket_type, create_ticket_type,
    update_ticket_type, delete_ticket_type,
    purchase_ticket, confirm_payment, sign_ticket,
    my_tickets, get_ticket, validate_ticket,
    TicketTypeCreateReq, TicketTypeUpdateReq,
    PurchaseReq, ConfirmReq, SignReq, ValidateReq,
)


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
