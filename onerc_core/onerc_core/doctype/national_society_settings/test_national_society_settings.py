# Copyright (c) 2026, Kelvin Njenga and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.onerc_core.doctype.national_society_settings.national_society_settings import (
	NationalSocietySettings,
)
from onerc_core.society.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []

# vmmsx's vmms_volunteer_employee_company Custom Field puts a direct Link to
# Company on this Single, and Company's ERPNext test record needs a Fiscal Year
# that collides with the site's real one. Nothing here reads that field.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Company"]

SETTINGS_DOCTYPE = fixtures.SETTINGS_DOCTYPE


class TestBrandingIsOptional(IntegrationTestCase):
	"""A society must be configurable before it has a picture to upload.

	The logo was a mandatory Attach Image, which put an image upload in front of
	everything else on the form: nobody could set the currency, the phone rules
	or the terminology on a fresh site until somebody found a logo file. That is
	backwards — branding is the part that can wait, and blank simply means
	not-yet-configured.
	"""

	def setUp(self):
		fixtures.reset()

	def test_the_logo_is_not_mandatory(self):
		self.assertFalse(frappe.get_meta(SETTINGS_DOCTYPE).get_field("logo").reqd)

	def test_no_branding_image_is_mandatory(self):
		"""The rule, not the one field — a new image must not reintroduce this."""
		images = [
			field
			for field in frappe.get_meta(SETTINGS_DOCTYPE).fields
			if field.fieldtype in ("Attach", "Attach Image")
		]

		self.assertTrue(images, "the doctype should still have branding image fields")
		self.assertEqual([field.fieldname for field in images if field.reqd], [])

	def test_the_settings_save_with_no_logo(self):
		doc = fixtures.configure(logo=None)

		self.assertFalse(doc.logo)
		self.assertTrue(frappe.db.get_single_value(SETTINGS_DOCTYPE, "organization_name"))

	def test_configuration_is_reachable_without_one(self):
		"""What the mandatory logo actually blocked: the rest of the form."""
		doc = fixtures.configure(
			logo=None,
			currency="XOF",
			phone_number_pattern=r"^\+225\d{10}$",
			terminology=[{"term_key": "volunteer", "singular": "Volontaire"}],
		)

		self.assertFalse(doc.logo)
		self.assertEqual(doc.currency, "XOF")
		self.assertEqual(doc.phone_number_pattern, r"^\+225\d{10}$")
		self.assertEqual(doc.terminology[0].singular, "Volontaire")

	def test_a_partly_populated_record_still_saves(self):
		"""The upgrade path: a record configured before this change must resave."""
		fixtures.configure()

		doc = frappe.get_doc(SETTINGS_DOCTYPE)
		doc.telephone = "+254 20 3950000"
		doc.save()

		self.assertEqual(doc.logo, fixtures.BASELINE["logo"])
		self.assertEqual(doc.telephone, "+254 20 3950000")

	def test_an_existing_logo_can_be_cleared(self):
		fixtures.configure()

		doc = frappe.get_doc(SETTINGS_DOCTYPE)
		doc.logo = None
		doc.save()

		self.assertFalse(frappe.db.get_single_value(SETTINGS_DOCTYPE, "logo"))

	def test_nothing_new_became_mandatory(self):
		"""The set of required fields is exactly the four identity fields."""
		required = {field.fieldname for field in frappe.get_meta(SETTINGS_DOCTYPE).fields if field.reqd}

		self.assertEqual(
			required, {"organization_name", "organization_short_name", "country", "primary_language"}
		)


class TestTimeZoneValidation(IntegrationTestCase):
	"""The zone is checked against IANA; the message's example is this site's."""

	def setUp(self):
		fixtures.reset()

	def _set_system_time_zone(self, value):
		frappe.db.set_single_value("System Settings", "time_zone", value)
		frappe.clear_document_cache("System Settings")

	def test_a_valid_zone_is_accepted(self):
		self.assertEqual(fixtures.configure(time_zone="Europe/Lisbon").time_zone, "Europe/Lisbon")

	def test_an_unknown_zone_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			fixtures.configure(time_zone="Mars/Olympus Mons")

	def test_the_example_is_the_site_s_own_zone(self):
		"""A worked example naming somebody else's country reads as an instruction.

		Hardcoding one meant every society that installed this was shown a Kenyan
		string. The site's configured zone is the one example always relevant to
		whoever is reading it.
		"""
		self._set_system_time_zone("Europe/Lisbon")

		with self.assertRaises(frappe.ValidationError) as raised:
			fixtures.configure(time_zone="Mars/Olympus Mons")

		self.assertIn("Europe/Lisbon", str(raised.exception))

	def test_the_example_falls_back_to_a_neutral_shape(self):
		"""System Settings can be blank on a site nobody has finished setting up."""
		self._set_system_time_zone(None)

		self.assertEqual(NationalSocietySettings.time_zone_example(), "Region/City")

		with self.assertRaises(frappe.ValidationError) as raised:
			fixtures.configure(time_zone="Mars/Olympus Mons")

		self.assertIn("Region/City", str(raised.exception))

	def test_no_country_is_named_in_the_message(self):
		"""Regression: the example comes from configuration, never from a literal."""
		self._set_system_time_zone("Europe/Lisbon")

		with self.assertRaises(frappe.ValidationError) as raised:
			fixtures.configure(time_zone="Mars/Olympus Mons")

		self.assertNotIn("Africa/Nairobi", str(raised.exception))

	def test_a_blank_zone_is_left_alone(self):
		"""Unset is a legitimate state — the locale then falls back to the site."""
		self.assertEqual(fixtures.configure(time_zone=None).time_zone, "")
