# onerc_storage Module

**App:** `onerc_core`  
**Module:** `Onerc Storage`  
**Branch:** `onerc_storage`  
**Last Updated:** June 2026

---

## Overview

`onerc_storage` is a file storage abstraction module inside `onerc_core`. It automatically routes all Frappe file uploads to any S3-compatible external storage provider — Cloudflare R2, AWS S3, Backblaze B2, or MinIO — with zero code changes required in any OneRC app.

When no external storage is configured, the module does nothing. All files go to Frappe's default local storage. This means the module is safe to install on any site without breaking anything.

---

## Why It Exists

Every OneRC app handles file uploads — vendor documents in `onerc_prequalification`, donation receipts in `onerc_donations`, volunteer IDs in `onerc_vmms`, beneficiary documents in `onerc_bcm`. Without external storage, all of these accumulate on the Frappe Cloud server. A single prequalification exercise with 1,286 vendors uploading 10 documents each is approximately 25GB. Two exercises and the server has a problem.

`onerc_storage` solves this once for all apps. Configure a bucket, and every file upload from every app — current and future — goes to external storage automatically.

---

## Architecture

```
Vendor uploads a file (any app, any DocType)
        ↓
Frappe's upload_file endpoint saves the file locally
        ↓
File.after_insert fires → on_file_after_insert() called
        ↓
onerc_storage checks: is an external backend configured?
        ↓
    No → do nothing, file stays local, no error
        ↓
   Yes → detect which app created the file
        → find the right backend (app-specific or default)
        → upload file content to S3
        → update Frappe File record URL to S3 URL
        → create OneRC Storage File record
        → delete local copy to save disk space
```

The calling app — `onerc_prequalification`, `onerc_donations`, any app — never knows this happened. It calls `upload_file` as normal. The interception is transparent.

---

## DocTypes

### OneRC Storage Backend

Stores the configuration for one external storage bucket. Multiple records are allowed — each record is one bucket. One record must be marked as the default.

**Autoname:** `field:backend_name`

| Field | Type | Notes |
|---|---|---|
| backend_name | Data | Machine-readable unique name. Example: `r2-main`, `s3-documents` |
| label | Data | Human label shown in the UI |
| backend_type | Select | Cloudflare R2 / AWS S3 / Backblaze B2 / MinIO / Local |
| is_active | Check | Default: checked |
| is_default | Check | Only one backend can be default at a time — enforced by controller |
| bucket_name | Data | Name of the S3 bucket |
| folder_prefix | Data | Optional folder inside the bucket. Example: `onerc/files` |
| endpoint_url | Data | Required for R2, MinIO. Leave blank for standard AWS S3 |
| region | Data | AWS region or `auto` for Cloudflare R2 |
| access_key_id | Password | Stored encrypted |
| secret_access_key | Password | Stored encrypted |
| signed_url_expiry | Int | How long presigned URLs are valid in seconds. Default: 3600 |
| make_public | Check | If checked, files get permanent public URLs instead of presigned |
| purpose | Small Text | Human description. Example: "All vendor prequalification documents" |
| app_binding | Data | Optional. If set, this backend is used when files come from this app |

**Controller behaviour:**
- `validate()`: if `is_default` is checked, all other backends have their `is_default` unchecked. Only one default is allowed.
- `validate()`: if backend_type is not Local, `bucket_name` and `access_key_id` are required.
- `test_connection()`: called from the Test Connection button. Attempts to list objects in the bucket using boto3. Returns a success or failure message.

---

### OneRC Storage File

Tracks every file that has been moved to external storage. One record per file.

**Autoname:** `STRF-.YYYY.-.#####`

| Field | Type | Notes |
|---|---|---|
| file_name | Data | Original filename |
| storage_backend | Link | → OneRC Storage Backend |
| storage_key | Data | The path inside the bucket. Example: `onerc/files/2026/06/pin-cert.pdf` |
| file_url | Data | Public or presigned URL |
| file_size | Int | File size in bytes |
| content_type | Data | MIME type. Example: `application/pdf` |
| is_private | Check | Default: checked |
| source_app | Data | Which app uploaded the file. Example: `onerc_prequalification` |
| source_doctype | Data | Which DocType the file is attached to |
| source_document | Data | Which specific record |
| uploaded_at | Datetime | When it was stored in external storage |
| frappe_file | Link | → Frappe File record |

---

## Backend Drivers

### base.py — Abstract Base Class

Every storage backend must inherit from `BaseStorageBackend` and implement four methods:

```python
class BaseStorageBackend(ABC):

    def __init__(self, backend_doc):
        # backend_doc is the OneRC Storage Backend frappe document
        self.backend = backend_doc

    @abstractmethod
    def upload(self, file_content, storage_key, content_type, is_private):
        # Upload file_content to storage_key in the bucket
        # Returns the URL (public or presigned)

    @abstractmethod
    def get_url(self, storage_key):
        # Return a URL for accessing the file
        # If make_public: permanent public URL
        # If private: presigned URL valid for signed_url_expiry seconds

    @abstractmethod
    def delete(self, storage_key):
        # Delete the file at storage_key from the bucket

    @abstractmethod
    def test_connection(self):
        # Verify credentials and bucket access
        # Returns: {"success": True/False, "message": "..."}
```

---

### s3.py — S3-Compatible Backend

Handles Cloudflare R2, AWS S3, Backblaze B2, and MinIO. Uses `boto3`.

Credentials are read using `frappe.utils.password.get_decrypted_password()` — they are never stored in plain text in memory longer than needed.

The boto3 client is built like this:

```python
client_kwargs = {
    "aws_access_key_id": key,
    "aws_secret_access_key": secret,
    "region_name": self.backend.region or "auto",
}
if self.backend.endpoint_url:
    client_kwargs["endpoint_url"] = self.backend.endpoint_url

self.client = boto3.client("s3", **client_kwargs)
```

Setting `endpoint_url` is what makes it work with R2 and other non-AWS providers. Without it, boto3 defaults to AWS.

---

### local.py — Local Fallback

A no-op backend. Does nothing. Never raises an error. Used when no external storage backend is configured — the system falls back to this silently, and Frappe's normal local storage behaviour continues unchanged.

---

## Backend Registry

`onerc_core/storage/backends/__init__.py` exposes two functions that every other part of the system uses:

```python
def get_backend(backend_name=None):
    """
    Returns an instance of the correct backend driver.

    If backend_name is given: load that specific backend.
    If not: load the default backend (is_default=1).
    If no default configured: return LocalBackend silently.
    """

def get_backend_for_app(source_app):
    """
    Check if any backend has app_binding matching source_app.
    If yes, return that backend.
    If no match: return the default backend.
    """
```

These are the only two functions any other code should ever call. Nothing imports the drivers directly.

---

## API Endpoints

All in `onerc_core/storage/api/v1/storage.py`. All decorated with `@frappe.whitelist()`.

### `store_file`

```python
store_file(
    file_content,       # bytes — the file content
    filename,           # str — original filename
    source_app,         # str — which app is uploading
    source_doctype,     # str — optional, which DocType
    source_document,    # str — optional, which record
    is_private,         # bool — default True
    backend_name,       # str — optional, use specific backend
    content_type,       # str — MIME type, optional
)
```

Returns:
```json
{
    "storage_file": "STRF-2026-00001",
    "url": "https://...",
    "storage_key": "onerc/files/2026/06/file.pdf"
}
```

This is the function any OneRC app can call if they want explicit control over which bucket a file goes to. For most cases, the automatic interception handles everything without calling this directly.

---

### `get_file_url`

```python
get_file_url(storage_file_name, expiry=3600)
```

Returns a fresh URL for a stored file. For private files, generates a new presigned URL with the given expiry. For public files, returns the permanent URL. Use this when you need to serve a file to a user and the presigned URL may have expired.

---

### `delete_file`

```python
delete_file(storage_file_name)
```

Deletes the file from external storage and removes the `OneRC Storage File` record.

---

### `test_backend_connection`

```python
test_backend_connection(backend_name)
```

Called from the Test Connection button on the `OneRC Storage Backend` form. Returns `{"success": True/False, "message": "..."}`. Tests the actual connection to the bucket without uploading anything.

---

### `list_backends`

```python
list_backends()
```

Returns all active backends with their label, type, purpose, and default status. Used by other apps or admin interfaces to show available storage options.

---

## Upload Interception — How It Works

`on_file_after_insert` in `onerc_core/storage/hooks.py` is the core of the automatic routing.

```python
# In onerc_core/hooks.py
doc_events = {
    "File": {
        "after_insert": "onerc_core.storage.hooks.on_file_after_insert"
    }
}
```

Every time any file is uploaded anywhere in Frappe — regardless of which app or DocType — this function runs. The sequence is:

1. Get the default backend. If it is `LocalBackend`, return immediately — nothing to do.
2. Read the file content from Frappe's local storage.
3. Detect which app created the file from `attached_to_doctype`.
4. Find the right backend using `get_backend_for_app()`.
5. Build the storage key: `{folder_prefix}/{source_app}/{YYYY}/{MM}/{filename}`.
6. Upload to external storage via `backend.upload()`.
7. Update the `Frappe File` record's `file_url` to point to the external URL.
8. Create an `OneRC Storage File` record.
9. Delete the local file copy.

**Critical:** The entire function is wrapped in `try/except`. If anything fails at any step, the error is logged and the function returns without raising. The file upload always succeeds from the user's perspective — it just stays local if external storage fails.

---

## Configuration Guide

### Step 1 — Create a Cloudflare R2 Bucket

1. Go to `cloudflare.com` and sign in
2. Click **R2 Object Storage** in the sidebar
3. Click **Create bucket**
4. Name the bucket — example: `onerc-files`
5. Location: leave as automatic
6. Click **Create bucket**
7. Note your **Account ID** from the R2 overview page

### Step 2 — Create API Credentials

1. On the R2 overview page click **Manage R2 API Tokens**
2. Click **Create API Token**
3. Name: `onerc-frappe`
4. Permissions: **Object Read and Write**
5. Bucket scope: select your bucket
6. Click **Create API Token**
7. Copy the **Access Key ID** and **Secret Access Key** — the secret is shown only once

### Step 3 — Configure in Frappe Desk

Go to **Desk → OneRC Storage Backend → New**

| Field | Value |
|---|---|
| Backend Name | `r2-main` |
| Label | `Cloudflare R2 (Main)` |
| Backend Type | `Cloudflare R2` |
| Is Active | checked |
| Is Default | checked |
| Bucket Name | your bucket name |
| Endpoint URL | `https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com` |
| Region | `auto` |
| Access Key ID | your Access Key ID |
| Secret Access Key | your Secret Access Key |
| Signed URL Expiry | `3600` |
| Make Public | unchecked (keep files private) |

Save. Then click **Test Connection**. You should see a success message.

### Step 4 — Verify

Upload any file via Frappe desk (attach to any record). Then:
- Check your Cloudflare R2 bucket — the file should appear there
- Check **Desk → OneRC Storage File** — a record should appear
- The Frappe File record's URL should point to the R2 URL

---

## Multiple Buckets

You can create multiple `OneRC Storage Backend` records to route different apps to different buckets.

**Example setup for KRCS:**

| Backend Name | Bucket | App Binding | Is Default |
|---|---|---|---|
| `r2-prequalification` | `onerc-prequal-files` | `onerc_prequalification` | No |
| `r2-donations` | `onerc-donation-files` | `onerc_donations` | No |
| `r2-main` | `onerc-files` | *(blank)* | Yes |

Files from `onerc_prequalification` go to the prequalification bucket. Files from `onerc_donations` go to the donations bucket. Everything else goes to the main default bucket.

The `app_binding` field controls this. Leave it blank on the default backend.

---

## Integration Guide — For Other OneRC Apps

### Automatic (Recommended)

Do nothing. Install `onerc_core`. Configure a backend in the desk. All file uploads from your app automatically go to external storage.

### Explicit (When You Need Control)

If your app needs to store a file programmatically and wants to target a specific bucket:

```python
from onerc_core.storage.api.v1.storage import store_file

result = store_file(
    file_content=pdf_bytes,
    filename="receipt-2026-001.pdf",
    source_app="onerc_donations",
    source_doctype="Donation",
    source_document="DON-2026-00001",
    is_private=True,
    content_type="application/pdf",
)

# result = {
#     "storage_file": "STRF-2026-00001",
#     "url": "https://...",
#     "storage_key": "onerc/files/2026/06/receipt-2026-001.pdf"
# }
```

### Getting a Fresh URL

Presigned URLs expire. When you need to serve a file that may have been stored a while ago:

```python
from onerc_core.storage.api.v1.storage import get_file_url

result = get_file_url("STRF-2026-00001", expiry=3600)
# Returns a fresh URL valid for 1 hour
```

---

## Adding a New Storage Backend

To add support for a new provider (example: DigitalOcean Spaces):

1. Create `onerc_core/onerc_core/storage/backends/spaces.py`
2. Inherit from `BaseStorageBackend`
3. Implement all four methods: `upload`, `get_url`, `delete`, `test_connection`
4. Add `DigitalOcean Spaces` to the `backend_type` Select field options on `OneRC Storage Backend`
5. Update the `get_backend()` function in `__init__.py` to load your new class when `backend_type == "DigitalOcean Spaces"`
6. Add any new credential fields to `OneRC Storage Backend`
7. Write tests

DigitalOcean Spaces is S3-compatible — the existing `s3.py` driver would work with a different endpoint URL. You may not need a new driver at all.

---

## Tests

Four tests, all passing:

| Test | What It Checks |
|---|---|
| `test_only_one_default_allowed` | Create two backends, set both as default, verify only the second ends up as default |
| `test_local_backend_requires_no_credentials` | Create a Local backend without credentials, verify no error |
| `test_s3_backend_requires_bucket_name` | Create an S3 backend without bucket name, verify MandatoryError |
| `test_storage_file_created_on_upload` | Mock S3 client, simulate upload, verify OneRC Storage File record created |

Run tests:
```bash
bench run-tests --app onerc_core --module onerc_storage
```

---

## Files Created

| File | Purpose |
|---|---|
| `onerc_core/onerc_storage/doctype/onerc_storage_backend/onerc_storage_backend.json` | DocType definition — 20 fields |
| `onerc_core/onerc_storage/doctype/onerc_storage_backend/onerc_storage_backend.py` | Controller — validates, enforces single default, test_connection |
| `onerc_core/onerc_storage/doctype/onerc_storage_backend/onerc_storage_backend.js` | Client script — Test Connection button |
| `onerc_core/onerc_storage/doctype/onerc_storage_backend/test_onerc_storage_backend.py` | 3 tests |
| `onerc_core/onerc_storage/doctype/onerc_storage_file/onerc_storage_file.json` | DocType definition — 15 fields |
| `onerc_core/onerc_storage/doctype/onerc_storage_file/onerc_storage_file.py` | Controller |
| `onerc_core/onerc_storage/doctype/onerc_storage_file/test_onerc_storage_file.py` | 1 test |
| `onerc_core/storage/backends/base.py` | Abstract base class |
| `onerc_core/storage/backends/local.py` | Local fallback — no-op |
| `onerc_core/storage/backends/s3.py` | S3-compatible driver — R2, AWS, B2, MinIO |
| `onerc_core/storage/backends/__init__.py` | Registry — get_backend(), get_backend_for_app() |
| `onerc_core/storage/api/v1/storage.py` | 5 whitelisted API endpoints |
| `onerc_core/storage/hooks.py` | File.after_insert interception |

**Modified:**
- `modules.txt` — added `Onerc Storage`
- `hooks.py` — wired `File.after_insert`
- `pyproject.toml` — added `boto3>=1.20.0`

---

## Known Limitations

- Files uploaded before a backend is configured stay in local storage permanently unless manually migrated
- The module intercepts uploads at `after_insert` — files are briefly stored locally before being moved. On slow connections or large files, there is a short window where the file exists in both places
- Presigned URLs expose the file for the duration of `signed_url_expiry`. If a file is deleted from R2 manually, existing presigned URLs will 404

---

## Roadmap

- Migration utility — move existing local files to external storage in bulk
- DigitalOcean Spaces driver
- Azure Blob Storage driver
- OneDrive / SharePoint driver (for organisations with Office 365 mandates)
- Storage quota monitoring — alert when bucket usage exceeds a threshold
- Move payments abstraction from `onerc_payments` into `onerc_core` (planned post go-live)
