# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SocietyTerminology(Document):
	"""One word this society uses differently.

	Keys are free text: core does not own the vocabulary, so it cannot enumerate
	the terms a product might ask about. Normalisation and duplicate rejection
	happen on the parent, where the whole table is visible.
	"""
