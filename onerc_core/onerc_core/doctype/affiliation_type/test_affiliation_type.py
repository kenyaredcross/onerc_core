# Copyright (c) 2026, Kelvin Njenga and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.identity.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class IntegrationTestAffiliationType(IntegrationTestCase):
	"""Integration tests for AffiliationType."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

	def _make(self, key, **kwargs):
		name = fixtures.make_affiliation_type(key, **kwargs)
		self.addCleanup(frappe.delete_doc, "Affiliation Type", name, force=True)

		return name

	def test_key_is_the_docname(self):
		affiliation_type = self._make("volunteer", label="Volunteer")

		self.assertEqual(affiliation_type, f"{fixtures.TEST_PREFIX}-volunteer")

	def test_is_active_defaults_to_enabled(self):
		self.assertEqual(frappe.new_doc("Affiliation Type").is_active, 1)

	def test_a_gated_type_must_name_a_capability(self):
		"""A gate with no key would fail closed forever. Refuse it instead."""
		with self.assertRaises(frappe.MandatoryError):
			self._make("beneficiary", label="Beneficiary", requires_gated_read=True)

	def test_a_gated_type_keeps_its_capability(self):
		affiliation_type = self._make(
			"beneficiary",
			label="Beneficiary",
			requires_gated_read=True,
			gating_capability="view_beneficiary_affiliations",
		)

		self.assertEqual(
			frappe.db.get_value("Affiliation Type", affiliation_type, "gating_capability"),
			"view_beneficiary_affiliations",
		)

	def test_an_ungated_type_does_not_keep_a_capability(self):
		"""A leftover capability would read as though a gate were still in force."""
		affiliation_type = self._make("donor", label="Donor", gating_capability="view_something_sensitive")

		self.assertFalse(frappe.db.get_value("Affiliation Type", affiliation_type, "gating_capability"))

	def test_dropping_the_gate_clears_the_capability(self):
		affiliation_type = self._make(
			"beneficiary",
			label="Beneficiary",
			requires_gated_read=True,
			gating_capability="view_beneficiary_affiliations",
		)

		doc = frappe.get_doc("Affiliation Type", affiliation_type)
		doc.requires_gated_read = 0
		doc.save()

		self.assertFalse(doc.gating_capability)

	def test_the_key_is_required(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Affiliation Type", "affiliation_type_name": "Keyless"}).insert()
