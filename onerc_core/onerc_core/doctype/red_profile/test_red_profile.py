# Copyright (c) 2026, Kelvin Njenga and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.identity.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []

# Frappe generates test records for every doctype a Link reaches, transitively.
# `user` reaches User, which reaches Email Account, which reaches Company, which
# on a site with ERPNext installed drags in a Fiscal Year colliding with the real
# one, and the whole class errors before a single test runs. None of that is
# under test here: the tests that need a login use Administrator, which is
# always present.
IGNORE_TEST_RECORD_DEPENDENCIES = ["User"]

# Person-facts: true whatever roles this person holds, and every one optional.
PERSONAL_FIELDS = (
	"gender",
	"date_of_birth",
	"marital_status",
	"nationality",
	"citizenship_status",
	"preferred_language",
	"profile_photo",
)


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

	# Personal identity — person-facts, true whatever roles someone holds.

	def test_registration_needs_none_of_the_personal_fields(self):
		"""Thin registration: a name and an email are the whole of it."""
		profile = self._make(email="thin.registration@example.test")

		doc = frappe.get_doc("Red Profile", profile)

		for fieldname in PERSONAL_FIELDS:
			self.assertFalse(doc.get(fieldname), f"{fieldname} was filled in without being asked for")

		self.assertEqual(doc.identifications, [])

	def test_no_personal_field_is_required(self):
		"""Completeness is the affiliation processes' question, not the spine's."""
		meta = frappe.get_meta("Red Profile")

		for fieldname in (*PERSONAL_FIELDS, "identifications"):
			field = meta.get_field(fieldname)

			self.assertIsNotNone(field, f"{fieldname} is missing")
			self.assertFalse(field.reqd, f"{fieldname} is required")
			self.assertFalse(field.mandatory_depends_on, f"{fieldname} is conditionally required")

	def test_every_personal_field_can_be_set(self):
		id_type = self._make_identification_type("national_id", label="National ID")
		profile = self._make(
			email="complete.profile@example.test",
			gender="Female",
			date_of_birth="1994-03-17",
			marital_status="Married",
			nationality="Kenya",
			citizenship_status="Citizen",
			preferred_language="en",
			profile_photo="/files/portrait.png",
			identifications=[{"id_type": id_type, "id_number": "12345678", "is_primary": 1}],
		)

		doc = frappe.get_doc("Red Profile", profile)

		self.assertEqual(doc.gender, "Female")
		self.assertEqual(str(doc.date_of_birth), "1994-03-17")
		self.assertEqual(doc.marital_status, "Married")
		self.assertEqual(doc.nationality, "Kenya")
		self.assertEqual(doc.citizenship_status, "Citizen")
		self.assertEqual(doc.preferred_language, "en")
		self.assertEqual(doc.profile_photo, "/files/portrait.png")
		self.assertEqual(len(doc.identifications), 1)

	def test_gender_is_a_link_to_the_configurable_vocabulary(self):
		"""A Link, never a Select. What genders a society records is its own answer."""
		self.assertEqual(frappe.get_meta("Red Profile").get_field("gender").fieldtype, "Link")
		self.assertEqual(frappe.get_meta("Red Profile").get_field("gender").options, "Gender")
		self.assertEqual(frappe.get_meta("Gender").autoname, "field:gender")

	def test_gender_accepts_a_society_added_option(self):
		"""The vocabulary is editable, so a value nobody hardcoded must resolve."""
		gender = frappe.get_doc({"doctype": "Gender", "gender": f"{fixtures.TEST_PREFIX} Gender"}).insert()
		self.addCleanup(frappe.delete_doc, "Gender", gender.name, force=True)

		profile = self._make(email="own.gender@example.test", gender=gender.name)

		self.assertEqual(frappe.db.get_value("Red Profile", profile, "gender"), gender.name)

	def test_an_unknown_gender_is_refused(self):
		"""A Link, so the vocabulary is enforced rather than suggested."""
		with self.assertRaises(frappe.LinkValidationError):
			self._make(email="unknown.gender@example.test", gender="Not A Configured Gender")

	def test_nationality_links_to_country(self):
		self.assertEqual(frappe.get_meta("Red Profile").get_field("nationality").options, "Country")

	def test_there_is_no_second_country_field(self):
		"""One question, asked once. The old duplication is deliberately dropped."""
		meta = frappe.get_meta("Red Profile")

		for fieldname in ("country_of_citizenship", "country", "citizenship_country"):
			self.assertIsNone(meta.get_field(fieldname), f"{fieldname} duplicates nationality")

	def test_preferred_language_is_a_link(self):
		field = frappe.get_meta("Red Profile").get_field("preferred_language")

		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Language")

	def test_citizenship_status_options(self):
		"""Near-universal categories, and blank, because the field is optional."""
		options = frappe.get_meta("Red Profile").get_field("citizenship_status").options.split("\n")

		self.assertEqual(options, ["", "Citizen", "Non-citizen", "Refugee", "Migrant", "Other"])

	def test_marital_status_options(self):
		options = frappe.get_meta("Red Profile").get_field("marital_status").options.split("\n")

		self.assertEqual(options, ["", "Single", "Married", "Divorced", "Widowed", "Other"])

	def test_profile_photo_is_an_image(self):
		meta = frappe.get_meta("Red Profile")

		self.assertEqual(meta.get_field("profile_photo").fieldtype, "Attach Image")
		self.assertEqual(meta.image_field, "profile_photo")

	def test_full_name_ignores_the_personal_fields(self):
		"""Composition is unchanged. These fields are additive, not part of it."""
		profile = self._make(
			first_name="Asha",
			last_name="Wanjiru",
			email="composition.unchanged@example.test",
			gender="Female",
			date_of_birth="1994-03-17",
		)

		self.assertEqual(frappe.db.get_value("Red Profile", profile, "full_name"), "Asha Wanjiru")

	# Identification — a table, because a person may hold several documents.

	def test_identifications_replace_flat_document_fields(self):
		"""The flat shape could record one document and never said which."""
		meta = frappe.get_meta("Red Profile")

		for fieldname in ("passport_number", "id_number", "id_document_type", "national_id"):
			self.assertIsNone(meta.get_field(fieldname), f"{fieldname} is a flat document field")

		self.assertEqual(meta.get_field("identifications").options, "Red Profile Identification")

	def test_id_type_links_to_the_configurable_vocabulary(self):
		field = frappe.get_meta("Red Profile Identification").get_field("id_type")

		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Identification Type")

	def test_several_identifications_of_different_types(self):
		national_id = self._make_identification_type("national_id", label="National ID")
		passport = self._make_identification_type("passport", label="Passport")

		profile = self._make(
			email="two.documents@example.test",
			identifications=[
				{"id_type": national_id, "id_number": "12345678", "is_primary": 1},
				{"id_type": passport, "id_number": "AK0912345", "attachment": "/files/passport.pdf"},
			],
		)

		rows = frappe.get_doc("Red Profile", profile).identifications

		self.assertEqual([row.id_type for row in rows], [national_id, passport])
		self.assertEqual([row.id_number for row in rows], ["12345678", "AK0912345"])
		self.assertEqual(rows[1].attachment, "/files/passport.pdf")

	def test_two_documents_of_one_type_are_allowed(self):
		"""Dual nationality means two passports. The old shape could hold one."""
		passport = self._make_identification_type("passport", label="Passport")

		profile = self._make(
			email="dual.nationality@example.test",
			identifications=[
				{"id_type": passport, "id_number": "AK0912345"},
				{"id_type": passport, "id_number": "P77771234"},
			],
		)

		self.assertEqual(len(frappe.get_doc("Red Profile", profile).identifications), 2)

	def test_an_unknown_identification_type_is_refused(self):
		with self.assertRaises(frappe.LinkValidationError):
			self._make(
				email="unknown.doctype@example.test",
				identifications=[{"id_type": "Not A Configured Type", "id_number": "1"}],
			)

	def test_only_one_identification_may_be_primary(self):
		"""Whoever asks which document to quote must get one answer."""
		national_id = self._make_identification_type("national_id", label="National ID")
		passport = self._make_identification_type("passport", label="Passport")

		with self.assertRaises(frappe.ValidationError):
			self._make(
				email="two.primaries@example.test",
				identifications=[
					{"id_type": national_id, "id_number": "12345678", "is_primary": 1},
					{"id_type": passport, "id_number": "AK0912345", "is_primary": 1},
				],
			)

	def test_no_primary_is_allowed(self):
		"""Nothing is required here, marking one included."""
		passport = self._make_identification_type("passport", label="Passport")

		profile = self._make(
			email="no.primary@example.test",
			identifications=[{"id_type": passport, "id_number": "AK0912345"}],
		)

		self.assertFalse(frappe.get_doc("Red Profile", profile).identifications[0].is_primary)

	def test_id_number_is_trimmed(self):
		passport = self._make_identification_type("passport", label="Passport")

		profile = self._make(
			email="spaced.number@example.test",
			identifications=[{"id_type": passport, "id_number": "  AK0912345  "}],
		)

		self.assertEqual(frappe.get_doc("Red Profile", profile).identifications[0].id_number, "AK0912345")

	def test_identifications_are_editable(self):
		"""Unlike affiliations, these are typed in. No service owns them."""
		self.assertFalse(frappe.get_meta("Red Profile").get_field("identifications").read_only)

	def test_the_sensitive_set_is_not_here(self):
		"""Blood group, medical notes and next of kin arrive later, gated."""
		meta = frappe.get_meta("Red Profile")

		for fieldname in ("blood_group", "medical_conditions", "next_of_kin", "disability"):
			self.assertIsNone(meta.get_field(fieldname), f"{fieldname} belongs to the gated extension")

	def _make_identification_type(self, key, **kwargs):
		name = fixtures.make_identification_type(key, **kwargs)
		self.addCleanup(frappe.delete_doc, "Identification Type", name, force=True)

		return name
