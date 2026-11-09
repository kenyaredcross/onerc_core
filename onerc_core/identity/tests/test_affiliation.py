# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.identity.services import affiliation
from onerc_core.identity.services.affiliation import AFFILIATION_PROVIDER_HOOK
from onerc_core.identity.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []


class TestSetAffiliation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.volunteer_type = fixtures.make_affiliation_type("volunteer", "Volunteer")
		cls.member_type = fixtures.make_affiliation_type("member", "Member")

	def setUp(self):
		self.profile = fixtures.make_profile()
		self.satellite = fixtures.make_satellite()

	def _set(self, **overrides):
		payload = {
			"profile": self.profile,
			"affiliation_type": self.volunteer_type,
			"status": "Active",
			"reference_doctype": fixtures.SATELLITE_DOCTYPE,
			"reference_name": self.satellite,
		}
		payload.update(overrides)

		return affiliation.set_affiliation(**payload)

	def test_writes_a_row(self):
		row = self._set()

		doc = frappe.get_doc("Red Profile", self.profile)
		self.assertEqual(len(doc.affiliations), 1)
		self.assertEqual(doc.affiliations[0].name, row)
		self.assertEqual(doc.affiliations[0].affiliation_type, self.volunteer_type)
		self.assertEqual(doc.affiliations[0].reference_name, self.satellite)

	def test_is_idempotent(self):
		"""A second identical call must not touch the database at all."""
		self._set()
		before = frappe.db.get_value("Red Profile", self.profile, "modified")

		self._set()

		self.assertEqual(frappe.db.get_value("Red Profile", self.profile, "modified"), before)

	def test_one_row_per_type(self):
		first = self._set(status="Pending")
		second = self._set(status="Active")

		doc = frappe.get_doc("Red Profile", self.profile)
		self.assertEqual(first, second)
		self.assertEqual(len(doc.affiliations), 1)
		self.assertEqual(doc.affiliations[0].status, "Active")

	def test_a_second_type_gets_its_own_row(self):
		self._set()
		self._set(affiliation_type=self.member_type)

		doc = frappe.get_doc("Red Profile", self.profile)
		self.assertEqual(len(doc.affiliations), 2)

	def test_status_is_read_only_on_the_row(self):
		self.assertTrue(
			frappe.get_meta("Red Profile Affiliation").get_field("status").read_only,
			"the satellite owns the status; the index only summarises it",
		)

	def test_unknown_status_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._set(status="Enthusiastic")

	def test_unknown_affiliation_type_is_rejected(self):
		with self.assertRaises(frappe.DoesNotExistError):
			self._set(affiliation_type="ID-TEST-nonexistent")

	def test_missing_satellite_record_is_rejected(self):
		with self.assertRaises(frappe.DoesNotExistError):
			self._set(reference_name="does-not-exist")

	def test_end_before_start_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._set(start_date="2026-06-01", end_date="2026-05-01")

	def test_dates_are_carried_onto_the_row(self):
		self._set(start_date="2026-01-04", end_date="2026-06-30")

		row = frappe.get_doc("Red Profile", self.profile).affiliations[0]
		self.assertEqual(str(row.start_date), "2026-01-04")
		self.assertEqual(str(row.end_date), "2026-06-30")


class TestAffiliationsAreDerived(IntegrationTestCase):
	"""The child table must refuse writes that did not come from the service."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.volunteer_type = fixtures.make_affiliation_type("volunteer", "Volunteer")

	def setUp(self):
		self.profile = fixtures.make_profile()
		self.satellite = fixtures.make_satellite()

	def test_inline_rows_on_a_new_profile_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Red Profile",
					"first_name": "Inline",
					"last_name": "Rows",
					"email": "inline.rows@example.test",
					"affiliations": [
						{
							"affiliation_type": self.volunteer_type,
							"status": "Active",
							"reference_doctype": fixtures.SATELLITE_DOCTYPE,
							"reference_name": self.satellite,
						}
					],
				}
			).insert()

	def test_a_direct_append_is_discarded(self):
		doc = frappe.get_doc("Red Profile", self.profile)
		doc.append(
			"affiliations",
			{
				"affiliation_type": self.volunteer_type,
				"status": "Active",
				"reference_doctype": fixtures.SATELLITE_DOCTYPE,
				"reference_name": self.satellite,
			},
		)
		doc.save()

		self.assertEqual(frappe.get_doc("Red Profile", self.profile).affiliations, [])

	def test_a_direct_status_edit_is_discarded(self):
		affiliation.set_affiliation(
			profile=self.profile,
			affiliation_type=self.volunteer_type,
			status="Pending",
			reference_doctype=fixtures.SATELLITE_DOCTYPE,
			reference_name=self.satellite,
		)

		doc = frappe.get_doc("Red Profile", self.profile)
		doc.affiliations[0].status = "Active"
		doc.save()

		self.assertEqual(frappe.get_doc("Red Profile", self.profile).affiliations[0].status, "Pending")

	def test_a_direct_removal_is_discarded(self):
		affiliation.set_affiliation(
			profile=self.profile,
			affiliation_type=self.volunteer_type,
			status="Active",
			reference_doctype=fixtures.SATELLITE_DOCTYPE,
			reference_name=self.satellite,
		)

		doc = frappe.get_doc("Red Profile", self.profile)
		doc.affiliations = []
		doc.save()

		self.assertEqual(len(frappe.get_doc("Red Profile", self.profile).affiliations), 1)

	def test_unrelated_edits_still_save(self):
		"""Restoring rows must not cost the rest of the document its save."""
		doc = frappe.get_doc("Red Profile", self.profile)
		doc.phone = "0700000000"
		doc.save()

		self.assertEqual(frappe.db.get_value("Red Profile", self.profile, "phone"), "0700000000")


class TestRebuildAffiliations(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.volunteer_type = fixtures.make_affiliation_type("volunteer", "Volunteer")
		cls.member_type = fixtures.make_affiliation_type("member", "Member")

	def setUp(self):
		self.profile = fixtures.make_profile()
		self.satellite = fixtures.make_satellite()

	def tearDown(self):
		fixtures.clear_staged()

	def _claim(self, **overrides):
		claim = {
			"affiliation_type": self.volunteer_type,
			"status": "Active",
			"reference_doctype": fixtures.SATELLITE_DOCTYPE,
			"reference_name": self.satellite,
		}
		claim.update(overrides)

		return claim

	def _seed_row(self, **overrides):
		return affiliation.set_affiliation(profile=self.profile, **self._claim(**overrides))

	def _rows(self):
		return frappe.get_doc("Red Profile", self.profile).affiliations

	def test_no_providers_is_a_no_op_that_keeps_existing_rows(self):
		"""The case that matters today: core installed, no satellite app yet.

		Nothing declares ownership, so nothing is eligible for removal. A
		rebuild that cannot rebuild must not delete.
		"""
		self._seed_row()

		with self.patch_hooks({AFFILIATION_PROVIDER_HOOK: []}):
			summary = affiliation.rebuild_affiliations(self.profile)

		self.assertEqual(summary["providers"], 0)
		self.assertEqual(summary["removed"], 0)
		self.assertFalse(summary["changed"])
		self.assertEqual(len(self._rows()), 1)
		self.assertEqual(summary["unclaimed"], [self.volunteer_type])

	def test_rebuilds_from_scratch_without_loss(self):
		"""Design 2's contract: drop every row, rebuild, lose nothing."""
		self._seed_row(start_date="2026-01-04")
		expected = [row.as_dict() for row in self._rows()]

		frappe.db.delete("Red Profile Affiliation", {"parent": self.profile})

		provider = fixtures.stage_provider(
			"first", [fixtures.SATELLITE_DOCTYPE], [self._claim(start_date="2026-01-04")]
		)
		with self.patch_hooks({AFFILIATION_PROVIDER_HOOK: [provider]}):
			summary = affiliation.rebuild_affiliations(self.profile)

		rebuilt = self._rows()
		self.assertEqual(summary["written"], 1)
		self.assertEqual(len(rebuilt), 1)
		for field in ("affiliation_type", "status", "reference_doctype", "reference_name", "start_date"):
			self.assertEqual(rebuilt[0].get(field), expected[0].get(field))

	def test_removes_a_row_whose_satellite_is_gone(self):
		self._seed_row()

		silent = fixtures.stage_provider("first", [fixtures.SATELLITE_DOCTYPE])
		with self.patch_hooks({AFFILIATION_PROVIDER_HOOK: [silent]}):
			summary = affiliation.rebuild_affiliations(self.profile)

		self.assertEqual(summary["removed"], 1)
		self.assertEqual(self._rows(), [])

	def test_leaves_rows_no_provider_owns(self):
		"""An uninstalled app is not a deleted satellite. Report, do not delete."""
		self._seed_row()

		other = fixtures.stage_provider("first", ["Note"])
		with self.patch_hooks({AFFILIATION_PROVIDER_HOOK: [other]}):
			summary = affiliation.rebuild_affiliations(self.profile)

		self.assertEqual(summary["removed"], 0)
		self.assertEqual(summary["unclaimed"], [self.volunteer_type])
		self.assertEqual(len(self._rows()), 1)

	def test_is_idempotent(self):
		self._seed_row()
		provider = fixtures.stage_provider("first", [fixtures.SATELLITE_DOCTYPE], [self._claim()])

		with self.patch_hooks({AFFILIATION_PROVIDER_HOOK: [provider]}):
			affiliation.rebuild_affiliations(self.profile)
			before = frappe.db.get_value("Red Profile", self.profile, "modified")
			summary = affiliation.rebuild_affiliations(self.profile)

		self.assertFalse(summary["changed"])
		self.assertEqual(frappe.db.get_value("Red Profile", self.profile, "modified"), before)

	def test_updates_a_changed_claim(self):
		self._seed_row(status="Pending")

		provider = fixtures.stage_provider(
			"first", [fixtures.SATELLITE_DOCTYPE], [self._claim(status="Ended")]
		)
		with self.patch_hooks({AFFILIATION_PROVIDER_HOOK: [provider]}):
			summary = affiliation.rebuild_affiliations(self.profile)

		self.assertEqual(summary["written"], 1)
		self.assertEqual(self._rows()[0].status, "Ended")

	def test_two_providers_claiming_one_type_is_rejected(self):
		first = fixtures.stage_provider("first", [fixtures.SATELLITE_DOCTYPE], [self._claim()])
		second = fixtures.stage_provider("second", [fixtures.SATELLITE_DOCTYPE], [self._claim()])

		with self.patch_hooks({AFFILIATION_PROVIDER_HOOK: [first, second]}):
			with self.assertRaises(frappe.ValidationError):
				affiliation.rebuild_affiliations(self.profile)

	def test_claiming_an_undeclared_doctype_is_rejected(self):
		liar = fixtures.stage_provider("first", ["Note"], [self._claim()])

		with self.patch_hooks({AFFILIATION_PROVIDER_HOOK: [liar]}):
			with self.assertRaises(frappe.ValidationError):
				affiliation.rebuild_affiliations(self.profile)

	def test_a_malformed_declaration_is_rejected(self):
		with self.patch_hooks({AFFILIATION_PROVIDER_HOOK: [fixtures.PROVIDER_PATHS["malformed"]]}):
			with self.assertRaises(frappe.ValidationError):
				affiliation.rebuild_affiliations(self.profile)

	def test_a_failing_provider_changes_nothing(self):
		"""Collect, then apply. A partial view of the satellites is not usable."""
		self._seed_row()

		silent = fixtures.stage_provider("first", [fixtures.SATELLITE_DOCTYPE])
		broken = fixtures.PROVIDER_PATHS["broken"]
		with self.patch_hooks({AFFILIATION_PROVIDER_HOOK: [silent, broken]}):
			with self.assertRaises(RuntimeError):
				affiliation.rebuild_affiliations(self.profile)

		self.assertEqual(len(self._rows()), 1, "the silent provider's removal must not have landed")

	def test_two_providers_owning_different_types_both_land(self):
		second_satellite = fixtures.make_satellite("Member record")
		volunteers = fixtures.stage_provider("first", [fixtures.SATELLITE_DOCTYPE], [self._claim()])
		members = fixtures.stage_provider(
			"second",
			[fixtures.SATELLITE_DOCTYPE],
			[self._claim(affiliation_type=self.member_type, reference_name=second_satellite)],
		)

		with self.patch_hooks({AFFILIATION_PROVIDER_HOOK: [volunteers, members]}):
			summary = affiliation.rebuild_affiliations(self.profile)

		self.assertEqual(summary["written"], 2)
		self.assertEqual(
			{row.affiliation_type for row in self._rows()}, {self.volunteer_type, self.member_type}
		)
