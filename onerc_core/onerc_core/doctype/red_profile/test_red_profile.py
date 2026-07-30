# Copyright (c) 2026, Kelvin Njenga and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.identity.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class IntegrationTestRedProfile(IntegrationTestCase):
	"""Integration tests for RedProfile."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

	def _make(self, **kwargs):
		name = fixtures.make_profile(**kwargs)
		self.addCleanup(frappe.delete_doc, "Red Profile", name, force=True)

		return name

	def test_docname_is_opaque(self):
		profile = self._make(email="opaque.name@example.test")

		self.assertTrue(profile.startswith("RP-"))
		self.assertNotIn("opaque", profile)

	def test_email_is_lowercased_and_trimmed(self):
		profile = self._make(email="  MiXeD.Case@Example.Test  ")

		self.assertEqual(frappe.db.get_value("Red Profile", profile, "email"), "mixed.case@example.test")

	def test_email_is_unique(self):
		self._make(email="duplicate@example.test")

		with self.assertRaises(frappe.UniqueValidationError):
			self._make(email="duplicate@example.test")

	def test_email_uniqueness_is_case_insensitive(self):
		"""Normalisation is what makes the unique index mean what it looks like."""
		self._make(email="casing@example.test")

		with self.assertRaises(frappe.UniqueValidationError):
			self._make(email="CASING@example.test")

	def test_email_is_required(self):
		with self.assertRaises(frappe.MandatoryError):
			frappe.get_doc({"doctype": "Red Profile", "first_name": "No", "last_name": "Email"}).insert()

	def test_full_name_is_composed(self):
		profile = self._make(first_name="Asha", last_name="Wanjiru", email="asha.w@example.test")

		self.assertEqual(frappe.db.get_value("Red Profile", profile, "full_name"), "Asha Wanjiru")

	def test_full_name_includes_a_middle_name(self):
		profile = self._make(
			first_name="Asha", middle_name="Njeri", last_name="Wanjiru", email="asha.n.w@example.test"
		)

		self.assertEqual(frappe.db.get_value("Red Profile", profile, "full_name"), "Asha Njeri Wanjiru")

	def test_full_name_is_read_only(self):
		"""Composed for display. Satellites fetch it; nothing branches on it."""
		self.assertTrue(frappe.get_meta("Red Profile").get_field("full_name").read_only)

	def test_full_name_recomposes_on_rename(self):
		profile = self._make(first_name="Asha", last_name="Wanjiru", email="renamed@example.test")

		doc = frappe.get_doc("Red Profile", profile)
		doc.last_name = "Kamau"
		doc.save()

		self.assertEqual(doc.full_name, "Asha Kamau")

	def test_user_is_optional(self):
		"""Not everyone with a profile can log in."""
		profile = self._make(email="no.user@example.test")

		self.assertFalse(frappe.db.get_value("Red Profile", profile, "user"))

	def test_several_profiles_may_have_no_user(self):
		"""`user` is unique *and* nullable — empty must not collide with empty."""
		self._make(email="first.userless@example.test")
		self._make(email="second.userless@example.test")

		self.assertEqual(frappe.db.count("Red Profile", {"email": ("like", "%userless@example.test")}), 2)

	def test_user_is_unique_when_set(self):
		self._make(email="linked.one@example.test", user="Administrator")

		with self.assertRaises(frappe.UniqueValidationError):
			self._make(email="linked.two@example.test", user="Administrator")

	def test_home_geo_node_is_the_geo_field(self):
		"""`home_geo_node`, never `region` — the name `Region` is taken."""
		meta = frappe.get_meta("Red Profile")

		self.assertEqual(meta.get_field("home_geo_node").options, "Geo Node")
		self.assertIsNone(meta.get_field("region"))

	def test_carries_no_domain_data(self):
		"""The spine stays thin. Domain data belongs in satellites."""
		meta = frappe.get_meta("Red Profile")

		for fieldname in ("skills", "fee", "blood_group", "availability", "training"):
			self.assertIsNone(meta.get_field(fieldname), f"{fieldname} is domain data")

	def test_affiliations_table_is_read_only(self):
		self.assertTrue(frappe.get_meta("Red Profile").get_field("affiliations").read_only)

	def test_doctype_carries_no_autoname_expression(self):
		"""The controller is the single source of truth for naming."""
		self.assertFalse(frappe.get_meta("Red Profile").autoname)
