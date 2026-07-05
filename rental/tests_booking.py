"""
Tests for the rental booking layer.

Invariants that must never break:
- No double-booking: overlapping live bookings rejected (API 409 + DB constraint backstop)
- Window sanity: past / out-of-window / misaligned-slot rejected
- Completion returns the asset to availability (does NOT deactivate the item)
- Only the item manager (establishment role) or P2P owner can configure a bookable
- Price is snapshotted from the rent pricing option
"""
from datetime import timedelta, datetime, date, time
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone
from django.db import IntegrityError, transaction
from ninja.errors import HttpError

from identity.models import Account, Profile
from core.models import Instance
from market.models import Item
from rental.models import Bookable, Availability, AvailabilityException, Booking
from parahub.endpoints import rental as api


def _req(profile):
    return SimpleNamespace(auth_profile=profile)


def _book(req, data):
    """create_booking → the primary BookingResponse (unwraps the series envelope).
    Tests that expect a rejection still get the raised HttpError — the create
    call raises before the result is indexed."""
    fn = api.create_booking
    return fn(req, data).bookings[0]


class BookingTestBase(TestCase):
    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.owner = self._profile('alice')
        self.renter = self._profile('bob')
        self.stranger = self._profile('carol')

        self.item = Item.objects.create(
            owner=self.owner, title='Moto', type=Item.ItemType.CREDIT,
            pricing_options=[{'type': 'rent', 'amount': 25, 'currency': 'EUR', 'unit': 'day'}],
        )

    def _profile(self, name):
        acc = Account.objects.create_user(
            username=name, email=f'{name}@test.parahub.io',
            password='x', instance=self.instance)
        return Profile.objects.create(
            account=acc, instance=self.instance, local_name=name,
            display_name=name.title(), is_primary=True,
            profile_type=Profile.ProfileType.PERSONAL)

    def _range_bookable(self):
        b = Bookable.objects.create(item=self.item, booking_mode=Bookable.Mode.RANGE,
                                    confirmation=Bookable.Confirmation.AUTO)
        Availability.objects.create(bookable=b, start=time(0, 0), stop=time(23, 59))
        return b


class DoubleBookingTest(BookingTestBase):
    def test_api_rejects_overlap(self):
        self._range_bookable()
        now = timezone.now()
        _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=now + timedelta(days=1), end=now + timedelta(days=3)))
        with self.assertRaises(HttpError) as ctx:
            _book(_req(self.renter), api.BookingCreateRequest(
                item_id=self.item.id, start=now + timedelta(days=2), end=now + timedelta(days=4)))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_db_constraint_backstop(self):
        """The exclusion constraint rejects overlap even bypassing the API."""
        b = self._range_bookable()
        now = timezone.now()
        Booking.objects.create(bookable=b, renter=self.renter, start=now + timedelta(days=1),
                               end=now + timedelta(days=3), status=Booking.Status.CONFIRMED)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Booking.objects.create(bookable=b, renter=self.renter,
                                       start=now + timedelta(days=2), end=now + timedelta(days=4),
                                       status=Booking.Status.CONFIRMED)

    def test_adjacent_ok(self):
        """End-exclusive: a booking starting exactly when another ends is allowed."""
        b = self._range_bookable()
        now = timezone.now()
        Booking.objects.create(bookable=b, renter=self.renter, start=now + timedelta(days=1),
                               end=now + timedelta(days=3), status=Booking.Status.CONFIRMED)
        Booking.objects.create(bookable=b, renter=self.renter, start=now + timedelta(days=3),
                               end=now + timedelta(days=5), status=Booking.Status.CONFIRMED)

    def test_cancelled_does_not_block(self):
        b = self._range_bookable()
        now = timezone.now()
        Booking.objects.create(bookable=b, renter=self.renter, start=now + timedelta(days=1),
                               end=now + timedelta(days=3), status=Booking.Status.CANCELLED)
        # overlapping live booking is fine because the other is cancelled
        _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=now + timedelta(days=2), end=now + timedelta(days=4)))


class WindowValidationTest(BookingTestBase):
    def test_past_rejected(self):
        self._range_bookable()
        now = timezone.now()
        with self.assertRaises(HttpError) as ctx:
            _book(_req(self.renter), api.BookingCreateRequest(
                item_id=self.item.id, start=now - timedelta(days=2), end=now - timedelta(days=1)))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_end_before_start_rejected(self):
        self._range_bookable()
        now = timezone.now()
        with self.assertRaises(HttpError):
            _book(_req(self.renter), api.BookingCreateRequest(
                item_id=self.item.id, start=now + timedelta(days=3), end=now + timedelta(days=1)))

    def test_misaligned_slot_rejected(self):
        b = Bookable.objects.create(item=self.item, booking_mode=Bookable.Mode.SLOTS,
                                    confirmation=Bookable.Confirmation.AUTO)
        Availability.objects.create(bookable=b, start=time(9, 0), stop=time(18, 0), slot_minutes=60)
        tz = ZoneInfo('Europe/Lisbon')
        tomorrow = (timezone.now().astimezone(tz) + timedelta(days=1)).date()
        slot_start = datetime.combine(tomorrow, time(10, 0), tzinfo=tz)
        # aligned → ok
        _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=slot_start, end=slot_start + timedelta(hours=1)))
        # misaligned (shifted 13 min) → 400
        with self.assertRaises(HttpError) as ctx:
            _book(_req(self.renter), api.BookingCreateRequest(
                item_id=self.item.id, start=slot_start + timedelta(minutes=13),
                end=slot_start + timedelta(minutes=73)))
        self.assertEqual(ctx.exception.status_code, 400)


class CompletionTest(BookingTestBase):
    def test_completion_keeps_item_active(self):
        self._range_bookable()
        now = timezone.now()
        bk = _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=now + timedelta(days=1), end=now + timedelta(days=2)))
        api.complete_booking(_req(self.owner), bk.id)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_active)  # asset returns to availability, not consumed

    def test_price_snapshot(self):
        self._range_bookable()
        now = timezone.now()
        bk = _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=now + timedelta(days=1), end=now + timedelta(days=3)))
        self.assertEqual(str(bk.price_total), '50')  # 25/day * 2 days
        self.assertEqual(bk.currency, 'EUR')


class PermissionTest(BookingTestBase):
    def test_stranger_cannot_configure_bookable(self):
        with self.assertRaises(HttpError) as ctx:
            api.create_bookable(_req(self.stranger), api.BookableCreateRequest(item_id=self.item.id))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_p2p_owner_can_configure(self):
        resp = api.create_bookable(_req(self.owner), api.BookableCreateRequest(item_id=self.item.id))
        self.assertEqual(resp.item_id, self.item.id)

    def test_renter_can_cancel_own(self):
        self._range_bookable()
        now = timezone.now()
        bk = _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=now + timedelta(days=1), end=now + timedelta(days=2)))
        resp = api.cancel_booking(_req(self.renter), bk.id)
        self.assertEqual(resp.status, 'CANCELLED')

    def test_cancel_records_note_and_actor(self):
        self._range_bookable()
        now = timezone.now()
        bk = _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=now + timedelta(days=1), end=now + timedelta(days=2)))
        resp = api.cancel_booking(_req(self.renter), bk.id,
                                  api.BookingCancelRequest(note="  changed my plans  "))
        self.assertEqual(resp.status, 'CANCELLED')
        self.assertEqual(resp.cancel_note, "changed my plans")   # trimmed
        self.assertEqual(resp.cancelled_by_id, self.renter.id)
        # Owner cancelling records the owner as the actor
        bk2 = _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=now + timedelta(days=3), end=now + timedelta(days=4)))
        resp2 = api.cancel_booking(_req(self.owner), bk2.id,
                                   api.BookingCancelRequest(note="asset unavailable"))
        self.assertEqual(resp2.cancelled_by_id, self.owner.id)
        self.assertEqual(resp2.cancel_note, "asset unavailable")

    def test_stranger_cannot_complete(self):
        self._range_bookable()
        now = timezone.now()
        bk = _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=now + timedelta(days=1), end=now + timedelta(days=2)))
        with self.assertRaises(HttpError) as ctx:
            api.complete_booking(_req(self.stranger), bk.id)
        self.assertEqual(ctx.exception.status_code, 403)


class RentalContextTest(BookingTestBase):
    def test_owner_can_manage_before_setup(self):
        ctx = api.rental_context(_req(self.owner), self.item.id)
        self.assertTrue(ctx.can_manage)
        self.assertTrue(ctx.has_rent_option)
        self.assertFalse(ctx.is_bookable)
        self.assertIsNone(ctx.bookable)

    def test_stranger_cannot_manage(self):
        ctx = api.rental_context(_req(self.stranger), self.item.id)
        self.assertFalse(ctx.can_manage)
        self.assertTrue(ctx.has_rent_option)

    def test_context_reflects_bookable(self):
        self._range_bookable()
        ctx = api.rental_context(_req(self.owner), self.item.id)
        self.assertTrue(ctx.is_bookable)
        self.assertIsNotNone(ctx.bookable)

    def test_no_rent_option_flagged(self):
        item = Item.objects.create(owner=self.owner, title='Not for rent',
                                   type=Item.ItemType.CREDIT,
                                   pricing_options=[{'type': 'sale', 'amount': 10, 'currency': 'EUR'}])
        ctx = api.rental_context(_req(self.owner), item.id)
        self.assertFalse(ctx.has_rent_option)


class SlugResolutionTest(BookingTestBase):
    """The public market URL addresses items by slug, not ULID — rental
    endpoints must resolve either (regression: /rental/{slug} 404'd)."""
    def test_context_by_slug(self):
        ctx = api.rental_context(_req(self.owner), self.item.slug)
        self.assertEqual(ctx.item_id, self.item.id)

    def test_availability_by_slug(self):
        self._range_bookable()
        resp = api.get_availability(_req(self.renter), self.item.slug)
        self.assertEqual(resp.bookable.item_id, self.item.id)

    def test_booking_by_slug(self):
        self._range_bookable()
        now = timezone.now()
        bk = _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.slug, start=now + timedelta(days=1), end=now + timedelta(days=2)))
        self.assertEqual(bk.item_id, self.item.id)


class NotificationWiringTest(BookingTestBase):
    """Each booking mutation schedules the right push to the right counterpart.
    `_notify_async` is patched so we assert the wiring (which fn, which account)
    without exercising the on_commit/thread/push-delivery plumbing."""

    def _request_bookable(self):
        b = Bookable.objects.create(item=self.item, booking_mode=Bookable.Mode.RANGE,
                                    confirmation=Bookable.Confirmation.REQUEST)
        Availability.objects.create(bookable=b, start=time(0, 0), stop=time(23, 59))
        return b

    def test_create_notifies_owner(self):
        self._range_bookable()
        now = timezone.now()
        with patch.object(api, '_notify_async') as mock_async:
            _book(_req(self.renter), api.BookingCreateRequest(
                item_id=self.item.id, start=now + timedelta(days=1), end=now + timedelta(days=2)))
        self.assertEqual(len(mock_async.call_args_list), 1)
        fn, acct, _bk = mock_async.call_args_list[0].args
        self.assertIs(fn, api.notify_new_booking)
        self.assertEqual(acct.id, self.owner.account_id)

    def test_confirm_notifies_renter(self):
        self._request_bookable()
        now = timezone.now()
        bk = _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=now + timedelta(days=1), end=now + timedelta(days=2)))
        self.assertEqual(bk.status, 'REQUESTED')
        with patch.object(api, '_notify_async') as mock_async:
            api.confirm_booking(_req(self.owner), bk.id)
        fn, acct, _bk = mock_async.call_args_list[0].args
        self.assertIs(fn, api.notify_booking_confirmed)
        self.assertEqual(acct.id, self.renter.account_id)

    def test_renter_cancel_notifies_owner(self):
        self._range_bookable()
        now = timezone.now()
        bk = _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=now + timedelta(days=1), end=now + timedelta(days=2)))
        with patch.object(api, '_notify_async') as mock_async:
            api.cancel_booking(_req(self.renter), bk.id, api.BookingCancelRequest(note=""))
        fn, acct, _bk = mock_async.call_args_list[0].args
        self.assertIs(fn, api.notify_booking_cancelled)
        self.assertEqual(acct.id, self.owner.account_id)

    def test_owner_cancel_notifies_renter(self):
        self._range_bookable()
        now = timezone.now()
        bk = _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=now + timedelta(days=1), end=now + timedelta(days=2)))
        with patch.object(api, '_notify_async') as mock_async:
            api.cancel_booking(_req(self.owner), bk.id, api.BookingCancelRequest(note="x"))
        fn, acct, _bk = mock_async.call_args_list[0].args
        self.assertIs(fn, api.notify_booking_cancelled)
        self.assertEqual(acct.id, self.renter.account_id)


class NotificationServiceTest(BookingTestBase):
    """The notify_* helpers build the right push and honour prefs/language."""

    def _booking(self, status='REQUESTED'):
        b = self._range_bookable()
        now = timezone.now()
        return Booking.objects.create(
            bookable=b, renter=self.renter, created_by=self.renter,
            start=now + timedelta(days=1), end=now + timedelta(days=2),
            status=status, currency='EUR', mode='RANGE', unit='day')

    @patch('notifications.services.send_push_notification')
    def test_new_booking_push(self, mock_send):
        from notifications.services import notify_new_booking
        bk = self._booking('REQUESTED')
        notify_new_booking(self.owner.account, bk)
        self.assertTrue(mock_send.called)
        args, kwargs = mock_send.call_args
        self.assertEqual(args[0], self.owner.account)
        self.assertIn('/rental/', kwargs['url'])
        self.assertEqual(kwargs['data']['type'], 'new_booking')

    @patch('notifications.services.send_push_notification')
    def test_pref_disabled_skips(self, mock_send):
        from notifications.services import notify_new_booking
        self.owner.notification_prefs = {'rental': False}
        self.owner.save(update_fields=['notification_prefs'])
        notify_new_booking(self.owner.account, self._booking('REQUESTED'))
        self.assertFalse(mock_send.called)

    @patch('notifications.services.send_push_notification')
    def test_confirmed_language_ru(self, mock_send):
        from notifications.services import notify_booking_confirmed
        self.renter.preferred_language = 'ru'
        self.renter.save(update_fields=['preferred_language'])
        notify_booking_confirmed(self.renter.account, self._booking('CONFIRMED'))
        args, kwargs = mock_send.call_args
        self.assertEqual(args[1], 'Бронь подтверждена')
        self.assertEqual(kwargs['url'], '/market/my?tab=bookings')

    @patch('notifications.services.send_push_notification')
    def test_cancelled_direction(self, mock_send):
        from notifications.services import notify_booking_cancelled
        bk = self._booking('CANCELLED')
        bk.cancel_note = 'maintenance'
        # owner cancelled → renter is told, lands on their bookings list
        notify_booking_cancelled(self.renter.account, bk)
        renter_call = mock_send.call_args
        self.assertEqual(renter_call.kwargs['url'], '/market/my?tab=bookings')
        self.assertIn('maintenance', renter_call.args[2])  # reason appended to body
        # renter cancelled → a manager is told, lands on the item inbox
        notify_booking_cancelled(self.owner.account, bk)
        self.assertIn('/rental/', mock_send.call_args.kwargs['url'])


class BadgeEndpointTest(BookingTestBase):
    """pending-count + incoming inbox aggregate across managed items."""

    def _two_live(self):
        b = self._range_bookable()
        now = timezone.now()
        Booking.objects.create(bookable=b, renter=self.renter,
                               start=now + timedelta(days=1), end=now + timedelta(days=2),
                               status=Booking.Status.REQUESTED)
        Booking.objects.create(bookable=b, renter=self.renter,
                               start=now + timedelta(days=3), end=now + timedelta(days=4),
                               status=Booking.Status.CONFIRMED)

    def test_pending_count_only_requested_for_manager(self):
        self._two_live()
        self.assertEqual(api.pending_count(_req(self.owner))['count'], 1)
        self.assertEqual(api.pending_count(_req(self.stranger))['count'], 0)

    def test_incoming_lists_live_requested_first(self):
        self._two_live()
        res = api.incoming_bookings(_req(self.owner))
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].status, 'REQUESTED')
        self.assertEqual(api.incoming_bookings(_req(self.stranger)), [])


class RecurringBookingTest(BookingTestBase):
    """Recurring series (`weekly`) materialize independent,
    conflict-safe occurrences sharing a recurrence_group."""

    def _weekly(self, profile, days_ahead=1, repeat=3, recurrence='WEEKLY'):
        now = timezone.now()
        s = now + timedelta(days=days_ahead)
        return api.create_booking(_req(profile), api.BookingCreateRequest(
            item_id=self.item.id, start=s, end=s + timedelta(hours=2),
            recurrence=recurrence, repeat=repeat))

    def test_add_months_clamps_day(self):
        d = datetime(2026, 1, 31, 10, 0)
        self.assertEqual(api._add_months(d, 1), datetime(2026, 2, 28, 10, 0))  # no Feb 31

    def test_weekly_series_materializes(self):
        self._range_bookable()
        env = self._weekly(self.renter, repeat=3)
        self.assertEqual(len(env.bookings), 3)
        self.assertEqual(env.skipped, [])
        groups = {b.recurrence_group for b in env.bookings}
        self.assertEqual(len(groups), 1)
        self.assertTrue(next(iter(groups)))               # non-empty shared group
        starts = sorted(b.start for b in env.bookings)
        self.assertEqual((starts[1] - starts[0]).days, 7)  # 7 days apart
        self.assertEqual((starts[2] - starts[1]).days, 7)

    def test_single_has_no_group(self):
        self._range_bookable()
        env = self._weekly(self.renter, repeat=1)          # repeat=1 → standalone
        self.assertEqual(len(env.bookings), 1)
        self.assertEqual(env.bookings[0].recurrence_group, '')

    def test_best_effort_skips_occupied_occurrence(self):
        b = self._range_bookable()
        now = timezone.now()
        s = now + timedelta(days=1)
        # occupy the 2nd weekly occurrence exactly (compute it the same way)
        windows = list(api._occurrence_windows(b, s, s + timedelta(hours=2), 'WEEKLY', 3))
        s2, e2 = windows[1]
        Booking.objects.create(bookable=b, renter=self.stranger, start=s2, end=e2,
                               status=Booking.Status.CONFIRMED)
        env = api.create_booking(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=s, end=s + timedelta(hours=2),
            recurrence='WEEKLY', repeat=3))
        self.assertEqual(len(env.bookings), 2)             # anchor + 3rd
        self.assertEqual(len(env.skipped), 1)
        self.assertEqual(env.skipped[0].reason, 'occupied')

    def test_anchor_clash_is_hard_error(self):
        b = self._range_bookable()
        now = timezone.now()
        s = now + timedelta(days=1)
        Booking.objects.create(bookable=b, renter=self.stranger, start=s, end=s + timedelta(hours=2),
                               status=Booking.Status.CONFIRMED)
        with self.assertRaises(HttpError) as ctx:                       # anchor occupied → whole request fails
            api.create_booking(_req(self.renter), api.BookingCreateRequest(
                item_id=self.item.id, start=s, end=s + timedelta(hours=2),
                recurrence='WEEKLY', repeat=3))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_repeat_clamped_to_max(self):
        self._range_bookable()
        env = self._weekly(self.renter, repeat=999)        # clamp to MAX_REPEAT, rest skipped (out of window)
        self.assertEqual(len(env.bookings) + len(env.skipped), api.MAX_REPEAT)
        self.assertTrue(any(s.reason == 'outside_window' for s in env.skipped))

    def test_cancel_series_cancels_this_and_future(self):
        self._range_bookable()
        env = self._weekly(self.renter, repeat=3)
        bs = sorted(env.bookings, key=lambda x: x.start)
        api.cancel_booking(_req(self.renter), bs[1].id, api.BookingCancelRequest(series=True))
        self.assertEqual(Booking.objects.get(id=bs[0].id).status, 'CONFIRMED')   # earlier untouched
        self.assertEqual(Booking.objects.get(id=bs[1].id).status, 'CANCELLED')
        self.assertEqual(Booking.objects.get(id=bs[2].id).status, 'CANCELLED')   # future swept

    def test_cancel_single_leaves_series(self):
        self._range_bookable()
        env = self._weekly(self.renter, repeat=3)
        bs = sorted(env.bookings, key=lambda x: x.start)
        api.cancel_booking(_req(self.renter), bs[1].id)    # series defaults False
        self.assertEqual(Booking.objects.get(id=bs[0].id).status, 'CONFIRMED')
        self.assertEqual(Booking.objects.get(id=bs[1].id).status, 'CANCELLED')
        self.assertEqual(Booking.objects.get(id=bs[2].id).status, 'CONFIRMED')   # rest survive

    def test_one_push_per_series(self):
        self._range_bookable()
        with patch.object(api, '_notify_async') as mock_async:
            self._weekly(self.renter, repeat=3)
        self.assertEqual(len(mock_async.call_args_list), 1)   # one push (anchor), not three
        self.assertIs(mock_async.call_args_list[0].args[0], api.notify_new_booking)


class RentalBoardTest(BookingTestBase):
    """The per-establishment rental board lists only that org's bookable items."""

    def _est_with_items(self):
        from geo.models import Establishment
        est = Establishment.objects.create(name='Coworking X', owner=self.owner)
        for i, mode in enumerate([Bookable.Mode.SLOTS, Bookable.Mode.RANGE]):
            it = Item.objects.create(
                owner=self.owner, establishment=est, title=f'Room {i}',
                type=Item.ItemType.CREDIT,
                pricing_options=[{'type': 'rent', 'amount': 20 + i, 'currency': 'EUR',
                                  'unit': 'hour' if mode == Bookable.Mode.SLOTS else 'day'}])
            b = Bookable.objects.create(item=it, booking_mode=mode)
            Availability.objects.create(bookable=b, start=time(9, 0), stop=time(18, 0), slot_minutes=60)
        # a non-bookable item on the same establishment → excluded from the board
        Item.objects.create(owner=self.owner, establishment=est, title='Just for sale',
                            type=Item.ItemType.CREDIT,
                            pricing_options=[{'type': 'sale', 'amount': 5, 'currency': 'EUR'}])
        return est

    def test_board_lists_only_bookable_items(self):
        est = self._est_with_items()
        resp = api.establishment_board(_req(self.owner), est.id)
        self.assertEqual({i.title for i in resp.items}, {'Room 0', 'Room 1'})
        self.assertTrue(resp.can_manage)                 # owner manages
        self.assertEqual(resp.owner.kind, 'establishment')
        self.assertEqual(resp.owner.name, 'Coworking X')

    def test_board_by_slug_visible_to_all(self):
        est = self._est_with_items()
        resp = api.establishment_board(_req(self.stranger), est.slug)
        self.assertEqual(len(resp.items), 2)             # renter-facing → visible
        self.assertFalse(resp.can_manage)                # but stranger can't manage

    def test_board_404(self):
        with self.assertRaises(HttpError) as ctx:
            api.establishment_board(_req(self.owner), 'nonexistent')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_board_includes_establishment_summary(self):
        """The board carries a compact company profile so the page is a
        self-contained, shareable booking landing."""
        est = self._est_with_items()
        est.description = 'We rent rooms'
        est.website = 'https://coworking.example'
        est.save(update_fields=['description', 'website'])
        resp = api.establishment_board(_req(self.owner), est.id)
        self.assertIsNotNone(resp.owner)
        self.assertEqual(resp.owner.id, est.id)
        self.assertEqual(resp.owner.name, 'Coworking X')
        self.assertEqual(resp.owner.slug, est.slug)
        self.assertEqual(resp.owner.description, 'We rent rooms')
        self.assertEqual(resp.owner.website, 'https://coworking.example')

    def test_board_anonymous_can_read(self):
        """No auth_profile (anonymous via OptionalProfileAuth) → still gets the
        inventory + company summary, but can_manage is False."""
        from types import SimpleNamespace
        est = self._est_with_items()
        resp = api.establishment_board(SimpleNamespace(auth_profile=None), est.slug)
        self.assertEqual(len(resp.items), 2)
        self.assertFalse(resp.can_manage)
        self.assertIsNotNone(resp.owner)
        self.assertEqual(resp.owner.name, 'Coworking X')


class ProfileBoardTest(BookingTestBase):
    """The person storefront: the owner board generalized from establishments to
    profiles. A single P2P item is just this board focused on n=1."""

    def test_board_lists_owners_p2p_items(self):
        self._range_bookable()  # makes self.item (owner=alice, est=None) bookable
        resp = api.profile_board(_req(self.owner), self.owner.id)
        self.assertEqual(resp.owner.kind, 'profile')
        self.assertEqual(resp.owner.name, self.owner.display_name)
        self.assertEqual(resp.owner.slug, self.owner.local_name)
        self.assertTrue(resp.can_manage)                 # owner manages own board
        self.assertEqual({i.title for i in resp.items}, {'Moto'})

    def test_board_by_local_name_anonymous(self):
        self._range_bookable()
        resp = api.profile_board(SimpleNamespace(auth_profile=None), self.owner.local_name)
        self.assertEqual({i.title for i in resp.items}, {'Moto'})
        self.assertFalse(resp.can_manage)               # anonymous can't manage

    def test_board_excludes_org_posted_items(self):
        """An item alice posts on behalf of an org belongs to that org's board,
        not her personal storefront."""
        from geo.models import Establishment
        self._range_bookable()                          # her own Moto → included
        est = Establishment.objects.create(name='Org X', owner=self.owner)
        org_item = Item.objects.create(
            owner=self.owner, establishment=est, title='Org Room',
            type=Item.ItemType.CREDIT,
            pricing_options=[{'type': 'rent', 'amount': 30, 'currency': 'EUR', 'unit': 'day'}])
        Bookable.objects.create(item=org_item, booking_mode=Bookable.Mode.RANGE)
        resp = api.profile_board(_req(self.owner), self.owner.id)
        self.assertEqual({i.title for i in resp.items}, {'Moto'})   # org item excluded

    def test_board_hidden_when_not_publicly_linked(self):
        """A non-public profile's board is hidden from others but visible to the
        owner (mirrors get_public_profile's is_publicly_linked gate)."""
        self._range_bookable()
        self.owner.is_publicly_linked = False
        self.owner.save(update_fields=['is_publicly_linked'])
        with self.assertRaises(HttpError) as ctx:
            api.profile_board(_req(self.stranger), self.owner.local_name)
        self.assertEqual(ctx.exception.status_code, 404)
        with self.assertRaises(HttpError):
            api.profile_board(SimpleNamespace(auth_profile=None), self.owner.local_name)
        # owner still sees their own board
        resp = api.profile_board(_req(self.owner), self.owner.id)
        self.assertTrue(resp.can_manage)

    def test_board_404(self):
        with self.assertRaises(HttpError) as ctx:
            api.profile_board(_req(self.owner), 'nonexistent')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_board_hides_registered_item_from_anonymous(self):
        """A REGISTERED bookable is absent from the anonymous storefront but
        present for any signed-in viewer (and the owner)."""
        self._range_bookable()
        self.item.visibility = 'REGISTERED'
        self.item.save(update_fields=['visibility'])

        anon = api.profile_board(SimpleNamespace(auth_profile=None), self.owner.local_name)
        self.assertEqual({i.title for i in anon.items}, set())          # hidden from anon

        signed_in = api.profile_board(_req(self.renter), self.owner.local_name)
        self.assertEqual({i.title for i in signed_in.items}, {'Moto'})  # any signed-in viewer

        owner_view = api.profile_board(_req(self.owner), self.owner.id)
        self.assertEqual({i.title for i in owner_view.items}, {'Moto'})  # owner always


class WalkInBookingTest(BookingTestBase):
    """Owner / manager books for an offline (walk-in / phone-in) client: there
    is no platform renter, it is auto-confirmed, it blocks the slot like any
    booking, and it never clutters the owner's own 'my bookings'."""

    def _walk_in(self, req, **kw):
        now = timezone.now()
        return _book(req, api.BookingCreateRequest(
            item_id=self.item.id,
            start=kw.get('start', now + timedelta(days=1)),
            end=kw.get('end', now + timedelta(days=2)),
            external_renter_name=kw.get('name', 'Carlos Sousa'),
            external_renter_phone=kw.get('phone', '+351 912 345 678'),
            msg=kw.get('msg', '')))

    def test_owner_creates_walk_in(self):
        self._range_bookable()
        bk = self._walk_in(_req(self.owner))
        self.assertIsNone(bk.renter_id)
        self.assertTrue(bk.is_walk_in)
        self.assertEqual(bk.status, 'CONFIRMED')          # auto-confirmed
        self.assertEqual(bk.renter_name, 'Carlos Sousa')  # external name surfaced
        self.assertEqual(bk.client_phone, '+351 912 345 678')
        row = Booking.objects.get(id=bk.id)
        self.assertIsNone(row.renter_id)
        self.assertEqual(row.external_renter_name, 'Carlos Sousa')
        self.assertEqual(row.created_by_id, self.owner.id)  # manager is recorded

    def test_walk_in_blocks_slot(self):
        self._range_bookable()
        now = timezone.now()
        self._walk_in(_req(self.owner), start=now + timedelta(days=1), end=now + timedelta(days=3))
        with self.assertRaises(HttpError) as ctx:
            _book(_req(self.renter), api.BookingCreateRequest(
                item_id=self.item.id, start=now + timedelta(days=2), end=now + timedelta(days=4)))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_walk_in_not_in_owner_mine(self):
        """A walk-in has no renter, so it never shows in the owner's renter log."""
        self._range_bookable()
        self._walk_in(_req(self.owner))
        self.assertEqual(api.my_bookings(_req(self.owner)), [])

    def test_walk_in_in_inbox_and_incoming(self):
        self._range_bookable()
        self._walk_in(_req(self.owner), name='Phone Client')
        inbox = api.bookings_inbox(_req(self.owner), self.item.id)
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0].renter_name, 'Phone Client')
        self.assertTrue(inbox[0].is_walk_in)
        incoming = api.incoming_bookings(_req(self.owner))
        self.assertEqual(len(incoming), 1)
        self.assertEqual(incoming[0].renter_name, 'Phone Client')

    def test_stranger_cannot_create_walk_in(self):
        self._range_bookable()
        with self.assertRaises(HttpError) as ctx:
            self._walk_in(_req(self.stranger))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_walk_in_auto_confirmed_in_request_mode(self):
        """Even on a REQUEST-mode bookable, the owner-entered walk-in is
        confirmed outright — the owner is the approver."""
        b = Bookable.objects.create(item=self.item, booking_mode=Bookable.Mode.RANGE,
                                    confirmation=Bookable.Confirmation.REQUEST)
        Availability.objects.create(bookable=b, start=time(0, 0), stop=time(23, 59))
        bk = self._walk_in(_req(self.owner))
        self.assertEqual(bk.status, 'CONFIRMED')

    def test_manager_can_cancel_walk_in(self):
        """Cancelling a renterless walk-in must not crash on the null renter."""
        self._range_bookable()
        bk = self._walk_in(_req(self.owner))
        resp = api.cancel_booking(_req(self.owner), bk.id)
        self.assertEqual(resp.status, 'CANCELLED')

    def test_renter_name_helper_handles_walk_in(self):
        from notifications.services import _renter_name
        self._range_bookable()
        bk = self._walk_in(_req(self.owner), name='Walk-In Wanda')
        self.assertEqual(_renter_name(Booking.objects.get(id=bk.id)), 'Walk-In Wanda')

    def test_normal_booking_is_not_walk_in(self):
        self._range_bookable()
        now = timezone.now()
        bk = _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=now + timedelta(days=1), end=now + timedelta(days=2)))
        self.assertFalse(bk.is_walk_in)
        self.assertEqual(bk.renter_id, self.renter.id)
        self.assertEqual(bk.client_phone, '')


class BlackoutExceptionTest(BookingTestBase):
    """Owner-managed blackout day-ranges (AvailabilityException CRUD)."""
    TZ = ZoneInfo('Europe/Lisbon')

    def _future(self, days):
        return (timezone.now().astimezone(self.TZ) + timedelta(days=days)).date()

    def test_owner_adds_and_lists_blackout(self):
        b = self._range_bookable()
        s, e = self._future(10), self._future(12)
        resp = api.add_exception(_req(self.owner), b.id, api.ExceptionIn(
            start_date=s.isoformat(), end_date=e.isoformat(), reason='  maintenance  '))
        self.assertEqual(resp.exception.start_date, s.isoformat())
        self.assertEqual(resp.exception.end_date, e.isoformat())   # inclusive round-trip
        self.assertEqual(resp.exception.reason, 'maintenance')      # trimmed
        self.assertEqual(resp.conflicts, 0)
        listed = api.list_exceptions(_req(self.owner), b.id)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].id, resp.exception.id)

    def test_blackout_blocks_booking(self):
        b = self._range_bookable()
        s = self._future(10)
        api.add_exception(_req(self.owner), b.id, api.ExceptionIn(
            start_date=s.isoformat(), end_date=s.isoformat()))   # single day
        start = datetime.combine(s, time(10, 0), tzinfo=self.TZ)
        with self.assertRaises(HttpError) as ctx:
            _book(_req(self.renter), api.BookingCreateRequest(
                item_id=self.item.id, start=start, end=start + timedelta(hours=2)))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_day_after_blackout_is_free(self):
        """End is exclusive at the next midnight — the following day is bookable."""
        b = self._range_bookable()
        s = self._future(10)
        api.add_exception(_req(self.owner), b.id, api.ExceptionIn(
            start_date=s.isoformat(), end_date=s.isoformat()))
        nxt = datetime.combine(s + timedelta(days=1), time(10, 0), tzinfo=self.TZ)
        _book(_req(self.renter), api.BookingCreateRequest(
            item_id=self.item.id, start=nxt, end=nxt + timedelta(hours=2)))

    def test_blackout_shows_in_availability(self):
        b = self._range_bookable()
        s, e = self._future(10), self._future(11)
        api.add_exception(_req(self.owner), b.id, api.ExceptionIn(
            start_date=s.isoformat(), end_date=e.isoformat()))
        frm = datetime.combine(self._future(9), time(0, 0), tzinfo=self.TZ)
        to = datetime.combine(self._future(13), time(0, 0), tzinfo=self.TZ)
        win = api.get_availability(_req(self.owner), self.item.id, frm=frm, to=to)
        self.assertEqual(len([o for o in win.occupied if o.status == 'BLACKOUT']), 1)

    def test_delete_blackout(self):
        b = self._range_bookable()
        s = self._future(10)
        resp = api.add_exception(_req(self.owner), b.id, api.ExceptionIn(
            start_date=s.isoformat(), end_date=s.isoformat()))
        api.delete_exception(_req(self.owner), b.id, resp.exception.id)
        self.assertEqual(len(api.list_exceptions(_req(self.owner), b.id)), 0)

    def test_delete_unknown_blackout_404(self):
        b = self._range_bookable()
        with self.assertRaises(HttpError) as ctx:
            api.delete_exception(_req(self.owner), b.id, 'NOSUCHID')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_stranger_cannot_add_list_or_delete(self):
        b = self._range_bookable()
        s = self._future(10)
        with self.assertRaises(HttpError) as ctx:
            api.add_exception(_req(self.stranger), b.id, api.ExceptionIn(
                start_date=s.isoformat(), end_date=s.isoformat()))
        self.assertEqual(ctx.exception.status_code, 403)
        with self.assertRaises(HttpError):
            api.list_exceptions(_req(self.stranger), b.id)
        resp = api.add_exception(_req(self.owner), b.id, api.ExceptionIn(
            start_date=s.isoformat(), end_date=s.isoformat()))
        with self.assertRaises(HttpError) as ctx2:
            api.delete_exception(_req(self.stranger), b.id, resp.exception.id)
        self.assertEqual(ctx2.exception.status_code, 403)

    def test_end_before_start_400(self):
        b = self._range_bookable()
        with self.assertRaises(HttpError) as ctx:
            api.add_exception(_req(self.owner), b.id, api.ExceptionIn(
                start_date=self._future(12).isoformat(), end_date=self._future(10).isoformat()))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_invalid_date_400(self):
        b = self._range_bookable()
        with self.assertRaises(HttpError) as ctx:
            api.add_exception(_req(self.owner), b.id, api.ExceptionIn(
                start_date='not-a-date', end_date='2026-07-10'))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_conflicts_reported_and_booking_kept(self):
        """A blackout over an existing booking reports the conflict but does NOT
        cancel the booking."""
        b = self._range_bookable()
        bk_start = datetime.combine(self._future(10), time(10, 0), tzinfo=self.TZ)
        Booking.objects.create(bookable=b, renter=self.renter, start=bk_start,
                               end=bk_start + timedelta(hours=2), status=Booking.Status.CONFIRMED)
        resp = api.add_exception(_req(self.owner), b.id, api.ExceptionIn(
            start_date=self._future(10).isoformat(), end_date=self._future(10).isoformat()))
        self.assertEqual(resp.conflicts, 1)
        self.assertTrue(Booking.objects.filter(status=Booking.Status.CONFIRMED).exists())

    def test_delete_scoped_to_bookable(self):
        """A blackout id from another bookable can't be deleted via this route."""
        b1 = self._range_bookable()
        item2 = Item.objects.create(
            owner=self.owner, title='Moto2', type=Item.ItemType.CREDIT,
            pricing_options=[{'type': 'rent', 'amount': 9, 'currency': 'EUR', 'unit': 'day'}])
        b2 = Bookable.objects.create(item=item2, booking_mode=Bookable.Mode.RANGE)
        s = self._future(10)
        resp = api.add_exception(_req(self.owner), b2.id, api.ExceptionIn(
            start_date=s.isoformat(), end_date=s.isoformat()))
        with self.assertRaises(HttpError) as ctx:
            api.delete_exception(_req(self.owner), b1.id, resp.exception.id)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertTrue(AvailabilityException.objects.filter(id=resp.exception.id).exists())
