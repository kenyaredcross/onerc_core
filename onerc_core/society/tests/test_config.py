# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.society.services import config
from onerc_core.society.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []


class TestGetUiConfig(IntegrationTestCase):
	def setUp(self):
		fixtures.reset()

	def test_payload_sections(self):
		payload = config.get_ui_config()

		self.assertEqual(
			set(payload),
			{"society", "theme", "locale", "terminology", "features", "validation", "social_media"},
		)

	def test_society_block(self):
		payload = config.get_ui_config()

		self.assertEqual(payload["society"]["name"], fixtures.MANDATORY["organization_name"])
		self.assertEqual(payload["society"]["short_name"], "TNS")
		self.assertEqual(payload["society"]["country"], "Kenya")

	def test_dark_logo_falls_back_to_the_main_logo(self):
		payload = config.get_ui_config()

		self.assertEqual(payload["society"]["logo_dark"], fixtures.MANDATORY["logo"])

	def test_dark_logo_is_used_when_set(self):
		fixtures.configure(logo_dark="/files/dark.png")

		self.assertEqual(config.get_ui_config()["society"]["logo_dark"], "/files/dark.png")

	def test_unset_theme_tokens_are_omitted(self):
		"""A blank token must not arrive as None and blank a UI's own default."""
		payload = config.get_ui_config()

		self.assertNotIn("surface_color", payload["theme"])
		self.assertNotIn(None, payload["theme"].values())

	def test_set_theme_tokens_are_returned(self):
		fixtures.configure(
			primary_color="#d7192d", surface_color="#ffffff", border_radius="8px", font_family="Inter"
		)

		theme = config.get_ui_config()["theme"]

		self.assertEqual(theme["primary_color"], "#d7192d")
		self.assertEqual(theme["surface_color"], "#ffffff")
		self.assertEqual(theme["border_radius"], "8px")
		self.assertEqual(theme["font_family"], "Inter")

	def test_locale_falls_back_to_system_settings(self):
		"""Society settings must not become a second source of truth for format."""
		system = frappe.get_cached_doc("System Settings")

		locale = config.get_ui_config()["locale"]

		self.assertEqual(locale["time_zone"], system.time_zone)
		self.assertEqual(locale["date_format"], system.date_format)
		self.assertEqual(locale["first_day_of_week"], system.first_day_of_the_week)

	def test_locale_prefers_the_society_value(self):
		fixtures.configure(time_zone="Africa/Nairobi", date_format="dd-mm-yyyy", currency="KES")

		locale = config.get_ui_config()["locale"]

		self.assertEqual(locale["time_zone"], "Africa/Nairobi")
		self.assertEqual(locale["date_format"], "dd-mm-yyyy")
		self.assertEqual(locale["currency"], "KES")

	def test_number_format_comes_only_from_system_settings(self):
		system = frappe.get_cached_doc("System Settings")

		self.assertEqual(config.get_ui_config()["locale"]["number_format"], system.number_format)

	def test_is_whitelisted_but_not_for_guests(self):
		"""A product UI calls this over the API — a logged-in one.

		Toggles and validation policy describe internal behaviour, so the guest
		door stays shut until there is a portal that needs a branding subset.
		"""
		self.assertIn(config.get_ui_config, frappe.whitelisted)
		self.assertNotIn(config.get_ui_config, frappe.guest_methods)


class TestTerminology(IntegrationTestCase):
	def setUp(self):
		fixtures.reset()

	def test_an_unconfigured_term_returns_the_key(self):
		"""Never an empty label — an unconfigured term should be obvious on screen."""
		self.assertEqual(config.term("volunteer"), "volunteer")

	def test_an_override_is_returned(self):
		fixtures.configure(
			terminology=[{"term_key": "volunteer", "singular": "Member Volunteer", "plural": "Volunteers"}]
		)

		self.assertEqual(config.term("volunteer"), "Member Volunteer")
		self.assertEqual(config.term("volunteer", plural=True), "Volunteers")

	def test_plural_falls_back_to_singular_plus_s(self):
		fixtures.configure(terminology=[{"term_key": "branch", "singular": "Branch"}])

		self.assertEqual(config.term("branch", plural=True), "Branchs")

	def test_keys_are_normalised_to_lower_snake_case(self):
		fixtures.configure(terminology=[{"term_key": "  Interest Area ", "singular": "Sector"}])

		self.assertEqual(config.term("interest_area"), "Sector")

	def test_a_duplicate_key_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			fixtures.configure(
				terminology=[
					{"term_key": "volunteer", "singular": "Volunteer"},
					{"term_key": "Volunteer", "singular": "Helper"},
				]
			)


class TestFeatureToggles(IntegrationTestCase):
	def setUp(self):
		fixtures.reset()

	def test_an_absent_key_uses_the_callers_default(self):
		"""Absent is not off — core does not define features and cannot decide."""
		self.assertFalse(config.is_feature_enabled("unknown_feature"))
		self.assertTrue(config.is_feature_enabled("unknown_feature", default=True))

	def test_an_enabled_toggle_is_reported(self):
		fixtures.configure(feature_toggles=[{"feature_key": "self_service", "is_enabled": 1}])

		self.assertTrue(config.is_feature_enabled("self_service"))

	def test_a_disabled_toggle_beats_the_callers_default(self):
		fixtures.configure(feature_toggles=[{"feature_key": "self_service", "is_enabled": 0}])

		self.assertFalse(config.is_feature_enabled("self_service", default=True))

	def test_keys_are_normalised(self):
		fixtures.configure(feature_toggles=[{"feature_key": "Self Service", "is_enabled": 1}])

		self.assertTrue(config.is_feature_enabled("self_service"))

	def test_a_duplicate_key_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			fixtures.configure(
				feature_toggles=[
					{"feature_key": "self_service", "is_enabled": 1},
					{"feature_key": "self-service", "is_enabled": 0},
				]
			)


class TestValidationPolicy(IntegrationTestCase):
	def setUp(self):
		fixtures.reset()

	def test_no_pattern_means_no_check(self):
		"""A society that has not declared a numbering plan gets no invented one."""
		fixtures.configure(phone_number_pattern=None)

		config.validate_phone_number("anything at all")

	def test_a_matching_number_passes(self):
		fixtures.configure(phone_number_pattern=r"^(\+254|0)[17]\d{8}$")

		config.validate_phone_number("+254712345678")
		config.validate_phone_number("0712345678")

	def test_a_non_matching_number_is_rejected(self):
		fixtures.configure(phone_number_pattern=r"^(\+254|0)[17]\d{8}$", phone_number_example="+254712345678")

		with self.assertRaises(frappe.ValidationError):
			config.validate_phone_number("12345")

	def test_the_example_is_quoted_back_to_the_user(self):
		fixtures.configure(phone_number_pattern=r"^(\+254|0)[17]\d{8}$", phone_number_example="+254712345678")

		with self.assertRaises(frappe.ValidationError) as raised:
			config.validate_phone_number("12345")

		self.assertIn("+254712345678", str(raised.exception))

	def test_a_pattern_must_match_the_whole_number(self):
		"""Anchored by fullmatch, so a pattern cannot accidentally pass a prefix."""
		fixtures.configure(phone_number_pattern=r"\d{4}")

		with self.assertRaises(frappe.ValidationError):
			config.validate_phone_number("1234567")

	def test_an_uncompilable_pattern_is_rejected_at_configuration_time(self):
		"""Fail once, here — not on every profile save."""
		with self.assertRaises(frappe.ValidationError):
			fixtures.configure(phone_number_pattern="^(unclosed")

	def test_an_unknown_time_zone_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			fixtures.configure(time_zone="Mars/Olympus_Mons")

	def test_a_known_time_zone_is_accepted(self):
		fixtures.configure(time_zone="Africa/Nairobi")

		self.assertEqual(config.settings().time_zone, "Africa/Nairobi")


class TestRedProfileUsesThePolicy(IntegrationTestCase):
	"""The policy is only real if something enforces it."""

	def setUp(self):
		fixtures.reset()

	def _make(self, phone):
		doc = frappe.get_doc(
			{
				"doctype": "Red Profile",
				"first_name": "Phone",
				"last_name": "Policy",
				"email": f"phone.{frappe.generate_hash(length=6)}@example.test",
				"phone": phone,
			}
		)
		doc.insert()
		self.addCleanup(frappe.delete_doc, "Red Profile", doc.name, force=True)

		return doc

	def test_a_valid_number_is_accepted(self):
		fixtures.configure(phone_number_pattern=r"^(\+254|0)[17]\d{8}$")

		self.assertEqual(self._make("0712345678").phone, "0712345678")

	def test_an_invalid_number_is_rejected(self):
		fixtures.configure(phone_number_pattern=r"^(\+254|0)[17]\d{8}$", phone_number_example="+254712345678")

		with self.assertRaises(frappe.ValidationError):
			self._make("12345")

	def test_no_policy_accepts_anything(self):
		fixtures.configure(phone_number_pattern=None)

		self.assertEqual(self._make("12345").phone, "12345")

	def test_a_blank_number_is_always_fine(self):
		"""Phone is optional. A policy governs format, not presence."""
		fixtures.configure(phone_number_pattern=r"^(\+254|0)[17]\d{8}$")

		self.assertFalse(self._make(None).phone)
