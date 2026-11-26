# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class RedProfileIdentification(Document):
	"""One identity document a person holds.

	A table rather than flat fields because a person may hold several at once:
	a national ID and a passport, or two passports under dual citizenship. The
	flat `passport_number` / `id_number` / `id_document_type` shape could only
	ever record one, and left the reader guessing which.

	Nothing here is required. Completeness is a question the volunteer and
	member affiliation processes ask when they need an answer; the identity
	spine stays thin at registration.

	Row-level rules live on the parent: Frappe runs `validate` on the document
	being saved, not on its children, so a guard written here would never fire.
	See `RedProfile.validate_identifications`.
	"""
