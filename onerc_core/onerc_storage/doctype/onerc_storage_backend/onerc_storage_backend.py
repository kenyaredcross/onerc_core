# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class OneRCStorageBackend(Document):
	def validate(self):
		if self.is_default:
			others = frappe.get_all(
				"OneRC Storage Backend",
				filters={"is_default": 1, "name": ["!=", self.name]},
				pluck="name",
			)
			for name in others:
				frappe.db.set_value("OneRC Storage Backend", name, "is_default", 0)

		if self.backend_type != "Local (Frappe default)":
			if not self.bucket_name:
				frappe.throw(_("Bucket Name is required for non-local backends."))
			if not self.access_key_id:
				frappe.throw(_("Access Key ID is required for non-local backends."))

	@frappe.whitelist()
	def test_connection(self):
		from onerc_core.storage.backends import get_backend

		backend = get_backend(backend_name=self.name)
		return backend.test_connection()
