# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from onerc_core.access.services import scope
from onerc_core.access.services.approvers import RULE_AT_LEVEL, resolve_approvers
from onerc_core.access.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []


class ApproverTestCase(IntegrationTestCase):
	"""Each subclass builds its own tree and assignments in setUpClass.

	Assignments are never written inside a test method here: rollback happens
	once per class, so a method that granted authority would still have granted
	it for the next method. One arrangement per class, asserted from several
	angles, keeps every case honest.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.tree = fixtures.build_tree()


class TestNearestAncestor(ApproverTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.county_approver = fixtures.make_user("county_approver", [fixtures.APPROVER_ROLE])
		fixtures.make_assignment(cls.county_approver, fixtures.APPROVER_ROLE, cls.tree["county_a"])

	def test_resolves_from_a_ward_up_to_the_county(self):
		self.assertEqual(
			resolve_approvers(self.tree["ward_a1"], fixtures.APPROVER_ROLE), [self.county_approver]
		)

	def test_the_node_itself_counts(self):
		""" "Including the node itself" — authority at A approves things at A."""
		self.assertEqual(
			resolve_approvers(self.tree["county_a"], fixtures.APPROVER_ROLE), [self.county_approver]
		)

	def test_every_ward_under_the_county_resolves_to_it(self):
		self.assertEqual(
			resolve_approvers(self.tree["ward_a2"], fixtures.APPROVER_ROLE), [self.county_approver]
		)

	def test_returns_empty_when_nobody_resolves_to_the_root(self):
		"""County B holds nobody, and neither does the region above it.

		Empty is the answer, not an exception. What an unapprovable record does is
		a product decision, and core inventing a fallback approver would make it
		silently.
		"""
		self.assertEqual(resolve_approvers(self.tree["ward_b1"], fixtures.APPROVER_ROLE), [])
		self.assertEqual(resolve_approvers(self.tree["county_c"], fixtures.APPROVER_ROLE), [])

	def test_a_different_role_resolves_to_nobody(self):
		self.assertEqual(resolve_approvers(self.tree["ward_a1"], fixtures.VIEWER_ROLE), [])

	def test_missing_arguments_resolve_to_nobody(self):
		self.assertEqual(resolve_approvers(None, fixtures.APPROVER_ROLE), [])
		self.assertEqual(resolve_approvers(self.tree["ward_a1"], None), [])

	def test_an_unknown_rule_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			resolve_approvers(self.tree["ward_a1"], fixtures.APPROVER_ROLE, rule="whoever_is_free")


class TestNearestWins(ApproverTestCase):
	"""A nearer holder beats a more distant one — that is what "nearest" means."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.at_county = fixtures.make_user("at_county", [fixtures.APPROVER_ROLE])
		cls.at_ward = fixtures.make_user("at_ward", [fixtures.APPROVER_ROLE])

		fixtures.make_assignment(cls.at_county, fixtures.APPROVER_ROLE, cls.tree["county_a"])
		fixtures.make_assignment(cls.at_ward, fixtures.APPROVER_ROLE, cls.tree["ward_a1"])

	def test_the_ward_holder_wins_at_the_ward(self):
		approvers = resolve_approvers(self.tree["ward_a1"], fixtures.APPROVER_ROLE)

		self.assertEqual(approvers, [self.at_ward])
		self.assertNotIn(self.at_county, approvers)

	def test_a_sibling_ward_still_walks_up_to_the_county(self):
		"""Ward A2 has no holder of its own, so the county's authority applies."""
		self.assertEqual(resolve_approvers(self.tree["ward_a2"], fixtures.APPROVER_ROLE), [self.at_county])


class TestMultipleHolders(ApproverTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.first = fixtures.make_user("holder_one", [fixtures.APPROVER_ROLE])
		cls.second = fixtures.make_user("holder_two", [fixtures.APPROVER_ROLE])

		for user in (cls.first, cls.second):
			fixtures.make_assignment(user, fixtures.APPROVER_ROLE, cls.tree["county_a"])

		# A second row for the same user at the same node — legal under ACC-01,
		# and it must not produce a duplicate in the approver list.
		fixtures.make_assignment(cls.first, fixtures.APPROVER_ROLE, cls.tree["county_a"])

	def test_returns_every_holder_at_the_matched_node(self):
		self.assertEqual(
			resolve_approvers(self.tree["ward_a1"], fixtures.APPROVER_ROLE),
			sorted([self.first, self.second]),
		)

	def test_a_duplicate_row_does_not_duplicate_the_approver(self):
		approvers = resolve_approvers(self.tree["ward_a1"], fixtures.APPROVER_ROLE)

		self.assertEqual(len(approvers), len(set(approvers)))

	def test_how_many_must_act_is_not_decided_here(self):
		"""This layer answers "who", never "how many" — that is the approval engine."""
		self.assertEqual(len(resolve_approvers(self.tree["ward_a1"], fixtures.APPROVER_ROLE)), 2)


class TestApproverLiveness(ApproverTestCase):
	"""A dead assignment does not stop the walk — routing continues past it."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.expired = fixtures.make_user("expired_approver", [fixtures.APPROVER_ROLE])
		cls.regional = fixtures.make_user("regional_approver", [fixtures.APPROVER_ROLE])

		fixtures.make_assignment(
			cls.expired, fixtures.APPROVER_ROLE, cls.tree["county_a"], valid_to=add_days(today(), -1)
		)
		fixtures.make_assignment(cls.regional, fixtures.APPROVER_ROLE, cls.tree["region"])

	def test_walks_past_a_county_whose_only_holder_expired(self):
		approvers = resolve_approvers(self.tree["ward_a1"], fixtures.APPROVER_ROLE)

		self.assertEqual(approvers, [self.regional])
		self.assertNotIn(self.expired, approvers)

	def test_the_expired_holder_returns_on_a_date_when_they_were_live(self):
		self.assertEqual(
			resolve_approvers(self.tree["ward_a1"], fixtures.APPROVER_ROLE, on_date=add_days(today(), -30)),
			[self.expired],
		)


class TestAtLevel(ApproverTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.at_county = fixtures.make_user("level_county", [fixtures.APPROVER_ROLE])
		cls.at_region = fixtures.make_user("level_region", [fixtures.APPROVER_ROLE])

		fixtures.make_assignment(cls.at_county, fixtures.APPROVER_ROLE, cls.tree["county_a"])
		fixtures.make_assignment(cls.at_region, fixtures.APPROVER_ROLE, cls.tree["region"])

	def _at(self, node: str, level: str) -> list[str]:
		return resolve_approvers(
			node, fixtures.APPROVER_ROLE, rule=RULE_AT_LEVEL, geo_level=self.tree["levels"][level]
		)

	def test_resolves_at_the_named_level(self):
		self.assertEqual(self._at(self.tree["ward_a1"], "county"), [self.at_county])

	def test_a_higher_level_skips_the_nearer_holder(self):
		"""The point of at_level: policy picks the tier, not proximity."""
		self.assertEqual(self._at(self.tree["ward_a1"], "region"), [self.at_region])

	def test_a_level_below_the_node_resolves_to_nobody(self):
		"""Ward is not in a county's ancestor chain, so there is nothing to find."""
		self.assertEqual(self._at(self.tree["county_a"], "ward"), [])

	def test_the_named_level_holding_nobody_returns_empty(self):
		self.assertEqual(self._at(self.tree["ward_b1"], "county"), [])

	def test_the_level_is_required(self):
		with self.assertRaises(frappe.MandatoryError):
			resolve_approvers(self.tree["ward_a1"], fixtures.APPROVER_ROLE, rule=RULE_AT_LEVEL)


class TestRoutingAndScopeAgree(ApproverTestCase):
	"""The reason both read Geo Assignment: they cannot contradict each other.

	If routing named someone whose scope excluded the record, the product would
	route an approval to a user who then could not open it. One source of truth
	is what forbids that, and this is the test that would catch it drifting.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.county = fixtures.make_user("agree_county", [fixtures.APPROVER_ROLE])
		cls.region = fixtures.make_user("agree_region", [fixtures.APPROVER_ROLE])

		fixtures.make_assignment(cls.county, fixtures.APPROVER_ROLE, cls.tree["county_a"])
		fixtures.make_assignment(cls.region, fixtures.APPROVER_ROLE, cls.tree["region"])

	def test_every_resolved_approver_can_reach_the_record(self):
		for node_key in ("ward_a1", "ward_a2", "county_a", "ward_b1", "ward_c1", "region"):
			node = self.tree[node_key]

			for approver in resolve_approvers(node, fixtures.APPROVER_ROLE):
				self.assertIn(
					node,
					scope.get_user_geo_scope(approver, fixtures.APPROVER_ROLE),
					f"{approver} was routed {node_key} but their scope excludes it",
				)
