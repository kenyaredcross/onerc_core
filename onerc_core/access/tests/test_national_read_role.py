# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""A national reading role: holding it reads everywhere, and acts nowhere.

The case: a national officer (the Kenya Red Cross calls them the NSD
Coordinator) must see every region's records, and the society wants them known
by the role they hold rather than by a Geo Assignment at the top of the tree.
`national_read_role_from_setting` names that role. It needs no assignment.

As in `test_read_role`, the stand-in doctype gives the test roles full
DocPerms, so the only thing keeping the national reader from writing is this
layer.
"""

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.access.services import enforcement, registry
from onerc_core.access.services.registry import NATIONAL_READ_ROLE_SETTING_KEY, SCOPEABLE_DOCTYPE_HOOK
from onerc_core.access.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []

NONEXISTENT_ROLE = "ACC-TEST National Role That Does Not Exist"


def national_registration() -> dict:
	return {**fixtures.registration(fixtures.APPROVER_ROLE), NATIONAL_READ_ROLE_SETTING_KEY: fixtures.SCOPE_ROLE_SETTING}


class NationalReadRoleTestCase(IntegrationTestCase):
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
		cls.records["unplaced"] = fixtures.make_record("unplaced", None)

		# The county officer acts in County A. The national reader holds the
		# national role and no Geo Assignment at all.
		cls.officer = fixtures.make_user("national_officer", [fixtures.APPROVER_ROLE])
		cls.national = fixtures.make_user("national_reader", [fixtures.VIEWER_ROLE])
		fixtures.make_assignment(cls.officer, fixtures.APPROVER_ROLE, cls.tree["county_a"])

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
		return self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [national_registration()]})

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

		self.assertEqual(entry[NATIONAL_READ_ROLE_SETTING_KEY], fixtures.SCOPE_ROLE_SETTING)
		self.assertNotIn(NATIONAL_READ_ROLE_SETTING_KEY, registry._validated(fixtures.registration()))

	# --- reading ------------------------------------------------------------

	def test_national_reader_lists_and_opens_everything_without_an_assignment(self):
		with self.registered():
			listed = self.listed_by(self.national)

			for key in self.records:
				with self.subTest(key=key):
					self.assertIn(self.records[key], listed)
					self.assertTrue(self.may(self.national, key, "read"))
					self.assertTrue(self.guard_permits(self.national, key, ptype="read"))

	# --- acting -------------------------------------------------------------

	def test_national_reader_cannot_write_although_the_docperm_would_allow_it(self):
		with self.registered():
			for ptype in ("write", "create", "delete", "submit"):
				with self.subTest(ptype=ptype):
					self.assertFalse(self.may(self.national, "county_b", ptype))

	def test_an_acting_guard_ignores_the_national_role(self):
		with self.registered():
			self.assertFalse(self.guard_permits(self.national, "county_b"))

	# --- the officer is unchanged -------------------------------------------

	def test_the_officer_keeps_exactly_their_own_county(self):
		with self.registered():
			listed = self.listed_by(self.officer)

			self.assertEqual(listed, {self.records["county_a"], self.records["ward_a1"]})
			self.assertFalse(self.may(self.officer, "county_b", "read"))

	# --- configuration -------------------------------------------------------

	def test_unset_grants_nothing_and_logs_nothing(self):
		fixtures.set_scope_role_setting(None)
		before = fixtures.scope_role_log_count()

		with self.registered():
			self.assertEqual(self.listed_by(self.national), set())

		self.assertEqual(fixtures.scope_role_log_count(), before)

	def test_a_role_that_does_not_exist_grants_nothing_and_is_logged(self):
		fixtures.set_scope_role_setting(NONEXISTENT_ROLE)
		before = fixtures.scope_role_log_count()

		with self.registered():
			self.assertEqual(self.listed_by(self.national), set())

		self.assertGreater(fixtures.scope_role_log_count(), before)
