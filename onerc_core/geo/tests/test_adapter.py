# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

from typing import ClassVar

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.geo.services import adapter
from onerc_core.geo.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []


class TestGeoAdapterThreeLevels(IntegrationTestCase):
	"""Region → County → Ward.

	                 Central                  Coast
	                /       \\                   |
	           Kiambu       Nyeri            Mombasa
	           /     \\         |                |
	      Kihara   Kabete    Kihara           Likoni

	"Kihara" appears twice under one level, in different counties — legitimate,
	and the thing the old `{geo_level}-{geo_node_name}` docname made impossible.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.region, cls.county, cls.ward = fixtures.make_levels(
			fixtures.THREE_LEVEL_PREFIX, ["Region", "County", "Ward"]
		)

		cls.central = fixtures.make_node("Central", cls.region, is_group=True)
		cls.coast = fixtures.make_node("Coast", cls.region, is_group=True)
		cls.kiambu = fixtures.make_node("Kiambu", cls.county, cls.central, is_group=True)
		cls.nyeri = fixtures.make_node("Nyeri", cls.county, cls.central, is_group=True)
		cls.mombasa = fixtures.make_node("Mombasa", cls.county, cls.coast, is_group=True)
		cls.kihara = fixtures.make_node("Kihara", cls.ward, cls.kiambu)
		cls.kabete = fixtures.make_node("Kabete", cls.ward, cls.kiambu)
		cls.kihara_nyeri = fixtures.make_node("Kihara", cls.ward, cls.nyeri)
		cls.likoni = fixtures.make_node("Likoni", cls.ward, cls.mombasa)

	def test_get_root_regions_returns_parentless_nodes(self):
		roots = adapter.get_root_regions()

		self.assertEqual([root.name for root in roots], [self.central, self.coast])
		self.assertEqual([root.geo_level_order for root in roots], [1, 1])

	def test_get_children_is_one_level_down_only(self):
		children = adapter.get_children(self.central)

		self.assertEqual([child.name for child in children], [self.kiambu, self.nyeri])
		self.assertNotIn(self.kihara, [child.name for child in children])

	def test_get_ancestors_is_nearest_first(self):
		ancestors = adapter.get_ancestors(self.kihara)

		self.assertEqual([a.name for a in ancestors], [self.kiambu, self.central])
		# Nearest-first *is* descending geo_level_order — asserted, not assumed.
		self.assertEqual([a.geo_level_order for a in ancestors], [2, 1])

	def test_ancestor_order_ignores_recency(self):
		"""Ordering must come from the Geo Level join, not a framework default.

		Touching the root makes it the most recently modified node. A default
		`modified desc` ordering would surface Central first; the explicit
		geo_level_order join must still put Kiambu first.
		"""
		frappe.get_doc("Geo Node", self.central).save()

		ancestors = adapter.get_ancestors(self.kihara)

		self.assertEqual([a.name for a in ancestors], [self.kiambu, self.central])

	def test_get_ancestors_of_a_root_is_empty(self):
		self.assertEqual(adapter.get_ancestors(self.central), [])

	def test_get_descendants_reaches_every_depth(self):
		descendants = adapter.get_descendants(self.central)

		self.assertEqual(
			set(descendants), {self.kiambu, self.nyeri, self.kihara, self.kabete, self.kihara_nyeri}
		)
		self.assertNotIn(self.central, descendants)
		self.assertNotIn(self.likoni, descendants)

	def test_get_descendants_of_a_leaf_is_empty(self):
		self.assertEqual(adapter.get_descendants(self.kihara), [])

	def test_get_level(self):
		level = adapter.get_level(self.kihara)

		self.assertEqual(level.key, self.ward)
		self.assertEqual(level.name, "Ward")
		self.assertEqual(level.order, 3)
		self.assertTrue(level.is_lowest)

	def test_level_labels_are_ordered_top_down(self):
		labels = adapter.level_labels()

		self.assertEqual([label.key for label in labels], [self.region, self.county, self.ward])
		self.assertEqual([label.order for label in labels], [1, 2, 3])

	def test_is_leaf(self):
		self.assertTrue(adapter.is_leaf(self.kihara))
		self.assertFalse(adapter.is_leaf(self.kiambu))
		self.assertFalse(adapter.is_leaf(self.central))

	def test_get_full_path(self):
		self.assertEqual(adapter.get_full_path(self.kihara), "Kihara — Kiambu — Central")
		self.assertEqual(adapter.get_full_path(self.central), "Central")

	def test_same_name_under_different_parents_is_allowed(self):
		"""The docname is opaque, so two Kiharas coexist and stay distinguishable."""
		self.assertNotEqual(self.kihara, self.kihara_nyeri)
		self.assertEqual(adapter.get_full_path(self.kihara_nyeri), "Kihara — Nyeri — Central")

	def test_resolve_upward_finds_nearest_match(self):
		match = adapter.resolve_upward(self.kihara, self._at_level(self.county))

		self.assertEqual(match, self.kiambu)

	def test_resolve_upward_considers_the_node_itself_first(self):
		match = adapter.resolve_upward(self.kihara, self._at_level(self.ward))

		self.assertEqual(match, self.kihara)

	def test_resolve_upward_returns_none_when_nothing_matches(self):
		self.assertIsNone(adapter.resolve_upward(self.kihara, lambda node: False))

	def test_matches_scope_self(self):
		self.assertTrue(adapter.matches_scope(self.kihara, self.kihara))

	def test_matches_scope_descendant(self):
		self.assertTrue(adapter.matches_scope(self.kihara, self.central))
		self.assertTrue(adapter.matches_scope(self.kihara, self.kiambu))

	def test_matches_scope_ancestor(self):
		self.assertTrue(adapter.matches_scope(self.central, self.kihara, allow_ancestor=True))
		self.assertFalse(adapter.matches_scope(self.central, self.kihara, allow_ancestor=False))

	def test_matches_scope_unrelated(self):
		self.assertFalse(adapter.matches_scope(self.kihara, self.coast))
		self.assertFalse(adapter.matches_scope(self.kihara, self.kihara_nyeri))
		self.assertFalse(adapter.matches_scope(self.kihara, self.likoni))

	def test_missing_node_is_rejected(self):
		with self.assertRaises(frappe.DoesNotExistError):
			adapter.get_ancestors("GEO-does-not-exist")

	@staticmethod
	def _at_level(level):
		def predicate(node):
			return frappe.db.get_value("Geo Node", node, "geo_level") == level

		return predicate


class TestGeoAdapterFiveLevels(IntegrationTestCase):
	"""Country → Region → County → Sub County → Ward.

	Same assertions, two levels deeper. If anything in the adapter had a depth
	assumption baked in, it fails here and passes above.
	"""

	LABELS: ClassVar[list[str]] = ["Country", "Region", "County", "Sub County", "Ward"]

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.levels = fixtures.make_levels(fixtures.FIVE_LEVEL_PREFIX, cls.LABELS)

		cls.kenya, cls.central, cls.kiambu, cls.kabete, cls.kihara = fixtures.make_chain(
			cls.levels, ["Kenya", "Central", "Kiambu", "Kabete", "Kihara"]
		)
		# A second branch, off the root, that shares no ancestry with Kihara
		# below Kenya.
		cls.coast = fixtures.make_node("Coast", cls.levels[1], cls.kenya, is_group=True)
		cls.mombasa = fixtures.make_node("Mombasa", cls.levels[2], cls.coast)

	def test_get_ancestors_is_nearest_first_at_depth(self):
		ancestors = adapter.get_ancestors(self.kihara)

		self.assertEqual([a.name for a in ancestors], [self.kabete, self.kiambu, self.central, self.kenya])
		self.assertEqual([a.geo_level_order for a in ancestors], [4, 3, 2, 1])

	def test_ancestor_order_ignores_recency_at_depth(self):
		frappe.get_doc("Geo Node", self.kenya).save()
		frappe.get_doc("Geo Node", self.central).save()

		ancestors = adapter.get_ancestors(self.kihara)

		self.assertEqual([a.name for a in ancestors], [self.kabete, self.kiambu, self.central, self.kenya])

	def test_get_full_path_spans_five_levels(self):
		self.assertEqual(adapter.get_full_path(self.kihara), "Kihara — Kabete — Kiambu — Central — Kenya")

	def test_get_descendants_reaches_the_bottom(self):
		descendants = adapter.get_descendants(self.kenya)

		self.assertEqual(
			set(descendants),
			{self.central, self.kiambu, self.kabete, self.kihara, self.coast, self.mombasa},
		)

	def test_level_labels_are_ordered_top_down(self):
		labels = adapter.level_labels()

		self.assertEqual([label.order for label in labels], [1, 2, 3, 4, 5])
		self.assertEqual([label.name for label in labels], self.LABELS)

	def test_only_the_deepest_level_is_lowest(self):
		labels = adapter.level_labels()

		self.assertEqual([bool(label.is_lowest) for label in labels], [False] * 4 + [True])

	def test_is_leaf_at_depth(self):
		self.assertTrue(adapter.is_leaf(self.kihara))
		self.assertFalse(adapter.is_leaf(self.kabete))
		self.assertFalse(adapter.is_leaf(self.kenya))

	def test_matches_scope_across_four_levels(self):
		self.assertTrue(adapter.matches_scope(self.kihara, self.kenya))
		self.assertTrue(adapter.matches_scope(self.kenya, self.kihara, allow_ancestor=True))
		self.assertFalse(adapter.matches_scope(self.kenya, self.kihara, allow_ancestor=False))

	def test_matches_scope_unrelated_branch(self):
		self.assertFalse(adapter.matches_scope(self.kihara, self.coast))
		self.assertFalse(adapter.matches_scope(self.kihara, self.mombasa))
		self.assertFalse(adapter.matches_scope(self.mombasa, self.central))

	def test_resolve_upward_skips_intermediate_levels(self):
		"""From a Ward, the nearest County is Kiambu — Sub County is skipped."""
		county = self.levels[2]

		match = adapter.resolve_upward(
			self.kihara,
			lambda node: frappe.db.get_value("Geo Node", node, "geo_level") == county,
		)

		self.assertEqual(match, self.kiambu)

	def test_resolve_upward_reaches_the_root(self):
		country = self.levels[0]

		match = adapter.resolve_upward(
			self.kihara,
			lambda node: frappe.db.get_value("Geo Node", node, "geo_level") == country,
		)

		self.assertEqual(match, self.kenya)

	def test_resolve_upward_returns_none_from_the_deepest_node(self):
		self.assertIsNone(adapter.resolve_upward(self.kihara, lambda node: False))


class TestAncestorOrderFollowsTheTree(IntegrationTestCase):
	"""Nearest-first is depth, not level order — proved where the two disagree.

	Every hierarchy above is well-formed, so ordering by tree position and
	ordering by `geo_level_order` give the same answer and neither can be told
	apart from the other. This class builds the one shape that separates them::

	    Root   (level order 1)
	    └── Mid    (level order 3)
	        └── Inner  (level order 2)
	            └── Leaf   (level order 4)

	Inner is Leaf's nearest ancestor by any honest reading of the tree, but it
	carries a shallower level than Mid above it. Ordering by the level ladder
	puts Mid first, and everything that walks upward — approver routing most of
	all — then reaches the wrong node first.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.chain = fixtures.build_misnested_chain(fixtures.MISNESTED_PREFIX)

	def test_the_fixture_really_is_nested_out_of_level_order(self):
		"""Without this, every test below could pass on a well-formed tree.

		Read from the parent links and Geo Level rather than through the adapter:
		a guard that asked the adapter would depend on the ordering it is meant to
		be guarding, and would go quiet at exactly the wrong moment.
		"""
		orders = [self._level_order(self.chain[key]) for key in ("root", "mid", "inner", "leaf")]

		self.assertEqual(orders, [1, 3, 2, 4])
		self.assertGreater(
			self._level_order(self.chain["mid"]),
			self._level_order(self.chain["inner"]),
			"Mid must sit at a deeper level than the node below it",
		)

	@staticmethod
	def _level_order(node: str) -> int:
		level = frappe.db.get_value("Geo Node", node, "geo_level")

		return frappe.db.get_value("Geo Level", level, "geo_level_order")

	def test_ancestors_are_nearest_first_by_depth(self):
		ancestors = adapter.get_ancestors(self.chain["leaf"])

		self.assertEqual(
			[a.name for a in ancestors],
			[self.chain["inner"], self.chain["mid"], self.chain["root"]],
		)

	def test_the_immediate_parent_comes_first(self):
		ancestors = adapter.get_ancestors(self.chain["leaf"])

		self.assertEqual(ancestors[0].name, self.chain["inner"])
		self.assertEqual(
			ancestors[0].name,
			frappe.db.get_value("Geo Node", self.chain["leaf"], "parent_geo_node"),
		)

	def test_resolve_upward_visits_the_chain_nearest_first(self):
		visited = []

		def never(node):
			visited.append(node)

			return False

		adapter.resolve_upward(self.chain["leaf"], never)

		self.assertEqual(
			visited,
			[self.chain["leaf"], self.chain["inner"], self.chain["mid"], self.chain["root"]],
		)

	def test_resolve_upward_stops_at_the_nearest_match(self):
		"""Both Inner and Mid match; the nearer one must win."""
		match = adapter.resolve_upward(
			self.chain["leaf"], lambda node: node in (self.chain["mid"], self.chain["inner"])
		)

		self.assertEqual(match, self.chain["inner"])

	def test_get_full_path_reads_from_the_node_outward(self):
		self.assertEqual(adapter.get_full_path(self.chain["leaf"]), "Leaf — Inner — Mid — Root")
