import frappe

from onerc_core.storage.backends import get_backend, get_backend_for_app


def on_file_after_insert(doc, method):
	"""
	Called every time any file is uploaded anywhere in Frappe.
	If external storage is configured, moves the file there.
	Falls back silently if not configured or if upload fails.
	"""
	try:
		backend = get_backend()

		# If backend is local, do nothing — file stays in Frappe local storage
		if backend.__class__.__name__ == "LocalBackend":
			return

		file_content = doc.get_content()
		if not file_content:
			return

		source_app = _detect_source_app(doc)
		backend_instance = get_backend_for_app(source_app)

		import datetime

		now = datetime.datetime.now()
		safe_name = doc.file_name.replace(" ", "-")
		folder = getattr(getattr(backend_instance, "backend", None), "folder_prefix", None) or "files"
		storage_key = (
			f"{folder}/{source_app or 'general'}/{now.year}/{now.month:02d}/{safe_name}"
		)

		url = backend_instance.upload(
			file_content=file_content,
			storage_key=storage_key,
			content_type=doc.content_type or "application/octet-stream",
			is_private=doc.is_private,
		)

		frappe.db.set_value("File", doc.name, "file_url", url)

		storage_file = frappe.get_doc(
			{
				"doctype": "OneRC Storage File",
				"file_name": doc.file_name,
				"storage_backend": backend_instance.backend.name,
				"storage_key": storage_key,
				"file_url": url,
				"file_size": doc.file_size,
				"content_type": doc.content_type,
				"is_private": doc.is_private,
				"source_app": source_app,
				"source_doctype": doc.attached_to_doctype,
				"source_document": doc.attached_to_name,
				"uploaded_at": frappe.utils.now_datetime(),
				"frappe_file": doc.name,
			}
		)
		storage_file.insert(ignore_permissions=True)

		# Remove the local copy to save disk space
		try:
			doc.delete_file_data_content()
		except Exception:
			pass

	except Exception as e:
		# NEVER break file upload — log and continue
		frappe.logger().error(
			f"onerc_storage: failed to move file to external storage: {e}. "
			"File kept in local storage."
		)


def _detect_source_app(file_doc):
	"""Identify which app owns this file from the attached_to_doctype field."""
	if not file_doc.attached_to_doctype:
		return None
	try:
		module = frappe.db.get_value(
			"DocType",
			file_doc.attached_to_doctype,
			"module",
		)
		if not module:
			return None
		app = frappe.db.get_value(
			"Module Def",
			module,
			"app_name",
		)
		return app
	except Exception:
		return None
