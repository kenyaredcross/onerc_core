# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from onerc_core.access.tests import fixtures
from onerc_core.onerc_core.doctype.geo_assignment.geo_assignment import is_live

EXTRA_TEST_RECORD_DEPENDENCIES = []


class TestGeoAssignment(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.tree = fixtures.build_tree()
		cls.user = fixtures.make_user("assignee")

	def test_docname_is_opaque(self):
		"""Every field here is mutable, so none of them may be the key."""
		name = fixtures.make_assignment(self.user, fixtures.APPROVER_ROLE, self.tree["county_a"])

		self.assertTrue(name.startswith("GA-"), name)
		self.assertNotIn(self.user, name)
		self.assertNotIn(fixtures.APPROVER_ROLE, name)
		self.assertNotIn(self.tree["county_a"], name)

	def test_acc_01_same_role_at_unrelated_nodes(self):
		"""ACC-01: one user, one role, several places — several rows, no complaint."""
		first = fixtures.make_assignment(self.user, fixtures.APPROVER_ROLE, self.tree["county_a"])
		second = fixtures.make_assignment(self.user, fixtures.APPROVER_ROLE, self.tree["county_c"])

		self.assertNotEqual(first, second)
		self.assertEqual(
			frappe.db.count("Geo Assignment", {"user": self.user, "role": fixtures.APPROVER_ROLE}),
			2,
		)

	def test_repeated_windows_at_one_node_are_allowed(self):
		"""An acting coordinator serving twice is two rows at the same node."""
		fixtures.make_assignment(
			self.user,
			fixtures.APPROVER_ROLE,
			self.tree["county_b"],
			valid_from="2026-01-01",
			valid_to="2026-03-31",
		)
		fixtures.make_assignment(
			self.user,
			fixtures.APPROVER_ROLE,
			self.tree["county_b"],
			valid_from="2026-07-01",
			valid_to="2026-09-30",
		)

		self.assertEqual(
			frappe.db.count("Geo Assignment", {"user": self.user, "geo_node": self.tree["county_b"]}), 2
		)

	def test_window_may_not_end_before_it_starts(self):
		with self.assertRaises(frappe.ValidationError):
			fixtures.make_assignment(
				self.user,
				fixtures.APPROVER_ROLE,
				self.tree["county_a"],
				valid_from="2026-06-01",
				valid_to="2026-05-01",
			)


class TestLiveness(IntegrationTestCase):
	"""The liveness rule, exercised on its Python side.

	`is_live()` and `LIVE_SQL` are two expressions of one rule, and the scope
	tests drive the SQL side over the same cases. Both must agree, which is the
	reason the rule is written down once and read from here.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.tree = fixtures.build_tree()
		cls.user = fixtures.make_user("liveness")

	def _assignment(self, **kwargs) -> str:
		return fixtures.make_assignment(self.user, fixtures.APPROVER_ROLE, self.tree["county_a"], **kwargs)

	def test_unbounded_and_active_is_live(self):
		self.assertTrue(is_live(self._assignment()))

	def test_inactive_is_not_live(self):
		self.assertFalse(is_live(self._assignment(is_active=False)))

	def test_expired_is_not_live(self):
		self.assertFalse(is_live(self._assignment(valid_to=add_days(today(), -1))))

	def test_not_yet_started_is_not_live(self):
		self.assertFalse(is_live(self._assignment(valid_from=add_days(today(), 1))))

	def test_inside_the_window_is_live(self):
		self.assertTrue(
			is_live(self._assignment(valid_from=add_days(today(), -5), valid_to=add_days(today(), 5)))
		)

	def test_boundaries_are_inclusive(self):
		"""A window that opens or closes today is live today."""
		self.assertTrue(is_live(self._assignment(valid_from=today())))
		self.assertTrue(is_live(self._assignment(valid_to=today())))

	def test_liveness_is_relative_to_the_date_asked_about(self):
		assignment = self._assignment(valid_from="2026-01-01", valid_to="2026-03-31")

		self.assertTrue(is_live(assignment, on_date="2026-02-15"))
		self.assertFalse(is_live(assignment, on_date="2026-04-01"))

	def test_a_missing_assignment_is_not_live(self):
		self.assertFalse(is_live("GA-does-not-exist"))
