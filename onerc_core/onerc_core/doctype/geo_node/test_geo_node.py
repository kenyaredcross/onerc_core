# Copyright (c) 2026, Kelvin Njenga and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.geo.services import adapter
from onerc_core.geo.tests import fixtures
from onerc_core.onerc_core.doctype.geo_node.geo_node import GeoNode, get_full_path

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class IntegrationTestGeoNode(IntegrationTestCase):
	"""Integration tests for GeoNode."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.region, cls.county = fixtures.make_levels(fixtures.THREE_LEVEL_PREFIX, ["Region", "County"])
		cls.central = fixtures.make_node("Central", cls.region, is_group=True)
		cls.coast = fixtures.make_node("Coast", cls.region, is_group=True)

	def _make_node(self, label, level, parent=None, **kwargs):
		"""Create a node and drop it when the test ends.

		Sibling-name uniqueness is a cross-row constraint, so tests must not leak
		nodes into each other — IntegrationTestCase only rolls back once the whole
		class is done, not per test. Same reasoning as `_make_level` in the Geo
		Level tests.
		"""
		name = fixtures.make_node(label, level, parent, **kwargs)
		self.addCleanup(frappe.delete_doc, "Geo Node", name, force=True)

		return name

	def test_docname_is_opaque(self):
		node = self._make_node("Kiambu", self.county, self.central)

		self.assertTrue(node.startswith("GEO-"))
		self.assertNotIn("Kiambu", node)
		self.assertNotIn(self.county, node)

	def test_same_name_under_different_parents_is_accepted(self):
		"""Regression: the old `{geo_level}-{geo_node_name}` docname threw here."""
		first = self._make_node("Kihara", self.county, self.central)
		second = self._make_node("Kihara", self.county, self.coast)

		self.assertNotEqual(first, second)
		self.assertEqual(
			frappe.db.get_value("Geo Node", first, "geo_node_name"),
			frappe.db.get_value("Geo Node", second, "geo_node_name"),
		)

	def test_sibling_names_must_be_unique(self):
		self._make_node("Kiambu", self.county, self.central)

		with self.assertRaises(frappe.ValidationError):
			self._make_node("Kiambu", self.county, self.central)

	def test_sibling_name_uniqueness_ignores_case(self):
		self._make_node("Kiambu", self.county, self.central)

		with self.assertRaises(frappe.ValidationError):
			self._make_node("kIaMbU", self.county, self.central)

	def test_sibling_name_uniqueness_ignores_surrounding_whitespace(self):
		self._make_node("Kiambu", self.county, self.central)

		with self.assertRaises(frappe.ValidationError):
			self._make_node("  Kiambu  ", self.county, self.central)

	def test_root_siblings_must_be_unique(self):
		"""Roots share an empty parent, so grouping them is a distinct code path."""
		self._make_node("Nyanza", self.region, is_group=True)

		with self.assertRaises(frappe.ValidationError):
			self._make_node("nyanza", self.region, is_group=True)

	def test_a_node_can_be_resaved_without_colliding_with_itself(self):
		"""The uniqueness check must exclude the row being saved."""
		nakuru = self._make_node("Nakuru", self.county, self.central)

		doc = frappe.get_doc("Geo Node", nakuru)
		doc.geo_code = "047"
		doc.save()

		self.assertEqual(doc.geo_code, "047")

	def test_parent_is_required_when_the_level_requires_it(self):
		with self.assertRaises(frappe.MandatoryError):
			self._make_node("Orphaned County", self.county)

	def test_a_parent_at_a_deeper_level_is_rejected(self):
		"""A Region may not be filed under a County.

		Nothing related the tree to the level ladder before this, so a hierarchy
		could be nested in an order its own levels contradict. Anything that then
		read depth off the level ladder walked the chain in an order that was not
		the tree's — which is how approver routing reached past the nearest holder.
		"""
		kiambu = self._make_node("Kiambu", self.county, self.central)

		with self.assertRaises(frappe.ValidationError):
			self._make_node("Upside Down", self.region, kiambu)

	def test_a_parent_at_the_same_level_is_rejected(self):
		"""Strictly shallower — a County under a County is not a hierarchy."""
		with self.assertRaises(frappe.ValidationError):
			self._make_node("Nested Region", self.region, self.central, is_group=True)

	def test_a_parent_at_a_shallower_level_is_accepted(self):
		node = self._make_node("Nakuru", self.county, self.central)

		self.assertTrue(frappe.db.exists("Geo Node", node))

	def test_the_rejection_names_both_levels(self):
		"""A rule nobody can act on is a rule that gets worked around."""
		kiambu = self._make_node("Kiambu", self.county, self.central)

		with self.assertRaises(frappe.ValidationError) as raised:
			self._make_node("Upside Down", self.region, kiambu)

		message = str(raised.exception)

		self.assertIn(self.region, message)
		self.assertIn(self.county, message)

	def test_top_level_node_needs_no_parent(self):
		node = self._make_node("Rift Valley", self.region)

		self.assertTrue(frappe.db.exists("Geo Node", node))

	def test_get_full_path_helper(self):
		kiambu = self._make_node("Kiambu", self.county, self.central)

		self.assertEqual(get_full_path(kiambu), "Kiambu — Central")

	def test_denormalised_geo_level_order_is_gone(self):
		self.assertIsNone(frappe.get_meta("Geo Node").get_field("geo_level_order"))

	def test_doctype_carries_no_autoname_expression(self):
		"""The controller is the single source of truth for naming."""
		self.assertFalse(frappe.get_meta("Geo Node").autoname)

	def test_nsm_parent_field_is_declared_explicitly(self):
		"""NestedSet.on_trash() derives `geo_node_parent` when this is unset."""
		self.assertEqual(GeoNode.nsm_parent_field, "parent_geo_node")


class TestSkippingALevel(IntegrationTestCase):
	"""A parent more than one rung up warns; it never refuses.

	Strict adjacency is a policy some societies hold and others do not: a district
	with no sub-district, a city that is its own county, a national programme
	registering straight under the country. A hard rule would reject the real tree
	in favour of an idealised ladder, so the entry surface points it out and the
	society decides.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.region, cls.county, cls.ward = fixtures.make_levels(
			fixtures.THREE_LEVEL_PREFIX, ["Region", "County", "Ward"]
		)
		cls.central = fixtures.make_node("Central", cls.region, is_group=True)

	def setUp(self):
		super().setUp()
		frappe.clear_messages()

	def _make_node(self, label, level, parent=None, **kwargs):
		name = fixtures.make_node(label, level, parent, **kwargs)
		self.addCleanup(frappe.delete_doc, "Geo Node", name, force=True)

		return name

	def _titles(self) -> list[str]:
		return [message.get("title") for message in frappe.get_message_log()]

	def test_a_parent_two_rungs_up_warns(self):
		self._make_node("Orphan Ward", self.ward, self.central)

		self.assertIn("A Level Was Skipped", self._titles())

	def test_it_saves_all_the_same(self):
		"""The half that matters: a valid tree is never rejected for tidiness."""
		node = self._make_node("Orphan Ward", self.ward, self.central)

		self.assertTrue(frappe.db.exists("Geo Node", node))

	def test_the_warning_names_both_levels_and_the_parent(self):
		"""A warning nobody can act on is noise."""
		self._make_node("Orphan Ward", self.ward, self.central)

		message = " ".join(entry.get("message", "") for entry in frappe.get_message_log())

		self.assertIn(self.central, message)
		self.assertIn(self.region, message)
		self.assertIn(self.ward, message)

	def test_an_adjacent_parent_warns_about_nothing(self):
		"""Without this, the test above would pass for a rule that always fires."""
		self._make_node("Kiambu", self.county, self.central)

		self.assertNotIn("A Level Was Skipped", self._titles())

	def test_a_root_node_warns_about_nothing(self):
		self._make_node("Rift Valley", self.region)

		self.assertNotIn("A Level Was Skipped", self._titles())

	def test_a_parent_at_a_deeper_level_still_refuses(self):
		"""Skipping warns; contradicting still throws. They are different mistakes."""
		kiambu = self._make_node("Kiambu", self.county, self.central)

		with self.assertRaises(frappe.ValidationError):
			self._make_node("Upside Down", self.region, kiambu)


class TestTheGuardSaysWhenItStandsDown(IntegrationTestCase):
	"""An unreadable level order disables the parent check. That must be visible.

	Returning in silence made the guard indistinguishable from a guard that
	passed, so a broken level could switch it off for every node saved underneath
	and nobody would hear about it for a year.

	**The reachable cause is a level that has gone**, not one saved without an
	order: `geo_level_order` is a mandatory Int, so its column is NOT NULL and a
	row cannot carry a blank. What can happen is a node left pointing at a Geo
	Level somebody removed, which is what this fixture reproduces — by deleting
	the row underneath the tree, which is the only way to produce the state and
	the same trick `fixtures.force_level` uses for the misnested chain.

	Two ladders, one broken and one intact, so the negative case is asserted
	against the same code path rather than against its absence.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		# The ladder whose top rung is about to disappear from under its nodes.
		cls.gone_region, cls.gone_county = fixtures.make_levels(
			fixtures.THREE_LEVEL_PREFIX, ["Region", "County"]
		)
		cls.orphaned_parent = fixtures.make_node("Central", cls.gone_region, is_group=True)

		# Delete the parent's level out from under it. Straight SQL: the ORM
		# refuses to remove a level a node still links to, which is the whole
		# point — this is the malformed state that exists on disk from before
		# such a rule, not one the app would let anybody create today.
		frappe.db.sql("DELETE FROM `tabGeo Level` WHERE name = %s", cls.gone_region)
		frappe.clear_document_cache("Geo Level", cls.gone_region)

		# An intact ladder alongside it, for the negative case.
		cls.region, cls.county = fixtures.make_levels(fixtures.FIVE_LEVEL_PREFIX, ["Region", "County"])
		cls.central = fixtures.make_node("Coast", cls.region, is_group=True)

	def _errors_since(self, marker) -> list[str]:
		"""Error Log rows this guard wrote since `marker`.

		Matched on `method`, which is where `frappe.log_error` puts the title;
		`error` holds the message body.
		"""
		return frappe.get_all(
			"Error Log",
			filters={"creation": (">", marker), "method": ("like", "%parent-level check skipped%")},
			pluck="name",
		)

	def test_a_missing_parent_level_is_logged(self):
		marker = frappe.utils.now()

		node = fixtures.make_node("Kiambu", self.gone_county, self.orphaned_parent)
		self.addCleanup(frappe.delete_doc, "Geo Node", node, force=True)

		self.assertTrue(self._errors_since(marker))

	def test_the_node_still_saves(self):
		"""The tree is already written; refusing would punish the wrong person."""
		node = fixtures.make_node("Nakuru", self.gone_county, self.orphaned_parent)
		self.addCleanup(frappe.delete_doc, "Geo Node", node, force=True)

		self.assertTrue(frappe.db.exists("Geo Node", node))

	def test_the_log_names_the_node_and_the_unreadable_level(self):
		"""A log entry nobody can act on is noise."""
		marker = frappe.utils.now()

		node = fixtures.make_node("Muranga", self.gone_county, self.orphaned_parent)
		self.addCleanup(frappe.delete_doc, "Geo Node", node, force=True)

		logged = frappe.db.get_value("Error Log", self._errors_since(marker)[0], "error")

		self.assertIn(self.orphaned_parent, logged)
		self.assertIn(self.gone_county, logged)

	def test_a_readable_ladder_logs_nothing(self):
		"""Without this, the tests above would pass for a guard that always complains."""
		marker = frappe.utils.now()

		node = fixtures.make_node("Kilifi", self.county, self.central)
		self.addCleanup(frappe.delete_doc, "Geo Node", node, force=True)

		self.assertEqual(self._errors_since(marker), [])


class TestAncestryStillIgnoresLevelOrder(IntegrationTestCase):
	"""The constraint every change above had to respect, asserted rather than trusted.

	The entry surface gained an auto-suggested order, a duplicate warning, a
	movable lowest marker and a derived top. None of them may have made ancestry,
	nearness or containment read `geo_level_order` — the tree is the truth, and
	the misnested fixture is the shape that tells the two apart.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.chain = fixtures.build_misnested_chain(fixtures.MISNESTED_PREFIX)

	def test_the_nearest_ancestor_is_the_tree_s_and_not_the_ladder_s(self):
		from onerc_core.geo.services import adapter

		ancestors = adapter.get_ancestors(self.chain["leaf"])

		# Tree order: Inner, Mid, Root. Level order would say Mid, Inner, Root.
		self.assertEqual([row["name"] for row in ancestors[:2]], [self.chain["inner"], self.chain["mid"]])

	def test_the_ladder_really_does_disagree_with_the_tree_here(self):
		"""Without this, the test above could pass on a well-formed tree."""
		from onerc_core.geo.services import adapter

		ancestors = adapter.get_ancestors(self.chain["leaf"])
		orders = [row["geo_level_order"] for row in ancestors]

		self.assertNotEqual(orders, sorted(orders, reverse=True))

	def test_resolve_upward_reaches_the_true_nearest_first(self):
		from onerc_core.geo.services import adapter

		seen = []

		def remember(candidate):
			seen.append(candidate)

			return False

		adapter.resolve_upward(self.chain["leaf"], remember)

		self.assertEqual(seen[:2], [self.chain["leaf"], self.chain["inner"]])

	def test_containment_is_bounds_and_not_order(self):
		from onerc_core.geo.services import adapter

		self.assertTrue(adapter.matches_scope(self.chain["leaf"], self.chain["root"]))
		self.assertTrue(adapter.matches_scope(self.chain["leaf"], self.chain["inner"]))


class IntegrationTestGeoNodeCoordinates(IntegrationTestCase):
	"""Where a node is, and the two ways a coordinate pair can be nothing.

	A point is optional and most nodes will never carry one — a tree is filled in
	from the top down over months. What the rules protect is the case where a
	point exists but is not a point: half a pair, or a pair that is not on the
	earth. Both are worth refusing at save rather than discovering on a map,
	because unlike a missing point — which every reader already handles — a wrong
	one looks like an answer.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.region, cls.county = fixtures.make_levels(fixtures.THREE_LEVEL_PREFIX, ["Region", "County"])
		cls.central = fixtures.make_node("Central", cls.region, is_group=True)

	def _make_node(self, label, **kwargs):
		name = fixtures.make_node(label, self.county, self.central, **kwargs)
		self.addCleanup(frappe.delete_doc, "Geo Node", name, force=True)

		return name

	def test_a_node_without_a_point_is_ordinary(self):
		"""The common case, and it must stay free of ceremony."""
		node = self._make_node("Unplaced")

		self.assertIsNone(adapter.get_point(node))

	def test_a_pair_is_read_back_through_the_adapter(self):
		node = self._make_node("Nairobi")
		doc = frappe.get_doc("Geo Node", node)
		doc.latitude, doc.longitude = -1.2921, 36.8219
		doc.save()

		self.assertEqual(adapter.get_point(node), {"latitude": -1.2921, "longitude": 36.8219})

	def test_half_a_pair_is_refused(self):
		"""An empty Float stores as 0.0, so half a pair would be drawn confidently
		in the Gulf of Guinea."""
		doc = frappe.get_doc("Geo Node", self._make_node("Halved"))
		doc.latitude = -1.2921

		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_a_latitude_off_the_earth_is_refused(self):
		doc = frappe.get_doc("Geo Node", self._make_node("Orbital"))
		doc.latitude, doc.longitude = 200.0, 36.8219

		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_a_longitude_off_the_earth_is_refused(self):
		doc = frappe.get_doc("Geo Node", self._make_node("Far Side"))
		doc.latitude, doc.longitude = -1.2921, 400.0

		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_many_points_come_back_in_one_read(self):
		"""The shape a map wants. Nodes without a point are absent rather than
		present with None, so a caller iterating the answer gets only what it can
		draw."""
		placed = self._make_node("Placed")
		unplaced = self._make_node("Unplaced Too")

		doc = frappe.get_doc("Geo Node", placed)
		doc.latitude, doc.longitude = -4.0435, 39.6682
		doc.save()

		points = adapter.get_points([placed, unplaced])

		self.assertIn(placed, points)
		self.assertNotIn(unplaced, points)

	def test_asking_about_nothing_reads_nothing(self):
		self.assertEqual(adapter.get_points([]), {})
