# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# Fields a satellite owns on its row. Everything the index carries, in other
# words, except which type the row is — that identifies the row.
SATELLITE_OWNED_FIELDS = (
	"status",
	"reference_doctype",
	"reference_name",
	"start_date",
	"end_date",
)


class RedProfileAffiliation(Document):
	"""One line of a Red Profile's affiliation index.

	Every field is read-only. Rows are written by
	`onerc_core.identity.services.affiliation.set_affiliation()` and by nothing
	else — not by the form, not by a satellite reaching into the child table.
	The row is a derived summary; the satellite named in `reference_doctype` /
	`reference_name` is the source of truth, and is allowed to disagree with it.
	"""


def allowed_statuses() -> list[str]:
	"""The status vocabulary, read from the field's own options.

	Read rather than restated so there is exactly one copy of the list. The
	service validates against this; nothing hardcodes it a second time.
	"""
	options = frappe.get_meta("Red Profile Affiliation").get_field("status").options or ""

	return [status for status in options.split("\n") if status]
