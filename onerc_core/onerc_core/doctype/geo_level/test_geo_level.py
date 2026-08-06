# Copyright (c) 2026, Kelvin Njenga and Contributors
# See license.txt

"""Geo Level entry integrity.

The theme running through all of it: **order is guidance, the tree is truth.**
So exactly one order-based rule refuses (a top rung cannot require a parent) and
the rest inform. Each warning test therefore asserts two things — that the
message was raised, *and* that the row saved anyway — because a warning that
turned out to block would forbid the multi-society shape these suites exist to
protect.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import cint

from onerc_core.geo.services import adapter
from onerc_core.geo.tests import fixtures
from onerc_core.onerc_core.doctype.geo_level.geo_level import (
	next_available_order,
	shares_a_hierarchy,
)

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class GeoLevelTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()
		cls.quieten_the_site_s_own_ladder()

	@classmethod
	def quieten_the_site_s_own_ladder(cls):
		"""Deactivate every level this suite did not create.

		Almost everything below is a statement about the ladder *as a whole* —
		what the next free rung is, which level is the top, whether an order
		collides. On a bare test site those answers are obvious; on a bench
		carrying a real society's configuration they are that society's, and the
		suite would assert whatever happened to be seeded.

		Deactivating rather than deleting: a level with nodes hanging off it
		cannot be deleted, and `is_active = 0` is exactly the state these rules
		are supposed to ignore. Written straight to the column so no controller
		runs, and rolled back with the rest of the transaction at class teardown,
		so the site's own configuration is untouched afterwards.
		"""
		for name in frappe.get_all("Geo Level", filters={"is_active": 1}, pluck="name"):
			frappe.db.set_value("Geo Level", name, "is_active", 0, update_modified=False)
			frappe.clear_document_cache("Geo Level", name)

	def setUp(self):
		super().setUp()
		# Warnings are the product here, so every test starts from a clean log and
		# nothing inherits a message another test provoked.
		frappe.clear_messages()

	def _make_level(self, key, label, order, **kwargs):
		"""Create a level and drop it when the test ends.

		These tests assert on cross-row state (one active lowest, the next free
		order), so they must not leak rows into each other — IntegrationTestCase
		only rolls back once the whole class is done, not per test.
		"""
		name = fixtures.make_level(key, label, order, **kwargs)
		self.addCleanup(frappe.delete_doc, "Geo Level", name, force=True)

		return name

	def _messages(self) -> str:
		"""Every message raised so far, flattened, for substring assertions."""
		return " ".join(
			f"{message.get('title', '')} {message.get('message', '')}" for message in frappe.get_message_log()
		)

	def _titles(self) -> list[str]:
		return [message.get("title") for message in frappe.get_message_log()]


class TestTheFieldItself(GeoLevelTestCase):
	def test_is_active_defaults_to_enabled(self):
		"""A new level is usable without an extra click."""
		self.assertEqual(cint(frappe.new_doc("Geo Level").is_active), 1)

	def test_geo_level_key_is_required(self):
		"""The key *is* the docname, so a missing one must fail early and clearly.

		`reqd` is what marks the field mandatory on the form. Server-side the
		naming layer gets there first — `autoname` runs before the mandatory
		check, so a keyless insert throws "Geo Level Key is required" out of
		`_field_autoname` rather than as a MandatoryError. Both paths are
		asserted: the flag for the form, the throw for the API.
		"""
		self.assertTrue(frappe.get_meta("Geo Level").get_field("geo_level_key").reqd)

		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Geo Level",
					"geo_level_name": "Keyless",
					"geo_level_order": 9,
				}
			).insert()

	def test_there_is_no_stored_highest_flag(self):
		"""The top is derived. A field would be a third answer to one question.

		Asserted against the schema rather than remembered, because adding one is
		exactly the shortcut somebody reaches for when a form needs to show which
		level is the top.
		"""
		meta = frappe.get_meta("Geo Level")

		for fieldname in ("is_highest_level", "is_highest", "is_root", "is_top_level", "parent_level"):
			self.assertIsNone(meta.get_field(fieldname), fieldname)


class TestTheOrderIsSuggested(GeoLevelTestCase):
	def test_a_first_level_with_no_order_starts_at_one(self):
		level = frappe.get_doc(
			{"doctype": "Geo Level", "geo_level_key": "T3-1", "geo_level_name": "Region"}
		).insert()
		self.addCleanup(frappe.delete_doc, "Geo Level", level.name, force=True)

		self.assertEqual(level.geo_level_order, 1)

	def test_a_later_level_with_no_order_takes_the_next_rung(self):
		self._make_level("T3-1", "Region", 1)
		self._make_level("T3-2", "County", 2)

		level = frappe.get_doc(
			{"doctype": "Geo Level", "geo_level_key": "T3-3", "geo_level_name": "Ward"}
		).insert()
		self.addCleanup(frappe.delete_doc, "Geo Level", level.name, force=True)

		self.assertEqual(level.geo_level_order, 3)

	def test_an_explicit_order_is_respected(self):
		"""The suggestion is a default. It must never overwrite an answer.

		This is what keeps every fixture that numbers its own ladder working, and
		what lets a society insert a tier between two others.
		"""
		self._make_level("T3-1", "Region", 1)
		self._make_level("T3-2", "County", 2)

		inserted = self._make_level("T3-9", "Sub County", 2)

		self.assertEqual(frappe.db.get_value("Geo Level", inserted, "geo_level_order"), 2)

	def test_zero_counts_as_blank(self):
		"""The field's own guidance starts at 1, so there is no rung 0 to have meant."""
		self._make_level("T3-1", "Region", 1)

		level = frappe.get_doc(
			{
				"doctype": "Geo Level",
				"geo_level_key": "T3-2",
				"geo_level_name": "County",
				"geo_level_order": 0,
			}
		).insert()
		self.addCleanup(frappe.delete_doc, "Geo Level", level.name, force=True)

		self.assertEqual(level.geo_level_order, 2)

	def test_an_inactive_level_frees_its_number(self):
		self._make_level("T3-1", "Region", 1)
		self._make_level("T3-2", "County", 2, is_active=False)

		self.assertEqual(next_available_order(), 2)

	def test_the_helper_answers_one_on_an_empty_ladder(self):
		self.assertEqual(next_available_order(), 1)

	def test_the_suggestion_does_not_move_an_existing_row(self):
		"""It is a `before_insert`. Re-saving a level must not renumber it."""
		region = self._make_level("T3-1", "Region", 1)
		self._make_level("T3-2", "County", 2)

		doc = frappe.get_doc("Geo Level", region)
		doc.description = "Touched"
		doc.save()

		self.assertEqual(doc.geo_level_order, 1)


class TestTheDuplicateOrderWarning(GeoLevelTestCase):
	def test_a_reused_order_warns(self):
		self._make_level("T3-1", "Region", 1)

		frappe.clear_messages()
		self._make_level("T5-1", "Province", 1)

		self.assertIn("Order Already In Use", self._titles())

	def test_a_reused_order_does_not_block(self):
		"""The assertion the multi-society shape depends on.

		Two societies on one site each number their own ladder from 1. If this
		ever became a throw, the second society could not be configured at all,
		and every parallel-ladder fixture in every consuming app would fail.
		"""
		self._make_level("T3-1", "Region", 1)
		twin = self._make_level("T5-1", "Province", 1)

		self.assertTrue(frappe.db.exists("Geo Level", twin))
		self.assertEqual(frappe.db.get_value("Geo Level", twin, "geo_level_order"), 1)

	def test_two_parallel_ladders_save_without_a_single_refusal(self):
		"""The whole shape, end to end, exactly as consuming apps build it."""
		for order, label in enumerate(["Region", "County", "Ward"], start=1):
			self._make_level(f"T3-{order}", label, order)

		for order, label in enumerate(["Province", "District", "Village"], start=1):
			self._make_level(f"T5-{order}", label, order)

		orders = frappe.get_all(
			"Geo Level", filters={"is_active": 1}, pluck="geo_level_order", order_by="name"
		)

		self.assertEqual(sorted(orders), [1, 1, 2, 2, 3, 3])

	def test_a_unique_order_warns_about_nothing(self):
		"""Without this, the warning tests would pass for a rule that always fires."""
		self._make_level("T3-1", "Region", 1)

		frappe.clear_messages()
		self._make_level("T3-2", "County", 2)

		self.assertNotIn("Order Already In Use", self._titles())

	def test_an_inactive_level_is_not_a_collision(self):
		self._make_level("T3-1", "Region", 1, is_active=False)

		frappe.clear_messages()
		self._make_level("T5-1", "Province", 1)

		self.assertNotIn("Order Already In Use", self._titles())

	def test_levels_with_no_nodes_yet_are_reported_as_undecidable(self):
		"""While a ladder is still being written down, nothing can be told apart."""
		self._make_level("T3-1", "Region", 1)

		frappe.clear_messages()
		self._make_level("T5-1", "Province", 1)

		self.assertIn("different hierarchies", self._messages())

	def test_a_collision_inside_one_hierarchy_is_named_as_such(self):
		"""When the tree can settle it, the message stops hedging.

		Two levels are in the same hierarchy when a node at each sits under one
		root. That is a fact about the tree, which is the only thing entitled to
		answer a structural question here.
		"""
		region = self._make_level("T3-1", "Region", 1)
		county = self._make_level("T3-2", "County", 2)

		central = fixtures.make_node("Central", region, is_group=True)
		self.addCleanup(frappe.delete_doc, "Geo Node", central, force=True)
		kiambu = fixtures.make_node("Kiambu", county, central)
		self.addCleanup(frappe.delete_doc, "Geo Node", kiambu, force=True)

		# Region moves down onto County's rung, now that both carry nodes in one
		# tree. Region rather than County, because County requires a parent and
		# the top rung may not — that rule still refuses, and it is not this one.
		doc = frappe.get_doc("Geo Level", region)
		doc.geo_level_order = 2
		frappe.clear_messages()
		doc.save()

		self.assertIn("same hierarchy", self._messages())
		self.assertEqual(frappe.db.get_value("Geo Level", region, "geo_level_order"), 2)

	def test_the_shared_hierarchy_probe_is_false_across_separate_trees(self):
		"""The negative half. Without it the probe could return True always."""
		region = self._make_level("T3-1", "Region", 1)
		province = self._make_level("T5-1", "Province", 1)

		here = fixtures.make_node("Central", region)
		self.addCleanup(frappe.delete_doc, "Geo Node", here, force=True)
		there = fixtures.make_node("Coastal", province)
		self.addCleanup(frappe.delete_doc, "Geo Node", there, force=True)

		self.assertFalse(shares_a_hierarchy(region, province))

	def test_the_probe_is_true_within_one_tree(self):
		region = self._make_level("T3-1", "Region", 1)
		county = self._make_level("T3-2", "County", 2)

		central = fixtures.make_node("Central", region, is_group=True)
		self.addCleanup(frappe.delete_doc, "Geo Node", central, force=True)
		kiambu = fixtures.make_node("Kiambu", county, central)
		self.addCleanup(frappe.delete_doc, "Geo Node", kiambu, force=True)

		self.assertTrue(shares_a_hierarchy(region, county))


class TestTheLowestMarkerMoves(GeoLevelTestCase):
	def test_marking_a_deeper_level_lowest_unsets_the_previous_one(self):
		"""The behaviour this change exists for.

		Before it, this threw, and adding a deeper tier meant finding and
		clearing the incumbent by hand before the new row would save at all.
		"""
		self._make_level("T3-1", "Region", 1)
		county = self._make_level("T3-2", "County", 2, is_lowest=True)

		ward = self._make_level("T3-3", "Ward", 3, is_lowest=True)

		self.assertFalse(frappe.db.get_value("Geo Level", county, "is_lowest_level"))
		self.assertTrue(frappe.db.get_value("Geo Level", ward, "is_lowest_level"))

	def test_it_does_not_throw(self):
		"""Stated separately, because "moved" and "did not refuse" are two claims."""
		self._make_level("T3-2", "County", 2, is_lowest=True)

		ward = self._make_level("T3-3", "Ward", 3, is_lowest=True)

		self.assertTrue(frappe.db.exists("Geo Level", ward))

	def test_at_most_one_active_lowest_holds_afterwards(self):
		"""The invariant survives as a result rather than as a refusal."""
		self._make_level("T3-1", "Region", 1)
		self._make_level("T3-2", "County", 2, is_lowest=True)
		self._make_level("T3-3", "Ward", 3, is_lowest=True)

		flagged = frappe.get_all("Geo Level", filters={"is_active": 1, "is_lowest_level": 1}, pluck="name")

		self.assertEqual(len(flagged), 1)

	def test_the_move_is_announced(self):
		self._make_level("T3-2", "County", 2, is_lowest=True)

		frappe.clear_messages()
		self._make_level("T3-3", "Ward", 3, is_lowest=True)

		self.assertIn("Lowest Level Moved", self._titles())

	def test_an_inactive_lowest_level_is_left_alone(self):
		"""The exemption, intact: a retired tier keeps its flag and fights nobody."""
		retired = self._make_level("T3-2", "Sub Location", 2, is_lowest=True, is_active=False)

		self._make_level("T3-3", "Ward", 3, is_lowest=True)

		self.assertTrue(frappe.db.get_value("Geo Level", retired, "is_lowest_level"))

	def test_an_inactive_level_does_not_take_the_marker(self):
		ward = self._make_level("T3-3", "Ward", 3, is_lowest=True)

		self._make_level("T3-4", "Village", 4, is_lowest=True, is_active=False)

		self.assertTrue(frappe.db.get_value("Geo Level", ward, "is_lowest_level"))

	def test_the_same_level_can_be_resaved_while_lowest(self):
		"""The move must exclude the row being saved, or it would unseat itself."""
		ward = self._make_level("T3-3", "Ward", 3, is_lowest=True)

		doc = frappe.get_doc("Geo Level", ward)
		doc.description = "Smallest administrative unit"
		doc.save()

		self.assertTrue(doc.is_lowest_level)
		self.assertTrue(frappe.db.get_value("Geo Level", ward, "is_lowest_level"))

	def test_a_lowest_marker_above_a_deeper_rung_warns(self):
		self._make_level("T3-3", "Ward", 3)

		frappe.clear_messages()
		self._make_level("T3-2", "County", 2, is_lowest=True)

		self.assertIn("Lowest Is Not The Deepest", self._titles())

	def test_that_warning_does_not_block_either(self):
		self._make_level("T3-3", "Ward", 3)

		county = self._make_level("T3-2", "County", 2, is_lowest=True)

		self.assertTrue(frappe.db.get_value("Geo Level", county, "is_lowest_level"))

	def test_the_deepest_rung_warns_about_nothing(self):
		self._make_level("T3-2", "County", 2)

		frappe.clear_messages()
		self._make_level("T3-3", "Ward", 3, is_lowest=True)

		self.assertNotIn("Lowest Is Not The Deepest", self._titles())


class TestTheTopLevelIsDerived(GeoLevelTestCase):
	def test_the_shallowest_active_level_is_the_top(self):
		region = self._make_level("T3-1", "Region", 1)
		self._make_level("T3-2", "County", 2)

		self.assertTrue(adapter.is_top_level(region))
		self.assertEqual([row["key"] for row in adapter.top_levels()], [region])

	def test_a_deeper_level_is_not_the_top(self):
		self._make_level("T3-1", "Region", 1)
		county = self._make_level("T3-2", "County", 2)

		self.assertFalse(adapter.is_top_level(county))

	def test_adding_a_shallower_level_moves_the_top(self):
		"""Derived means it follows the data with nothing to keep in step."""
		county = self._make_level("T3-2", "County", 2)

		self.assertTrue(adapter.is_top_level(county))

		region = self._make_level("T3-1", "Region", 1)

		self.assertTrue(adapter.is_top_level(region))
		self.assertFalse(adapter.is_top_level(county))

	def test_an_inactive_level_is_never_the_top(self):
		self._make_level("T3-1", "Region", 1, is_active=False)
		county = self._make_level("T3-2", "County", 2)

		self.assertTrue(adapter.is_top_level(county))
		self.assertFalse(adapter.is_top_level("T3-1"))

	def test_two_levels_sharing_the_shallowest_rung_are_both_reported(self):
		"""Plural, and not hedging: on a two-society site this is the real answer."""
		region = self._make_level("T3-1", "Region", 1)
		province = self._make_level("T5-1", "Province", 1)

		self.assertEqual(sorted(row["key"] for row in adapter.top_levels()), sorted([region, province]))

	def test_an_empty_ladder_has_no_top(self):
		self.assertEqual(adapter.top_levels(), [])
		self.assertFalse(adapter.is_top_level("nothing-at-all"))

	def test_the_overview_marks_the_top_the_lowest_and_the_collisions(self):
		region = self._make_level("T3-1", "Region", 1)
		county = self._make_level("T3-2", "County", 2, is_lowest=True)
		province = self._make_level("T5-1", "Province", 1)

		overview = {row["key"]: row for row in adapter.hierarchy_overview()}

		self.assertTrue(overview[region]["is_top"])
		self.assertTrue(overview[province]["is_top"])
		self.assertTrue(overview[county]["is_lowest"])
		self.assertTrue(overview[county]["requires_parent"])
		self.assertEqual(overview[region]["shares_order_with"], [province])
		self.assertEqual(overview[county]["shares_order_with"], [])

	def test_the_overview_is_ordered_top_down(self):
		self._make_level("T3-3", "Ward", 3)
		self._make_level("T3-1", "Region", 1)
		self._make_level("T3-2", "County", 2)

		self.assertEqual([row["order"] for row in adapter.hierarchy_overview()], [1, 2, 3])

	def test_the_overview_leaves_inactive_levels_out(self):
		self._make_level("T3-1", "Region", 1)
		self._make_level("T3-2", "County", 2, is_active=False)

		self.assertEqual([row["key"] for row in adapter.hierarchy_overview()], ["T3-1"])


class TestTheOneRuleThatStillRefuses(GeoLevelTestCase):
	def test_top_level_cannot_require_a_parent(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_level("T3-1", "Region", 1, requires_parent=True)

	def test_lower_levels_may_require_a_parent(self):
		self._make_level("T3-1", "Region", 1)

		county = self._make_level("T3-2", "County", 2)

		self.assertTrue(frappe.db.get_value("Geo Level", county, "requires_parent"))
