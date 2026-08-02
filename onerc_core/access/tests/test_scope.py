# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from onerc_core.access.services import scope
from onerc_core.access.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []


class ScopeTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.tree = fixtures.build_tree()

	def scope_for(self, user: str, role: str, on_date: str | None = None) -> set[str]:
		return scope.get_user_geo_scope(user, role, on_date)


class TestGetUserGeoScope(ScopeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.approver_a = fixtures.make_user("approver_a", [fixtures.APPROVER_ROLE])
		fixtures.make_assignment(cls.approver_a, fixtures.APPROVER_ROLE, cls.tree["county_a"])

	def test_covers_the_assigned_node(self):
		self.assertIn(self.tree["county_a"], self.scope_for(self.approver_a, fixtures.APPROVER_ROLE))

	def test_covers_every_descendant(self):
		covered = self.scope_for(self.approver_a, fixtures.APPROVER_ROLE)

		self.assertIn(self.tree["ward_a1"], covered)
		self.assertIn(self.tree["ward_a2"], covered)

	def test_does_not_cover_a_sibling_subtree(self):
		"""The property the whole layer exists for, at the service level."""
		covered = self.scope_for(self.approver_a, fixtures.APPROVER_ROLE)

		self.assertNotIn(self.tree["county_b"], covered)
		self.assertNotIn(self.tree["ward_b1"], covered)
		self.assertNotIn(self.tree["county_c"], covered)

	def test_does_not_cover_the_ancestor(self):
		"""Authority at a county does not reach up to the region.

		Scope is downward only. `matches_scope(allow_ancestor=True)` exists in the
		adapter for questions about containment, but authority is not containment
		— being trusted with a county is not being trusted with the country.
		"""
		self.assertNotIn(self.tree["region"], self.scope_for(self.approver_a, fixtures.APPROVER_ROLE))

	def test_exact_membership(self):
		self.assertEqual(
			self.scope_for(self.approver_a, fixtures.APPROVER_ROLE),
			{self.tree["county_a"], self.tree["ward_a1"], self.tree["ward_a2"]},
		)


class TestFailClosed(ScopeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.nobody = fixtures.make_user("nobody", [fixtures.APPROVER_ROLE])

	def test_no_assignment_sees_nothing(self):
		"""Holding the Frappe role is not holding it anywhere."""
		self.assertEqual(self.scope_for(self.nobody, fixtures.APPROVER_ROLE), set())

	def test_unknown_role_sees_nothing(self):
		self.assertEqual(self.scope_for(self.nobody, "ACC-TEST No Such Role"), set())

	def test_no_role_sees_nothing(self):
		self.assertEqual(self.scope_for(self.nobody, None), set())

	def test_an_empty_user_falls_back_to_the_session_user(self):
		"""Omitting the user must resolve to the caller, not to nobody-in-particular.

		Asserted with an unprivileged session user on purpose. A test run's default
		session is Administrator, who is legitimately unrestricted, so leaving it in
		place would have this pass for a reason unrelated to the fallback.
		"""
		frappe.set_user(self.nobody)
		self.addCleanup(frappe.set_user, "Administrator")

		self.assertEqual(scope.get_user_geo_scope(None, fixtures.APPROVER_ROLE), set())


class TestLivenessThroughScope(ScopeTestCase):
	"""The SQL side of the liveness rule, over the same cases as `is_live()`."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.user = fixtures.make_user("timebound", [fixtures.APPROVER_ROLE])

	def setUp(self):
		"""Start each case with no assignments at all.

		`IntegrationTestCase` rolls back once per class, not per test, so rows
		written by one method are still there for the next. This class asserts
		what a *single* assignment grants, so it clears the slate itself rather
		than depending on a rollback that does not happen between methods.
		"""
		super().setUp()

		for name in frappe.get_all("Geo Assignment", filters={"user": self.user}, pluck="name"):
			frappe.delete_doc("Geo Assignment", name, force=True)

	def _grant(self, **kwargs) -> None:
		fixtures.make_assignment(self.user, fixtures.APPROVER_ROLE, self.tree["county_a"], **kwargs)

	def _covered(self) -> bool:
		return self.tree["ward_a1"] in self.scope_for(self.user, fixtures.APPROVER_ROLE)

	def test_inactive_grants_nothing(self):
		self._grant(is_active=False)

		self.assertFalse(self._covered())

	def test_expired_grants_nothing(self):
		self._grant(valid_to=add_days(today(), -1))

		self.assertFalse(self._covered())

	def test_not_yet_started_grants_nothing(self):
		self._grant(valid_from=add_days(today(), 1))

		self.assertFalse(self._covered())

	def test_open_ended_grants(self):
		self._grant(valid_from=add_days(today(), -30))

		self.assertTrue(self._covered())

	def test_an_expired_row_alongside_a_live_one_still_grants(self):
		"""Deactivating is not deleting — history must not remove authority."""
		self._grant(valid_to=add_days(today(), -1))
		self._grant()

		self.assertTrue(self._covered())

	def test_scope_is_relative_to_the_date_asked_about(self):
		self._grant(valid_from="2026-01-01", valid_to="2026-03-31")

		self.assertIn(
			self.tree["ward_a1"],
			self.scope_for(self.user, fixtures.APPROVER_ROLE, on_date="2026-02-15"),
		)
		self.assertEqual(self.scope_for(self.user, fixtures.APPROVER_ROLE, on_date="2026-04-01"), set())


class TestMultipleAssignments(ScopeTestCase):
	"""ACC-01 at the scope level: the union of two unrelated subtrees."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.multi = fixtures.make_user("multi", [fixtures.APPROVER_ROLE])
		fixtures.make_assignment(cls.multi, fixtures.APPROVER_ROLE, cls.tree["county_a"])
		fixtures.make_assignment(cls.multi, fixtures.APPROVER_ROLE, cls.tree["county_b"])

	def test_covers_both_subtrees(self):
		covered = self.scope_for(self.multi, fixtures.APPROVER_ROLE)

		self.assertEqual(
			covered,
			{
				self.tree["county_a"],
				self.tree["ward_a1"],
				self.tree["ward_a2"],
				self.tree["county_b"],
				self.tree["ward_b1"],
			},
		)

	def test_neither_leaks_the_other_s_sibling(self):
		"""Two grants must union, not widen.

		A union of disjoint subtrees cannot reach County C. If it did, the
		expansion had walked upward from one grant to the shared region and back
		down — which is how a multi-county assignment would quietly become a
		national one.
		"""
		covered = self.scope_for(self.multi, fixtures.APPROVER_ROLE)

		self.assertNotIn(self.tree["county_c"], covered)
		self.assertNotIn(self.tree["ward_c1"], covered)
		self.assertNotIn(self.tree["region"], covered)


class TestRoleDimension(ScopeTestCase):
	"""Scope is per role. Two roles at two places do not pool."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.crossover = fixtures.make_user("crossover", [fixtures.APPROVER_ROLE, fixtures.VIEWER_ROLE])
		fixtures.make_assignment(cls.crossover, fixtures.APPROVER_ROLE, cls.tree["county_a"])
		fixtures.make_assignment(cls.crossover, fixtures.VIEWER_ROLE, cls.tree["county_b"])

	def test_approver_scope_is_county_a_only(self):
		covered = self.scope_for(self.crossover, fixtures.APPROVER_ROLE)

		self.assertIn(self.tree["ward_a1"], covered)
		self.assertNotIn(self.tree["county_b"], covered)
		self.assertNotIn(self.tree["ward_b1"], covered)

	def test_viewer_scope_is_county_b_only(self):
		covered = self.scope_for(self.crossover, fixtures.VIEWER_ROLE)

		self.assertIn(self.tree["ward_b1"], covered)
		self.assertNotIn(self.tree["county_a"], covered)
		self.assertNotIn(self.tree["ward_a1"], covered)

	def test_the_two_scopes_are_disjoint(self):
		self.assertEqual(
			self.scope_for(self.crossover, fixtures.APPROVER_ROLE)
			& self.scope_for(self.crossover, fixtures.VIEWER_ROLE),
			set(),
		)


class TestUnrestrictedBypass(ScopeTestCase):
	"""The bypass, tested explicitly rather than assumed."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.plain = fixtures.make_user("plain", [fixtures.APPROVER_ROLE])
		cls.manager = fixtures.make_user("manager", [fixtures.APPROVER_ROLE, "System Manager"])

	def test_administrator_is_unrestricted(self):
		self.assertTrue(scope.has_unrestricted_scope("Administrator"))

	def test_system_manager_is_unrestricted(self):
		self.assertTrue(scope.has_unrestricted_scope(self.manager))

	def test_a_plain_user_is_not(self):
		self.assertFalse(scope.has_unrestricted_scope(self.plain))

	def test_unrestricted_scope_covers_the_whole_tree(self):
		covered = self.scope_for(self.manager, fixtures.APPROVER_ROLE)

		for key in ("region", "county_a", "ward_a1", "county_b", "ward_b1", "county_c", "ward_c1"):
			self.assertIn(self.tree[key], covered, key)

	def test_unrestricted_needs_no_assignment(self):
		self.assertEqual(
			frappe.db.count("Geo Assignment", {"user": self.manager}),
			0,
			"the bypass must not be an artefact of a fixture assignment",
		)
