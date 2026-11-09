# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""The gate.

Every test here is written to *fail* if the layer leaks. A test that only proves
County A's approver can see County A would pass just as happily with no access
control at all — so each case pairs what a user can reach with what they
provably cannot, through all three enforcement layers:

* **list query** — `frappe.get_list`, which runs the real query engine and the
  real `get_permission_query_conditions` hook;
* **document read** — `frappe.has_permission`, the path a guessed docname or a
  bookmarked URL takes;
* **API guard** — `enforcement.guard()`, the path a custom endpoint takes.

A hole in any one of them is a hole in the system, which is why County B is
denied three times over rather than once.
"""

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.access.services import enforcement
from onerc_core.access.services.registry import SCOPEABLE_DOCTYPE_HOOK
from onerc_core.access.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []


class EnforcementTestCase(IntegrationTestCase):
	"""Shared arrangement: the tree, a record in every node, and the registration."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		# DDL, and it commits — so it happens before anything that must roll back.
		fixtures.ensure_scoped_doctype()
		fixtures.reset()

		cls.tree = fixtures.build_tree()
		cls.records = {
			key: fixtures.make_record(key, cls.tree[key])
			for key in ("region", "county_a", "ward_a1", "ward_a2", "county_b", "ward_b1", "county_c")
		}
		# A record that was never placed in the tree.
		cls.records["unplaced"] = fixtures.make_record("unplaced", None)

	@classmethod
	def tearDownClass(cls):
		# Roll the fixture data back before dropping the doctype, so the drop is
		# not fighting rows that are about to disappear anyway.
		frappe.db.rollback()
		fixtures.teardown()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")

	def scoped(self, role: str = fixtures.APPROVER_ROLE):
		return self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [fixtures.registration(role)]})

	# --- the three layers, each asked the same question -------------------

	def listed_by(self, user: str) -> set[str]:
		"""Layer 1: what the query engine returns for this user."""
		frappe.set_user(user)

		return set(frappe.get_list(fixtures.SCOPED_DOCTYPE, pluck="name", limit_page_length=0))

	def may_read(self, user: str, record: str) -> bool:
		"""Layer 2: what the document permission check says about one record."""
		doc = frappe.get_doc(fixtures.SCOPED_DOCTYPE, record)

		return frappe.has_permission(fixtures.SCOPED_DOCTYPE, doc=doc, user=user, ptype="read")

	def guard_permits(self, user: str, record: str) -> bool:
		"""Layer 3: what the API guard does."""
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


class TestTheGate(EnforcementTestCase):
	"""County A's approver cannot reach County B. Three layers, no exceptions."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.approver_a = fixtures.make_user("gate_a", [fixtures.APPROVER_ROLE])
		cls.approver_b = fixtures.make_user("gate_b", [fixtures.APPROVER_ROLE])

		fixtures.make_assignment(cls.approver_a, fixtures.APPROVER_ROLE, cls.tree["county_a"])
		fixtures.make_assignment(cls.approver_b, fixtures.APPROVER_ROLE, cls.tree["county_b"])

	def test_reaches_its_own_county(self):
		with self.scoped():
			self.assert_reachable(self.approver_a, "county_a")

	def test_reaches_wards_beneath_it(self):
		with self.scoped():
			self.assert_reachable(self.approver_a, "ward_a1")
			self.assert_reachable(self.approver_a, "ward_a2")

	def test_cannot_reach_the_other_county(self):
		"""The gate. If this passes while the layer is broken, nothing else matters."""
		with self.scoped():
			self.assert_unreachable(self.approver_a, "county_b")

	def test_cannot_reach_a_ward_of_the_other_county(self):
		with self.scoped():
			self.assert_unreachable(self.approver_a, "ward_b1")

	def test_cannot_reach_an_unassigned_county(self):
		with self.scoped():
			self.assert_unreachable(self.approver_a, "county_c")

	def test_cannot_reach_upward(self):
		"""Authority over a county is not authority over the region containing it."""
		with self.scoped():
			self.assert_unreachable(self.approver_a, "region")

	def test_cannot_reach_an_unplaced_record(self):
		"""A record in no county is inside nobody's scope — both layers agree."""
		with self.scoped():
			self.assert_unreachable(self.approver_a, "unplaced")

	def test_the_gate_is_symmetric(self):
		"""County B's approver is denied County A by the same machinery."""
		with self.scoped():
			self.assert_reachable(self.approver_b, "ward_b1")
			self.assert_unreachable(self.approver_b, "county_a")
			self.assert_unreachable(self.approver_b, "ward_a1")

	def test_the_list_query_returns_exactly_the_subtree(self):
		with self.scoped():
			self.assertEqual(
				self.listed_by(self.approver_a),
				{self.records["county_a"], self.records["ward_a1"], self.records["ward_a2"]},
			)

	def test_the_guard_hides_whether_a_record_exists(self):
		"""A name outside the scope and a name that never existed answer alike.

		Otherwise a caller could map the tree by watching which names come back
		"not found" and which come back "forbidden".
		"""
		with self.scoped():
			self.assertFalse(self.guard_permits(self.approver_a, self.records["ward_b1"]))
			self.assertFalse(self.guard_permits(self.approver_a, "no-such-record"))


class TestFailClosed(EnforcementTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		# Holds the Frappe role, but has never been granted it anywhere.
		cls.nobody = fixtures.make_user("gate_nobody", [fixtures.APPROVER_ROLE])

	def test_sees_nothing_at_all(self):
		with self.scoped():
			self.assertEqual(self.listed_by(self.nobody), set())

	def test_is_denied_every_record(self):
		with self.scoped():
			for key in ("county_a", "ward_a1", "county_b", "region", "unplaced"):
				self.assert_unreachable(self.nobody, key)


class TestUnrestrictedBypass(EnforcementTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.manager = fixtures.make_user("gate_manager", [fixtures.APPROVER_ROLE, "System Manager"])

	def test_reaches_every_placed_record(self):
		with self.scoped():
			for key in ("region", "county_a", "ward_a1", "county_b", "ward_b1", "county_c"):
				self.assert_reachable(self.manager, key)

	def test_reaches_the_unplaced_record_too(self):
		"""The bypass is a bypass — it does not re-acquire the geo requirement."""
		with self.scoped():
			self.assert_reachable(self.manager, "unplaced")


class TestMultipleAssignments(EnforcementTestCase):
	"""ACC-01 end to end: two unrelated counties, no leak into a third."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.multi = fixtures.make_user("gate_multi", [fixtures.APPROVER_ROLE])
		fixtures.make_assignment(cls.multi, fixtures.APPROVER_ROLE, cls.tree["county_a"])
		fixtures.make_assignment(cls.multi, fixtures.APPROVER_ROLE, cls.tree["county_b"])

	def test_sees_the_union_of_both_subtrees(self):
		with self.scoped():
			self.assertEqual(
				self.listed_by(self.multi),
				{
					self.records["county_a"],
					self.records["ward_a1"],
					self.records["ward_a2"],
					self.records["county_b"],
					self.records["ward_b1"],
				},
			)

	def test_neither_grant_widens_into_the_third_county(self):
		with self.scoped():
			self.assert_unreachable(self.multi, "county_c")
			self.assert_unreachable(self.multi, "region")


class TestRoleDimension(EnforcementTestCase):
	"""Approver in County A, viewer in County B — and the scoped role is approver.

	The registration names one role. Holding a *different* role in County B is
	not authority over County B's records of this doctype, and the layer must not
	pool the two.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.crossover = fixtures.make_user("gate_crossover", [fixtures.APPROVER_ROLE, fixtures.VIEWER_ROLE])
		fixtures.make_assignment(cls.crossover, fixtures.APPROVER_ROLE, cls.tree["county_a"])
		fixtures.make_assignment(cls.crossover, fixtures.VIEWER_ROLE, cls.tree["county_b"])

	def test_the_approver_grant_applies(self):
		with self.scoped(fixtures.APPROVER_ROLE):
			self.assert_reachable(self.crossover, "ward_a1")

	def test_the_viewer_grant_does_not_apply_to_an_approver_scoped_doctype(self):
		with self.scoped(fixtures.APPROVER_ROLE):
			self.assert_unreachable(self.crossover, "county_b")
			self.assert_unreachable(self.crossover, "ward_b1")

	def test_re_registering_for_the_viewer_role_flips_the_answer(self):
		"""Same user, same data — only the registered role differs."""
		with self.scoped(fixtures.VIEWER_ROLE):
			self.assert_reachable(self.crossover, "ward_b1")
			self.assert_unreachable(self.crossover, "ward_a1")


class TestLivenessThroughEnforcement(EnforcementTestCase):
	"""A dead assignment grants nothing, all the way out to the query engine."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.inactive = fixtures.make_user("gate_inactive", [fixtures.APPROVER_ROLE])
		cls.expired = fixtures.make_user("gate_expired", [fixtures.APPROVER_ROLE])

		fixtures.make_assignment(cls.inactive, fixtures.APPROVER_ROLE, cls.tree["county_a"], is_active=False)
		fixtures.make_assignment(
			cls.expired, fixtures.APPROVER_ROLE, cls.tree["county_a"], valid_to="2026-01-31"
		)

	def test_a_deactivated_assignment_grants_nothing(self):
		with self.scoped():
			self.assertEqual(self.listed_by(self.inactive), set())
			self.assert_unreachable(self.inactive, "ward_a1")

	def test_an_expired_assignment_grants_nothing(self):
		with self.scoped():
			self.assertEqual(self.listed_by(self.expired), set())
			self.assert_unreachable(self.expired, "ward_a1")


class TestUnregisteredDoctypeIsUntouched(EnforcementTestCase):
	"""With no registration the same user sees everything — proving the gate is the cause.

	Without this, every "sees nothing" assertion above would be consistent with
	the records simply being unreadable for some unrelated reason.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.approver = fixtures.make_user("gate_unreg", [fixtures.APPROVER_ROLE])
		fixtures.make_assignment(cls.approver, fixtures.APPROVER_ROLE, cls.tree["county_a"])

	def test_without_registration_nothing_is_filtered(self):
		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: []}):
			listed = self.listed_by(self.approver)

		self.assertIn(self.records["county_b"], listed)
		self.assertIn(self.records["region"], listed)
		self.assertIn(self.records["unplaced"], listed)

	def test_registering_is_what_takes_county_b_away(self):
		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: []}):
			before = self.listed_by(self.approver)

		with self.scoped():
			after = self.listed_by(self.approver)

		self.assertIn(self.records["county_b"], before)
		self.assertNotIn(self.records["county_b"], after)
