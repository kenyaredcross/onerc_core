from onerc_core.storage.backends.base import BaseStorageBackend


class LocalBackend(BaseStorageBackend):
	"""
	No-op fallback used when no external storage is configured.
	Never throws errors — files stay in Frappe local storage.
	"""

	def __init__(self, backend_doc=None):
		self.backend = backend_doc

	def upload(self, file_content, storage_key, content_type, is_private):
		return None

	def get_url(self, storage_key):
		return None

	def delete(self, storage_key):
		pass

	def test_connection(self):
		return {
			"success": True,
			"message": "Local storage is active. No external configuration needed.",
		}
