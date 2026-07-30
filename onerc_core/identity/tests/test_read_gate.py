# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.identity.services import affiliation, read_gate
from onerc_core.identity.services.read_gate import CAPABILITY_RESOLVER_HOOK
from onerc_core.identity.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []

GATING_CAPABILITY = "view_beneficiary_affiliations"


class TestReadGate(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.reset()

		cls.volunteer_type = fixtures.make_affiliation_type("volunteer", "Volunteer")
		cls.beneficiary_type = fixtures.make_affiliation_type(
			"beneficiary",
			"Beneficiary",
			requires_gated_read=True,
			gating_capability=GATING_CAPABILITY,
		)

	def setUp(self):
		self.profile = fixtures.make_profile()
		self.volunteer_satellite = fixtures.make_satellite()
		self.beneficiary_satellite = fixtures.make_satellite("Beneficiary record")

		self._seed(self.volunteer_type, self.volunteer_satellite)
		self._seed(self.beneficiary_type, self.beneficiary_satellite)

	def _seed(self, affiliation_type, satellite):
		affiliation.set_affiliation(
			profile=self.profile,
			affiliation_type=affiliation_type,
			status="Active",
			reference_doctype=fixtures.SATELLITE_DOCTYPE,
			reference_name=satellite,
		)

	def _visible_types(self):
		return {row["affiliation_type"] for row in read_gate.visible_affiliations(self.profile)}

	def test_both_rows_are_stored(self):
		"""The gate is a read concern. Storage is unaffected."""
		self.assertEqual(len(frappe.get_doc("Red Profile", self.profile).affiliations), 2)

	def test_ungated_rows_are_always_visible(self):
		self.assertIn(self.volunteer_type, self._visible_types())

	def test_gated_rows_are_hidden_when_no_resolver_is_installed(self):
		"""Fail closed. Nothing implements capabilities, so nothing can be granted."""
		with self.patch_hooks({CAPABILITY_RESOLVER_HOOK: []}):
			visible = self._visible_types()

		self.assertNotIn(self.beneficiary_type, visible)
		self.assertIn(self.volunteer_type, visible)

	def test_administrator_is_not_an_exception(self):
		"""No role or account is special-cased — the capability is the only key."""
		self.assertEqual(frappe.session.user, "Administrator")

		with self.patch_hooks({CAPABILITY_RESOLVER_HOOK: []}):
			self.assertNotIn(self.beneficiary_type, self._visible_types())

	def test_gated_rows_are_visible_when_the_resolver_grants(self):
		with self.patch_hooks({CAPABILITY_RESOLVER_HOOK: [fixtures.RESOLVER_GRANT]}):
			self.assertIn(self.beneficiary_type, self._visible_types())

	def test_gated_rows_are_hidden_when_the_resolver_denies(self):
		with self.patch_hooks({CAPABILITY_RESOLVER_HOOK: [fixtures.RESOLVER_DENY]}):
			visible = self._visible_types()

		self.assertNotIn(self.beneficiary_type, visible)
		self.assertIn(self.volunteer_type, visible)

	def test_two_resolvers_are_rejected(self):
		"""Install order must not decide who sees beneficiary rows."""
		hooks = {CAPABILITY_RESOLVER_HOOK: [fixtures.RESOLVER_GRANT, fixtures.RESOLVER_DENY]}

		with self.patch_hooks(hooks), self.assertRaises(frappe.ValidationError):
			self._visible_types()

	def test_onload_strips_gated_rows(self):
		"""The desk read path goes through the service, server-side."""
		doc = frappe.get_doc("Red Profile", self.profile)

		with self.patch_hooks({CAPABILITY_RESOLVER_HOOK: [fixtures.RESOLVER_DENY]}):
			doc.run_method("onload")

		self.assertEqual([row.affiliation_type for row in doc.affiliations], [self.volunteer_type])

	def test_onload_keeps_gated_rows_when_granted(self):
		doc = frappe.get_doc("Red Profile", self.profile)

		with self.patch_hooks({CAPABILITY_RESOLVER_HOOK: [fixtures.RESOLVER_GRANT]}):
			doc.run_method("onload")

		self.assertEqual(len(doc.affiliations), 2)

	def test_saving_a_stripped_document_does_not_delete_the_hidden_row(self):
		"""The dangerous path: a gated reader edits an unrelated field.

		Their form never held the beneficiary row, so posting the document back
		would delete it — if the affiliations table were writable this way. It
		is not: the persisted rows are restored on save.
		"""
		doc = frappe.get_doc("Red Profile", self.profile)

		with self.patch_hooks({CAPABILITY_RESOLVER_HOOK: [fixtures.RESOLVER_DENY]}):
			doc.run_method("onload")
			doc.phone = "0711111111"
			doc.save()

		reloaded = frappe.get_doc("Red Profile", self.profile)
		self.assertEqual(reloaded.phone, "0711111111")
		self.assertEqual(
			{row.affiliation_type for row in reloaded.affiliations},
			{self.volunteer_type, self.beneficiary_type},
		)

	def test_visible_affiliations_accepts_a_loaded_document(self):
		doc = frappe.get_doc("Red Profile", self.profile)

		with self.patch_hooks({CAPABILITY_RESOLVER_HOOK: [fixtures.RESOLVER_GRANT]}):
			rows = read_gate.visible_affiliations(doc)

		self.assertEqual(len(rows), 2)

	def test_gated_capabilities_lists_only_gated_types(self):
		gated = read_gate.gated_capabilities()

		self.assertEqual(gated.get(self.beneficiary_type), GATING_CAPABILITY)
		self.assertNotIn(self.volunteer_type, gated)
