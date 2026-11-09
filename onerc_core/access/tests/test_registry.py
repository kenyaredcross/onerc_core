# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from onerc_core.access.services import enforcement, registry
from onerc_core.access.services.registry import SCOPEABLE_DOCTYPE_HOOK
from onerc_core.access.tests import fixtures

EXTRA_TEST_RECORD_DEPENDENCIES = []

# A registration needs a real doctype with a real field to validate against, and
# these cases never query it — only its meta. ToDo serves, and using a framework
# doctype keeps the inversion honest: core is validating a registration for a
# doctype it has never heard of.
BORROWED_DOCTYPE = "ToDo"
BORROWED_FIELD = "reference_name"


class TestInertWithoutRegistrations(IntegrationTestCase):
	"""Core standalone. Nothing registered, nothing scoped, nothing broken.

	This is the state of a site with no product apps installed, and it is the
	state core ships in. The engine must be completely inert — not "safe by
	accident because there is no data", but structurally silent.
	"""

	def test_no_registrations(self):
		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: []}):
			self.assertEqual(registry.registrations(), {})
			self.assertEqual(registry.scoped_doctypes(), [])

	def test_nothing_is_scopeable(self):
		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: []}):
			self.assertIsNone(registry.for_doctype(BORROWED_DOCTYPE))
			self.assertIsNone(registry.for_doctype("Red Profile"))

	def test_the_query_layer_adds_no_condition(self):
		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: []}):
			self.assertEqual(
				enforcement.get_permission_query_conditions("Administrator", BORROWED_DOCTYPE), ""
			)

	def test_the_document_layer_denies_nothing(self):
		doc = frappe.get_doc({"doctype": BORROWED_DOCTYPE, "description": "ACC-TEST inert"})

		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: []}):
			self.assertTrue(enforcement.has_permission(doc=doc, ptype="read", user="Administrator"))

	def test_the_guard_permits(self):
		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: []}):
			# No exception is the assertion.
			enforcement.guard(BORROWED_DOCTYPE, "does-not-matter", user="Administrator")

	def test_an_unregistered_doctype_is_never_denied(self):
		"""None from the registry means "no opinion", never "deny"."""
		other = fixtures.registration(doctype=BORROWED_DOCTYPE, field=BORROWED_FIELD)

		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [other]}):
			self.assertTrue(enforcement.is_in_scope("Red Profile", None, "Administrator"))
			self.assertEqual(enforcement.get_permission_query_conditions("Administrator", "Red Profile"), "")


class TestRegistrationReading(IntegrationTestCase):
	def test_reads_a_declaration_back(self):
		entry = fixtures.registration(doctype=BORROWED_DOCTYPE, field=BORROWED_FIELD)

		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [entry]}):
			self.assertEqual(registry.scoped_doctypes(), [BORROWED_DOCTYPE])
			self.assertEqual(registry.for_doctype(BORROWED_DOCTYPE), entry)

	def test_core_names_no_product_doctype(self):
		"""The inversion, asserted against the source rather than by inspection.

		Core may only learn a doctype's name from a registration. Docstrings are
		exempt and deliberately so — `registry` documents the contract with a
		worked Volunteer example, and that is prose describing what an app would
		write, not core reaching for a doctype. What is checked is executable:
		string literals the code actually evaluates, and every module it imports.
		"""
		import ast
		import pathlib

		forbidden = ("Volunteer", "vmmsx", "onerc_vmms")
		services = pathlib.Path(enforcement.__file__).parent

		for module in sorted(services.glob("*.py")):
			tree = ast.parse(module.read_text())
			docstrings = {
				doc
				for node in ast.walk(tree)
				if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
				and (doc := ast.get_docstring(node, clean=False))
			}

			evaluated = [
				node.value
				for node in ast.walk(tree)
				if isinstance(node, ast.Constant)
				and isinstance(node.value, str)
				and node.value not in docstrings
			]

			for node in ast.walk(tree):
				if isinstance(node, ast.ImportFrom) and node.module:
					evaluated.append(node.module)
				elif isinstance(node, ast.Import):
					evaluated.extend(alias.name for alias in node.names)

			for name in forbidden:
				matches = [value for value in evaluated if name in value]

				self.assertEqual(
					matches,
					[],
					f"{module.name} evaluates {name} — a registration is the only way core may learn it",
				)

	def test_resolves_the_geo_field_against_the_doctype(self):
		entry = fixtures.registration(doctype=BORROWED_DOCTYPE, field=BORROWED_FIELD)

		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [entry]}):
			self.assertEqual(registry.geo_node_field(BORROWED_DOCTYPE), BORROWED_FIELD)


class TestBadRegistrations(IntegrationTestCase):
	"""A misconfigured security layer must be loud, never quietly permissive."""

	def _reject(self, entries, exception=frappe.ValidationError):
		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: entries}), self.assertRaises(exception):
			registry.registrations()

	def test_two_apps_claiming_one_doctype(self):
		self._reject(
			[
				fixtures.registration(doctype=BORROWED_DOCTYPE, field=BORROWED_FIELD),
				fixtures.registration(
					doctype=BORROWED_DOCTYPE, field=BORROWED_FIELD, role=fixtures.VIEWER_ROLE
				),
			]
		)

	def test_an_entry_that_is_not_a_dict(self):
		self._reject(["ToDo"])

	def test_a_missing_key(self):
		self._reject([{"doctype": BORROWED_DOCTYPE, "role": fixtures.APPROVER_ROLE}], frappe.MandatoryError)

	def test_an_empty_value(self):
		self._reject(
			[{"doctype": BORROWED_DOCTYPE, "geo_node_field": "", "role": fixtures.APPROVER_ROLE}],
			frappe.MandatoryError,
		)

	def test_a_field_the_doctype_does_not_have(self):
		"""Throwing beats the alternatives.

		Skipping the filter would leak every row of the doctype to every user;
		denying everything would look like missing data rather than the wiring
		mistake it is. Neither should be reachable by a typo.
		"""
		entry = fixtures.registration(doctype=BORROWED_DOCTYPE, field="home_geo_nod")

		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: [entry]}), self.assertRaises(frappe.ValidationError):
			registry.geo_node_field(BORROWED_DOCTYPE)

	def test_the_geo_field_of_an_unregistered_doctype(self):
		with self.patch_hooks({SCOPEABLE_DOCTYPE_HOOK: []}), self.assertRaises(frappe.ValidationError):
			registry.geo_node_field(BORROWED_DOCTYPE)
