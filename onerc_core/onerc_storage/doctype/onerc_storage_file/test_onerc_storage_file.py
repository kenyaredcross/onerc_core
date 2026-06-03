# Copyright (c) 2026, Kelvin Njenga and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class IntegrationTestOneRCStorageFile(IntegrationTestCase):
	def setUp(self):
		frappe.db.delete("OneRC Storage Backend", {"backend_name": "_test-storage-backend"})
		frappe.db.delete("OneRC Storage File", {"source_app": "_test_app"})

	def tearDown(self):
		frappe.db.delete("OneRC Storage File", {"source_app": "_test_app"})
		frappe.db.delete("OneRC Storage Backend", {"backend_name": "_test-storage-backend"})

	def _create_local_backend(self):
		doc = frappe.get_doc(
			{
				"doctype": "OneRC Storage Backend",
				"backend_name": "_test-storage-backend",
				"label": "Test Local Backend",
				"backend_type": "Local (Frappe default)",
				"is_default": 1,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_storage_file_created_on_upload(self):
		backend_doc = self._create_local_backend()

		mock_s3_client = MagicMock()
		mock_s3_client.put_object.return_value = {}

		with patch("boto3.client", return_value=mock_s3_client):
			storage_file = frappe.get_doc(
				{
					"doctype": "OneRC Storage File",
					"file_name": "test-document.pdf",
					"storage_backend": backend_doc.name,
					"storage_key": "files/_test_app/2026/06/test-document.pdf",
					"file_url": "https://example.com/test-document.pdf",
					"file_size": 1024,
					"content_type": "application/pdf",
					"is_private": 1,
					"source_app": "_test_app",
					"source_doctype": "Stakeholder",
					"source_document": "STKH-0001",
				}
			)
			storage_file.insert(ignore_permissions=True)

		found = frappe.db.exists("OneRC Storage File", storage_file.name)
		self.assertTrue(found)
		self.assertEqual(
			frappe.db.get_value("OneRC Storage File", storage_file.name, "source_app"),
			"_test_app",
		)
