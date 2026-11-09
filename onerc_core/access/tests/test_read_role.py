# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""A registration's reading role widens who may open a record, never who may act.

The case: somebody responsible for a region must see every county's records in
it without becoming the officer who edits them. The registration's own role
keeps governing every act; `read_role_from_setting` adds a second role whose
area counts for reads only.

The stand-in doctype gives both test roles full DocPerms, so the *only* thing
keeping the reader from writing is this layer. A test that passed because the
DocPerm said no would prove nothing.
"""

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.access.services import enforcement, registry
from onerc_core.access.services.registry import READ_ROLE_SETTING_KEY, SCOPEABLE_DOCTYPE_HOOK
from onerc_core.access.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []

NONEXISTENT_ROLE = "ACC-TEST Reading Role That Does Not Exist"


def reading_registration() -> dict:
	return {**fixtures.registration(fixtures.APPROVER_ROLE), READ_ROLE_SETTING_KEY: fixtures.SCOPE_ROLE_SETTING}


class ReadRoleTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		fixtures.ensure_scoped_doctype()
		fixtures.ensure_setting_field()
		fixtures.reset()

		cls.tree = fixtures.build_tree()
		cls.records = {
			key: fixtures.make_record(key, cls.tree[key]) for key in ("county_a", "ward_a1", "county_b", "county_c")
		}

		# The county officer acts in County A. The regional reader holds the
		# reading role over the whole region.
		cls.officer = fixtures.make_user("read_officer", [fixtures.APPROVER_ROLE])
		cls.reader = fixtures.make_user("read_regional", [fixtures.VIEWER_ROLE])
		fixtures.make_assignment(cls.officer, fixtures.APPROVER_ROLE, cls.tree["county_a"])
		fixtures.make_assignment(cls.reader, fixtures.VIEWER_ROLE, cls.tree["region"])

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		fixtures.teardown()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(fixtures.set_scope_role_setting, None)
		fixtures.set_scope_role_setting(fixtures.VIEWER_ROLE)

	def registered(self):
		return self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [reading_registration()]})

	def listed_by(self, user: str) -> set[str]:
		frappe.set_user(user)
		names = set(frappe.get_list(fixtures.SCOPED_DOCTYPE, pluck="name", limit_page_length=0))
		frappe.set_user("Administrator")
		return names

	def may(self, user: str, key: str, ptype: str) -> bool:
		doc = frappe.get_doc(fixtures.SCOPED_DOCTYPE, self.records[key])
		return frappe.has_permission(fixtures.SCOPED_DOCTYPE, doc=doc, user=user, ptype=ptype)

	def guard_permits(self, user: str, key: str, ptype: str | None = None) -> bool:
		try:
			enforcement.guard(fixtures.SCOPED_DOCTYPE, self.records[key], user=user, ptype=ptype)
		except frappe.PermissionError:
			return False
		return True

	# --- the registration -------------------------------------------------

	def test_the_key_is_kept_and_optional(self):
		with self.registered():
			entry = registry.for_doctype(fixtures.SCOPED_DOCTYPE)

		self.assertEqual(entry[READ_ROLE_SETTING_KEY], fixtures.SCOPE_ROLE_SETTING)
		self.assertNotIn(READ_ROLE_SETTING_KEY, registry._validated(fixtures.registration()))

	# --- reading ------------------------------------------------------------

	def test_reader_lists_and_opens_every_county_in_the_region(self):
		with self.registered():
			listed = self.listed_by(self.reader)

			for key in self.records:
				with self.subTest(key=key):
					self.assertIn(self.records[key], listed)
					self.assertTrue(self.may(self.reader, key, "read"))
					self.assertTrue(self.guard_permits(self.reader, key, ptype="read"))

	# --- acting -------------------------------------------------------------

	def test_reader_cannot_write_although_the_docperm_would_allow_it(self):
		with self.registered():
			for ptype in ("write", "create", "delete", "submit"):
				with self.subTest(ptype=ptype):
					self.assertFalse(self.may(self.reader, "county_b", ptype))

	def test_an_acting_guard_ignores_the_reading_role(self):
		"""`guard` called without a ptype is how endpoints that act have always called it."""
		with self.registered():
			self.assertFalse(self.guard_permits(self.reader, "county_b"))

	# --- the officer is unchanged -------------------------------------------

	def test_the_officer_keeps_exactly_their_own_county(self):
		with self.registered():
			listed = self.listed_by(self.officer)

			self.assertEqual(listed, {self.records["county_a"], self.records["ward_a1"]})
			self.assertTrue(self.may(self.officer, "county_a", "write"))
			self.assertFalse(self.may(self.officer, "county_b", "read"))

	# --- configuration -------------------------------------------------------

	def test_unset_grants_nothing_and_logs_nothing(self):
		fixtures.set_scope_role_setting(None)
		before = fixtures.scope_role_log_count()

		with self.registered():
			self.assertEqual(self.listed_by(self.reader), set())

		self.assertEqual(fixtures.scope_role_log_count(), before)

	def test_a_role_that_does_not_exist_grants_nothing_and_is_logged(self):
		fixtures.set_scope_role_setting(NONEXISTENT_ROLE)
		before = fixtures.scope_role_log_count()

		with self.registered():
			self.assertEqual(self.listed_by(self.reader), set())
			# The officer's own access does not depend on the reading role.
			self.assertIn(self.records["county_a"], self.listed_by(self.officer))

		self.assertGreater(fixtures.scope_role_log_count(), before)
