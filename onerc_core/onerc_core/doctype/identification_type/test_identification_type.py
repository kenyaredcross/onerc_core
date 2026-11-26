# Copyright (c) 2026, Kelvin Njenga and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.identity.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []

# The set hooks.py seeds. A society may edit or deactivate any of them, so the
# tests below check that the vocabulary arrived, never that it stayed this way.
SEEDED_KEYS = ("national_id", "passport", "alien_id", "driving_licence")


class IntegrationTestIdentificationType(IntegrationTestCase):
	"""Integration tests for IdentificationType."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

	def _make(self, key, **kwargs):
		name = fixtures.make_identification_type(key, **kwargs)
		self.addCleanup(frappe.delete_doc, "Identification Type", name, force=True)

		return name

	def test_key_is_the_docname(self):
		"""Keyed by data, like Affiliation Type and Geo Level and for one reason.

		Imports and society configuration name these keys. A hash would make
		every reference to "the passport type" unreadable and unstable.
		"""
		identification_type = self._make("passport", label="Passport")

		self.assertEqual(identification_type, f"{fixtures.TEST_PREFIX}-passport")

	def test_naming_is_declared_on_the_doctype(self):
		self.assertEqual(frappe.get_meta("Identification Type").autoname, "field:identification_type_key")

	def test_key_is_unique(self):
		"""Either constraint may report first: the docname, or the unique index."""
		self._make("duplicate")

		with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
			self._make("duplicate")

	def test_is_active_defaults_to_enabled(self):
		self.assertEqual(frappe.new_doc("Identification Type").is_active, 1)

	def test_name_is_trimmed(self):
		identification_type = self._make("spaced", label="  Alien ID  ")

		self.assertEqual(
			frappe.db.get_value("Identification Type", identification_type, "identification_type_name"),
			"Alien ID",
		)

	def test_the_society_may_add_its_own(self):
		"""The seeded set is a starting point, not a closed list."""
		identification_type = self._make("refugee_card", label="Refugee Card")

		self.assertTrue(frappe.db.exists("Identification Type", identification_type))

	def test_the_seeded_vocabulary_is_installed(self):
		"""hooks.py ships these as fixtures, so a fresh site can record a document."""
		for key in SEEDED_KEYS:
			self.assertTrue(frappe.db.exists("Identification Type", key), f"{key} was not seeded")

	def test_everyone_may_read_the_vocabulary(self):
		"""It is a list of document names. Without read access nobody could pick one."""
		roles = {row.role for row in frappe.get_meta("Identification Type").permissions if row.read}

		self.assertIn("All", roles)
