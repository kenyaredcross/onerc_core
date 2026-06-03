from abc import ABC, abstractmethod


class BaseStorageBackend(ABC):

	def __init__(self, backend_doc):
		self.backend = backend_doc

	@abstractmethod
	def upload(self, file_content, storage_key, content_type, is_private):
		"""
		Upload file_content to storage_key in the bucket.
		Returns the URL (public or presigned based on config).
		"""

	@abstractmethod
	def get_url(self, storage_key):
		"""
		Return a URL for accessing the file.
		If make_public: return permanent public URL.
		If private: return presigned URL valid for signed_url_expiry seconds.
		"""

	@abstractmethod
	def delete(self, storage_key):
		"""Delete the file at storage_key from the bucket."""

	@abstractmethod
	def test_connection(self):
		"""
		Verify credentials and bucket access.
		Returns dict: {success: bool, message: str}
		"""
