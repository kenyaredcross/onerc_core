# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Which role scopes a doctype is configuration — and an unresolvable one is loud.

Two things are proved here, and the second matters more than the first.

**The capability.** A registration may name its role through a National Society
Settings field instead of a literal, so a society can decide which of its roles
scopes a doctype without anybody editing an app.

**The trap that shape would otherwise open.** `get_user_geo_scope` takes a role
name and matches assignments against it. A role that names nothing matches no
assignment, returns an empty set, and every enforcement layer denies everybody —
which is indistinguishable, from the outside, from "correctly configured, nobody
assigned yet". That is a site-wide outage wearing the costume of an empty
database.

So the headline tests are not "does it work" but:

* `TestTheSilentDenyTrapIsClosed` — a role that resolves to nothing is refused
  at config time and *logged* at enforcement time, never silently denied;
* `TestTheSharpDistinction` — a correctly configured role with zero assignments
  and a misconfigured role both deny, and the code can still tell them apart.

If those two passed while the distinction was absent, the change would be
worthless, so each asserts the presence *and* absence of the signal.
"""

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.access.services import enforcement, registry
from onerc_core.access.services.registry import SCOPEABLE_DOCTYPE_HOOK
from onerc_core.access.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []

BORROWED_DOCTYPE = "ToDo"
BORROWED_FIELD = "reference_name"

NONEXISTENT_ROLE = "ACC-TEST Role That Does Not Exist"


class ScopeRoleTestCase(IntegrationTestCase):
	"""The tree, records in it, and two roles held in two different counties."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		# Both commit, so they happen before anything that must roll back.
		fixtures.ensure_scoped_doctype()
		fixtures.ensure_setting_field()
		fixtures.reset()

		cls.tree = fixtures.build_tree()
		cls.records = {
			key: fixtures.make_record(key, cls.tree[key])
			for key in ("county_a", "ward_a1", "county_b", "ward_b1", "county_c")
		}

		# Two users, two *different* society roles, two different counties. The
		# roles are what the setting will be pointed at.
		cls.approver = fixtures.make_user("cfg_approver", [fixtures.APPROVER_ROLE])
		cls.viewer = fixtures.make_user("cfg_viewer", [fixtures.VIEWER_ROLE])

		fixtures.make_assignment(cls.approver, fixtures.APPROVER_ROLE, cls.tree["county_a"])
		fixtures.make_assignment(cls.viewer, fixtures.VIEWER_ROLE, cls.tree["county_b"])

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		fixtures.teardown()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(fixtures.set_scope_role_setting, None)

	# --- the three layers, asked the same question ------------------------

	def static(self, role: str = fixtures.APPROVER_ROLE):
		return self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [fixtures.registration(role)]})

	def from_setting(self):
		return self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [fixtures.registration_from_setting()]})

	def listed_by(self, user: str) -> set[str]:
		frappe.set_user(user)

		return set(frappe.get_list(fixtures.SCOPED_DOCTYPE, pluck="name", limit_page_length=0))

	def may_read(self, user: str, record: str) -> bool:
		doc = frappe.get_doc(fixtures.SCOPED_DOCTYPE, record)

		return frappe.has_permission(fixtures.SCOPED_DOCTYPE, doc=doc, user=user, ptype="read")

	def guard_permits(self, user: str, record: str) -> bool:
		try:
			enforcement.guard(fixtures.SCOPED_DOCTYPE, record, user=user)
		except frappe.PermissionError:
			return False

		return True

	def assert_reachable(self, user: str, key: str):
		self.assertIn(self.records[key], self.listed_by(user), f"{key}: not in list query")
		self.assertTrue(self.may_read(user, self.records[key]), f"{key}: document read denied")
		self.assertTrue(self.guard_permits(user, self.records[key]), f"{key}: guard denied")

	def assert_unreachable(self, user: str, key: str):
		self.assertNotIn(self.records[key], self.listed_by(user), f"{key}: LEAKED via list query")
		self.assertFalse(self.may_read(user, self.records[key]), f"{key}: LEAKED via document read")
		self.assertFalse(self.guard_permits(user, self.records[key]), f"{key}: LEAKED via guard")


# --- backward compatibility -----------------------------------------------


class TestStaticRoleIsUnchanged(ScopeRoleTestCase):
	"""A literal `role` behaves exactly as it did. This is the regression guard."""

	def test_the_registration_shape_is_byte_for_byte_what_it_was(self):
		"""No new key appears on a static registration.

		Anything reading a registration as a whole dict — including the existing
		`test_reads_a_declaration_back` — must see precisely the three keys it
		saw before.
		"""
		entry = fixtures.registration(doctype=BORROWED_DOCTYPE, field=BORROWED_FIELD)

		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [entry]}):
			read_back = registry.for_doctype(BORROWED_DOCTYPE)

		self.assertEqual(read_back, entry)
		self.assertEqual(sorted(read_back), ["doctype", "geo_node_field", "role"])
		self.assertNotIn(registry.ROLE_SETTING_KEY, read_back)

	def test_resolve_returns_the_literal_untouched(self):
		entry = fixtures.registration()

		with self.static():
			self.assertEqual(registry.resolve_role(entry), fixtures.APPROVER_ROLE)

	def test_the_literal_is_not_checked_for_existence(self):
		"""Deliberately unchanged behaviour, asserted so nobody "improves" it.

		A literal role that does not exist denies — exactly as before this
		change — and does *not* log. Adding a lookup here would alter how every
		pre-existing registration performs, which is the one thing this change
		may not do.
		"""
		before = fixtures.scope_role_log_count()
		entry = {
			"doctype": fixtures.SCOPED_DOCTYPE,
			"geo_node_field": fixtures.GEO_FIELD,
			"role": NONEXISTENT_ROLE,
		}

		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [entry]}):
			self.assertEqual(registry.resolve_role(entry), NONEXISTENT_ROLE)
			self.assert_unreachable(self.approver, "county_a")

		self.assertEqual(fixtures.scope_role_log_count(), before)

	def test_static_scoping_still_works_end_to_end(self):
		with self.static():
			self.assert_reachable(self.approver, "county_a")
			self.assert_reachable(self.approver, "ward_a1")
			self.assert_unreachable(self.approver, "county_b")


# --- the capability --------------------------------------------------------


class TestRoleFromSetting(ScopeRoleTestCase):
	"""A registration whose role is named by a settings field scopes correctly."""

	def test_resolve_reads_the_configured_role(self):
		fixtures.set_scope_role_setting(fixtures.APPROVER_ROLE)

		with self.from_setting():
			self.assertEqual(
				registry.resolve_role(fixtures.registration_from_setting()), fixtures.APPROVER_ROLE
			)

	def test_it_scopes_exactly_like_the_literal_would(self):
		"""Same outcome as the static registration, reached the other way."""
		fixtures.set_scope_role_setting(fixtures.APPROVER_ROLE)

		with self.from_setting():
			self.assert_reachable(self.approver, "county_a")
			self.assert_reachable(self.approver, "ward_a1")
			self.assert_unreachable(self.approver, "county_b")

	def test_the_registration_carries_the_setting_key_not_a_role(self):
		entry = fixtures.registration_from_setting()

		with self.from_setting():
			read_back = registry.for_doctype(fixtures.SCOPED_DOCTYPE)

		self.assertEqual(read_back, entry)
		self.assertEqual(sorted(read_back), ["doctype", "geo_node_field", "role_from_setting"])
		self.assertNotIn(registry.ROLE_KEY, read_back)

	def test_a_user_holding_the_other_role_is_denied(self):
		"""The setting names one role; holding a different one grants nothing."""
		fixtures.set_scope_role_setting(fixtures.APPROVER_ROLE)

		with self.from_setting():
			self.assert_unreachable(self.viewer, "county_b")


class TestConfigurationDrivesTheRole(ScopeRoleTestCase):
	"""Zero code diff: change the setting, get a different effective scope."""

	def test_the_same_code_yields_two_different_scopes(self):
		"""Both halves in one test, so there is no doubt they share a code path.

		Nothing is edited between the two blocks except the value in National
		Society Settings.
		"""
		with self.from_setting():
			fixtures.set_scope_role_setting(fixtures.APPROVER_ROLE)

			self.assert_reachable(self.approver, "county_a")
			self.assert_unreachable(self.viewer, "county_b")

			fixtures.set_scope_role_setting(fixtures.VIEWER_ROLE)

			self.assert_reachable(self.viewer, "county_b")
			self.assert_unreachable(self.approver, "county_a")

	def test_the_resolved_role_follows_the_setting(self):
		entry = fixtures.registration_from_setting()

		with self.from_setting():
			fixtures.set_scope_role_setting(fixtures.APPROVER_ROLE)
			self.assertEqual(registry.resolve_role(entry), fixtures.APPROVER_ROLE)

			fixtures.set_scope_role_setting(fixtures.VIEWER_ROLE)
			self.assertEqual(registry.resolve_role(entry), fixtures.VIEWER_ROLE)


# --- the headline ----------------------------------------------------------


class TestTheSilentDenyTrapIsClosed(ScopeRoleTestCase):
	"""A role that resolves to nothing must never deny silently."""

	def test_config_time_refuses_a_role_that_does_not_exist(self):
		"""Saving the settings form with a bad role throws, then and there.

		The message is asserted, not just the exception class. `MandatoryError`
		subclasses `ValidationError`, so a settings single with an unrelated
		blank required field would otherwise satisfy `assertRaises` and this
		test would pass without the role check ever running — which it did,
		before the fixture filled those fields in.
		"""
		with self.from_setting(), self.assertRaises(frappe.ValidationError):
			fixtures.save_scope_role_setting(NONEXISTENT_ROLE)

		message = frappe.as_json(frappe.message_log[-1] if frappe.message_log else {})

		self.assertIn(NONEXISTENT_ROLE, message, "refused, but not for the reason under test")
		self.assertIn(fixtures.SCOPED_DOCTYPE, message)

	def test_the_refusal_is_not_a_mandatory_field_error_in_disguise(self):
		"""Guards the test above by proving the same save succeeds with a good role.

		If the settings single were unsaveable for an unrelated reason, this
		would fail — so the refusal above can only be about the role.
		"""
		with self.from_setting():
			fixtures.save_scope_role_setting(fixtures.APPROVER_ROLE)

		self.assertEqual(
			frappe.db.get_single_value(fixtures.SETTINGS_DOCTYPE, fixtures.SCOPE_ROLE_SETTING),
			fixtures.APPROVER_ROLE,
		)

	def test_config_time_allows_an_empty_value(self):
		"""Not yet configured is not a mistake — it must still be saveable."""
		with self.from_setting():
			fixtures.save_scope_role_setting(None)

		self.assertIsNone(registry.resolve_role(fixtures.registration_from_setting()))

	def test_config_time_allows_a_real_role(self):
		with self.from_setting():
			fixtures.save_scope_role_setting(fixtures.VIEWER_ROLE)

		self.assertEqual(registry.resolve_role(fixtures.registration_from_setting()), fixtures.VIEWER_ROLE)

	def test_config_time_ignores_settings_fields_nobody_registered(self):
		"""With no settings-backed registration, the check must not fire at all."""
		with self.static():
			fixtures.save_scope_role_setting(NONEXISTENT_ROLE)

		self.assertEqual(
			frappe.db.get_single_value(fixtures.SETTINGS_DOCTYPE, fixtures.SCOPE_ROLE_SETTING),
			NONEXISTENT_ROLE,
		)

	def test_enforcement_logs_and_fails_closed_on_a_bad_value(self):
		"""The value is planted behind validate()'s back — as a bad migration would.

		Config-time validation is the first line, not the only one: a value can
		reach the database without passing through the form, so enforcement has
		to cope with one and say so.
		"""
		fixtures.set_scope_role_setting(NONEXISTENT_ROLE)
		before = fixtures.scope_role_log_count()

		with self.from_setting():
			self.assert_unreachable(self.approver, "county_a")

		self.assertGreater(
			fixtures.scope_role_log_count(), before, "a misconfigured role denied everybody silently"
		)

	def test_enforcement_logs_and_fails_closed_on_an_unset_value(self):
		fixtures.set_scope_role_setting(None)
		before = fixtures.scope_role_log_count()

		with self.from_setting():
			self.assert_unreachable(self.approver, "county_a")

		self.assertGreater(fixtures.scope_role_log_count(), before)

	def test_enforcement_logs_and_fails_closed_on_a_missing_settings_field(self):
		"""A registration naming a field that is not on the settings doctype."""
		entry = fixtures.registration_from_setting(setting="no_such_settings_field")
		before = fixtures.scope_role_log_count()

		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [entry]}):
			self.assert_unreachable(self.approver, "county_a")

		self.assertGreater(fixtures.scope_role_log_count(), before)

	def test_it_denies_rather_than_grants(self):
		"""Fail closed, not open. The inverse mistake would be catastrophic."""
		fixtures.set_scope_role_setting(NONEXISTENT_ROLE)

		with self.from_setting():
			self.assertEqual(
				enforcement.get_permission_query_conditions(self.approver, fixtures.SCOPED_DOCTYPE),
				enforcement.DENY_ALL,
			)
			self.assertFalse(
				enforcement.is_in_scope(fixtures.SCOPED_DOCTYPE, self.tree["county_a"], self.approver)
			)

	def test_it_does_not_throw_in_the_query_path(self):
		"""Throwing here would break every list view on the site, not one doctype."""
		fixtures.set_scope_role_setting(NONEXISTENT_ROLE)

		with self.from_setting():
			# No exception is the assertion.
			enforcement.get_permission_query_conditions(self.approver, fixtures.SCOPED_DOCTYPE)

	def test_an_administrator_can_still_get_in_to_fix_it(self):
		"""The framework exemption is untouched, which is what makes this fixable."""
		fixtures.set_scope_role_setting(NONEXISTENT_ROLE)

		with self.from_setting():
			self.assertEqual(
				enforcement.get_permission_query_conditions("Administrator", fixtures.SCOPED_DOCTYPE), ""
			)
			self.assertTrue(
				enforcement.is_in_scope(fixtures.SCOPED_DOCTYPE, self.tree["county_a"], "Administrator")
			)


class TestTheSharpDistinction(ScopeRoleTestCase):
	"""Both deny. Only one is a fault — and the code knows which.

	This is the test that decides whether the trap is really closed. If a
	correctly configured role with no assignments and a role that names nothing
	produce identical observable behaviour, then nothing has been fixed: the
	outage is still invisible.
	"""

	def test_a_valid_role_with_no_assignments_denies_without_any_signal(self):
		"""Case (a): normal. Nobody has been granted anything yet."""
		fixtures.set_scope_role_setting(fixtures.VIEWER_ROLE)
		before = fixtures.scope_role_log_count()

		with self.from_setting():
			# The viewer role is real and resolves; this user simply holds no
			# assignment under it.
			self.assertEqual(
				registry.resolve_role(fixtures.registration_from_setting()), fixtures.VIEWER_ROLE
			)
			self.assert_unreachable(self.approver, "county_a")

		self.assertEqual(
			fixtures.scope_role_log_count(),
			before,
			"an ordinary empty scope was reported as a misconfiguration",
		)

	def test_an_unresolvable_role_denies_and_signals(self):
		"""Case (b): a fault. Same denial, different diagnosis."""
		fixtures.set_scope_role_setting(NONEXISTENT_ROLE)
		before = fixtures.scope_role_log_count()

		with self.from_setting():
			self.assertIsNone(registry.resolve_role(fixtures.registration_from_setting()))
			self.assert_unreachable(self.approver, "county_a")

		self.assertGreater(fixtures.scope_role_log_count(), before)

	def test_the_two_are_distinguishable_in_one_run(self):
		"""The distinction itself, asserted directly rather than inferred.

		Same user, same records, same registration, both denied — and the only
		difference between the two halves is whether the configured role exists.
		One produces a signal; the other must not.
		"""
		with self.from_setting():
			fixtures.set_scope_role_setting(fixtures.VIEWER_ROLE)
			healthy_before = fixtures.scope_role_log_count()
			self.assert_unreachable(self.approver, "county_a")
			healthy_signals = fixtures.scope_role_log_count() - healthy_before

			fixtures.set_scope_role_setting(NONEXISTENT_ROLE)
			broken_before = fixtures.scope_role_log_count()
			self.assert_unreachable(self.approver, "county_a")
			broken_signals = fixtures.scope_role_log_count() - broken_before

		self.assertEqual(healthy_signals, 0, "a healthy empty scope signalled a fault")
		self.assertGreater(broken_signals, 0, "a real misconfiguration produced no signal")

	def test_the_healthy_case_is_genuinely_denied_too(self):
		"""Guards the test above: if (a) were *reachable*, it would prove nothing."""
		fixtures.set_scope_role_setting(fixtures.VIEWER_ROLE)

		with self.from_setting():
			self.assert_unreachable(self.approver, "county_a")
			# ...while the user who does hold that role reaches their own county.
			self.assert_reachable(self.viewer, "county_b")


# --- registration shape ----------------------------------------------------


class TestExactlyOneRoleKey(ScopeRoleTestCase):
	"""XOR, enforced at registration and refused loudly either way."""

	def _reject(self, entry, exception=frappe.ValidationError):
		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [entry]}), self.assertRaises(exception):
			registry.registrations()

	def test_both_keys_is_rejected(self):
		self._reject(
			{
				"doctype": BORROWED_DOCTYPE,
				"geo_node_field": BORROWED_FIELD,
				"role": fixtures.APPROVER_ROLE,
				"role_from_setting": fixtures.SCOPE_ROLE_SETTING,
			}
		)

	def test_neither_key_is_rejected(self):
		self._reject({"doctype": BORROWED_DOCTYPE, "geo_node_field": BORROWED_FIELD}, frappe.MandatoryError)

	def test_an_empty_role_value_counts_as_absent(self):
		self._reject(
			{"doctype": BORROWED_DOCTYPE, "geo_node_field": BORROWED_FIELD, "role": ""},
			frappe.MandatoryError,
		)

	def test_the_base_keys_are_still_required(self):
		self._reject(
			{"geo_node_field": BORROWED_FIELD, "role_from_setting": fixtures.SCOPE_ROLE_SETTING},
			frappe.MandatoryError,
		)
		self._reject(
			{"doctype": BORROWED_DOCTYPE, "role_from_setting": fixtures.SCOPE_ROLE_SETTING},
			frappe.MandatoryError,
		)


class TestAllThreeLayersUseTheResolvedRole(ScopeRoleTestCase):
	"""Fixing one call site and leaving two would be worse than fixing none."""

	def test_each_layer_independently_honours_the_configured_role(self):
		"""Asserted per layer, so a miss in one cannot hide behind the others."""
		with self.from_setting():
			fixtures.set_scope_role_setting(fixtures.VIEWER_ROLE)

			# Layer 1 — query filter.
			self.assertIn(self.records["county_b"], self.listed_by(self.viewer))
			self.assertNotIn(self.records["county_a"], self.listed_by(self.viewer))

			# Layer 2 — document read.
			self.assertTrue(self.may_read(self.viewer, self.records["county_b"]))
			self.assertFalse(self.may_read(self.viewer, self.records["county_a"]))

			# Layer 3 — API guard.
			self.assertTrue(self.guard_permits(self.viewer, self.records["county_b"]))
			self.assertFalse(self.guard_permits(self.viewer, self.records["county_a"]))

	def test_each_layer_independently_fails_closed_on_a_bad_role(self):
		fixtures.set_scope_role_setting(NONEXISTENT_ROLE)

		with self.from_setting():
			self.assertEqual(
				enforcement.get_permission_query_conditions(self.viewer, fixtures.SCOPED_DOCTYPE),
				enforcement.DENY_ALL,
			)
			self.assertFalse(self.may_read(self.viewer, self.records["county_b"]))
			self.assertFalse(self.guard_permits(self.viewer, self.records["county_b"]))

	def test_the_guard_names_the_resolved_role_not_the_settings_field(self):
		"""A refusal that named the fieldname would send the reader to the wrong place."""
		fixtures.set_scope_role_setting(fixtures.VIEWER_ROLE)

		with self.from_setting(), self.assertRaises(frappe.PermissionError):
			enforcement.guard(fixtures.SCOPED_DOCTYPE, self.records["county_a"], user=self.viewer)

		message = frappe.as_json(frappe.message_log[-1] if frappe.message_log else {})

		self.assertIn(fixtures.VIEWER_ROLE, message)
		self.assertNotIn(fixtures.SCOPE_ROLE_SETTING, message)

	def test_the_guard_says_so_when_the_role_is_not_configured(self):
		fixtures.set_scope_role_setting(None)

		with self.from_setting(), self.assertRaises(frappe.PermissionError):
			enforcement.guard(fixtures.SCOPED_DOCTYPE, self.records["county_a"], user=self.viewer)
