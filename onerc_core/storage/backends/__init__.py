import frappe


def get_backend(backend_name=None):
	"""
	Returns an instance of the correct backend driver.

	If backend_name is given: load that specific backend.
	If not: load the default backend (is_default=1).
	If no default configured: return LocalBackend silently.
	"""
	from onerc_core.storage.backends.local import LocalBackend

	if backend_name:
		doc = frappe.get_doc("OneRC Storage Backend", backend_name)
	else:
		results = frappe.get_all(
			"OneRC Storage Backend",
			filters={"is_default": 1, "is_active": 1},
			limit=1,
		)
		if not results:
			return LocalBackend()
		doc = frappe.get_doc("OneRC Storage Backend", results[0].name)

	if doc.backend_type == "Local (Frappe default)":
		return LocalBackend(doc)

	from onerc_core.storage.backends.s3 import S3Backend

	return S3Backend(doc)


def get_backend_for_app(source_app):
	"""
	Check if any backend has app_binding matching source_app.
	If yes, return that backend. If no, return the default backend.
	"""
	if source_app:
		results = frappe.get_all(
			"OneRC Storage Backend",
			filters={"app_binding": source_app, "is_active": 1},
			limit=1,
		)
		if results:
			return get_backend(results[0].name)
	return get_backend()
