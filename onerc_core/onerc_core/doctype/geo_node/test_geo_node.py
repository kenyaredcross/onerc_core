# Copyright (c) 2026, Kelvin Njenga and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

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
