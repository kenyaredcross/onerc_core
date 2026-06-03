import datetime

import frappe

from onerc_core.storage.backends import get_backend, get_backend_for_app


@frappe.whitelist()
def store_file(
	file_content,
	filename,
	source_app,
	source_doctype=None,
	source_document=None,
	is_private=True,
	backend_name=None,
	content_type=None,
):
	"""
	The single function any OneRC app calls to store a file in external storage.

	Returns {storage_file, url, storage_key}.
	"""
	if backend_name:
		backend = get_backend(backend_name=backend_name)
	else:
		backend = get_backend_for_app(source_app)

	folder = (
		getattr(getattr(backend, "backend", None), "folder_prefix", None) or "files"
	)
	now = datetime.datetime.now()
	safe_name = filename.replace(" ", "-")
	storage_key = f"{folder}/{source_app or 'general'}/{now.year}/{now.month:02d}/{safe_name}"

	url = backend.upload(
		file_content=file_content,
		storage_key=storage_key,
		content_type=content_type or "application/octet-stream",
		is_private=bool(is_private),
	)

	storage_file = frappe.get_doc(
		{
			"doctype": "OneRC Storage File",
			"file_name": filename,
			"storage_backend": backend.backend.name if backend.backend else None,
			"storage_key": storage_key,
			"file_url": url,
			"file_size": len(file_content) if file_content else 0,
			"content_type": content_type,
			"is_private": int(bool(is_private)),
			"source_app": source_app,
			"source_doctype": source_doctype,
			"source_document": source_document,
			"uploaded_at": frappe.utils.now_datetime(),
		}
	)
	storage_file.insert(ignore_permissions=True)

	return {
		"storage_file": storage_file.name,
		"url": url,
		"storage_key": storage_key,
	}


@frappe.whitelist()
def get_file_url(storage_file_name, expiry=3600):
	"""Get a fresh URL for a stored file."""
	doc = frappe.get_doc("OneRC Storage File", storage_file_name)
	backend = get_backend(backend_name=doc.storage_backend)

	if doc.is_private:
		# temporarily override expiry on the backend if caller requested a different value
		original_expiry = getattr(getattr(backend, "backend", None), "signed_url_expiry", None)
		if backend.backend:
			backend.backend.signed_url_expiry = int(expiry)
		url = backend.get_url(doc.storage_key)
		if backend.backend and original_expiry is not None:
			backend.backend.signed_url_expiry = original_expiry
	else:
		url = backend.get_url(doc.storage_key)

	return {"url": url}


@frappe.whitelist()
def delete_file(storage_file_name):
	"""Delete a file from external storage and remove the OneRC Storage File record."""
	doc = frappe.get_doc("OneRC Storage File", storage_file_name)
	backend = get_backend(backend_name=doc.storage_backend)

	try:
		backend.delete(doc.storage_key)
	except Exception as e:
		frappe.log_error(f"onerc_storage: delete failed for {doc.storage_key}: {e}")
		frappe.throw(frappe._("Failed to delete file from storage: {0}").format(str(e)))

	doc.delete(ignore_permissions=True)
	return {"deleted": storage_file_name}


@frappe.whitelist()
def test_backend_connection(backend_name):
	"""Called from the Test Connection button on the OneRC Storage Backend form."""
	backend = get_backend(backend_name=backend_name)
	return backend.test_connection()


@frappe.whitelist()
def list_backends():
	"""Returns all active backends with metadata. Used by other apps."""
	backends = frappe.get_all(
		"OneRC Storage Backend",
		filters={"is_active": 1},
		fields=["name", "label", "backend_type", "purpose", "is_default", "app_binding"],
		order_by="is_default desc, label asc",
	)
	return backends
