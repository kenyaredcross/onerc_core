# Copyright (c) 2026, Kelvin Njenga and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import cint

from onerc_core.geo.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class IntegrationTestGeoLevel(IntegrationTestCase):
	"""Integration tests for GeoLevel."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

	def _make_level(self, key, label, order, **kwargs):
		"""Create a level and drop it when the test ends.

		These tests assert on a global constraint (one active lowest level), so
		they must not leak rows into each other — IntegrationTestCase only rolls
		back once the whole class is done, not per test.
		"""
		name = fixtures.make_level(key, label, order, **kwargs)
		self.addCleanup(frappe.delete_doc, "Geo Level", name, force=True)

		return name

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

	def test_second_active_lowest_level_is_rejected(self):
		self._make_level("T3-1", "Region", 1)
		self._make_level("T3-3", "Ward", 3, is_lowest=True)

		with self.assertRaises(frappe.ValidationError):
			self._make_level("T3-2", "County", 2, is_lowest=True)

	def test_inactive_lowest_level_does_not_conflict(self):
		self._make_level("T3-3", "Ward", 3, is_lowest=True)

		retired = self._make_level("T3-2", "Sub Location", 2, is_lowest=True, is_active=False)

		self.assertTrue(frappe.db.exists("Geo Level", retired))

	def test_the_same_level_can_be_resaved_while_lowest(self):
		"""The uniqueness check must exclude the row being saved."""
		ward = self._make_level("T3-3", "Ward", 3, is_lowest=True)

		doc = frappe.get_doc("Geo Level", ward)
		doc.description = "Smallest administrative unit"
		doc.save()

		self.assertTrue(doc.is_lowest_level)

	def test_top_level_cannot_require_a_parent(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_level("T3-1", "Region", 1, requires_parent=True)

	def test_lower_levels_may_require_a_parent(self):
		self._make_level("T3-1", "Region", 1)

		county = self._make_level("T3-2", "County", 2)

		self.assertTrue(frappe.db.get_value("Geo Level", county, "requires_parent"))
