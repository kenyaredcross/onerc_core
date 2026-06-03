# Copyright (c) 2026, Kelvin Njenga and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class IntegrationTestOneRCStorageBackend(IntegrationTestCase):
	def setUp(self):
		frappe.db.delete("OneRC Storage Backend", {"backend_name": ["like", "_test-%"]})

	def tearDown(self):
		frappe.db.delete("OneRC Storage Backend", {"backend_name": ["like", "_test-%"]})

	def _make_backend(self, name, backend_type="Local (Frappe default)", is_default=0, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "OneRC Storage Backend",
				"backend_name": name,
				"label": name,
				"backend_type": backend_type,
				"is_default": is_default,
				**kwargs,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_only_one_default_allowed(self):
		first = self._make_backend("_test-first", is_default=1)
		self.assertEqual(frappe.db.get_value("OneRC Storage Backend", first.name, "is_default"), 1)

		second = self._make_backend("_test-second", is_default=1)
		self.assertEqual(frappe.db.get_value("OneRC Storage Backend", second.name, "is_default"), 1)
		self.assertEqual(frappe.db.get_value("OneRC Storage Backend", first.name, "is_default"), 0)

	def test_local_backend_requires_no_credentials(self):
		doc = self._make_backend("_test-local-only", backend_type="Local (Frappe default)")
		self.assertEqual(doc.backend_type, "Local (Frappe default)")

	def test_s3_backend_requires_bucket_name(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._make_backend(
				"_test-s3-no-bucket",
				backend_type="AWS S3",
				bucket_name=None,
				access_key_id="somekey",
			)
