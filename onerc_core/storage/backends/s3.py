import frappe

from onerc_core.storage.backends.base import BaseStorageBackend


class S3Backend(BaseStorageBackend):
	"""S3-compatible backend — works with Cloudflare R2, AWS S3, Backblaze B2, MinIO."""

	def __init__(self, backend_doc):
		self.backend = backend_doc
		self.client = self._build_client()

	def _build_client(self):
		import boto3
		from frappe.utils.password import get_decrypted_password

		key = get_decrypted_password(
			"OneRC Storage Backend",
			self.backend.name,
			"access_key_id",
			raise_exception=False,
		)
		secret = get_decrypted_password(
			"OneRC Storage Backend",
			self.backend.name,
			"secret_access_key",
			raise_exception=False,
		)

		client_kwargs = {
			"aws_access_key_id": key,
			"aws_secret_access_key": secret,
			"region_name": self.backend.region or "auto",
		}
		if self.backend.endpoint_url:
			client_kwargs["endpoint_url"] = self.backend.endpoint_url

		return boto3.client("s3", **client_kwargs)

	def upload(self, file_content, storage_key, content_type, is_private):
		put_kwargs = {
			"Bucket": self.backend.bucket_name,
			"Key": storage_key,
			"Body": file_content,
			"ContentType": content_type or "application/octet-stream",
		}
		if self.backend.make_public:
			put_kwargs["ACL"] = "public-read"

		self.client.put_object(**put_kwargs)
		return self.get_url(storage_key)

	def get_url(self, storage_key):
		if self.backend.make_public:
			endpoint = (self.backend.endpoint_url or "https://s3.amazonaws.com").rstrip("/")
			return f"{endpoint}/{self.backend.bucket_name}/{storage_key}"

		expiry = int(self.backend.signed_url_expiry or 3600)
		return self.client.generate_presigned_url(
			"get_object",
			Params={"Bucket": self.backend.bucket_name, "Key": storage_key},
			ExpiresIn=expiry,
		)

	def delete(self, storage_key):
		self.client.delete_object(
			Bucket=self.backend.bucket_name,
			Key=storage_key,
		)

	def test_connection(self):
		try:
			self.client.list_objects_v2(
				Bucket=self.backend.bucket_name,
				MaxKeys=1,
			)
			return {
				"success": True,
				"message": f"Successfully connected to bucket '{self.backend.bucket_name}'.",
			}
		except Exception as e:
			return {"success": False, "message": str(e)}
