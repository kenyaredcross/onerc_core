# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class IdentificationType(Document):
	"""A kind of identity document a person may hold.

	A configuration vocabulary, like Affiliation Type and Geo Level, and keyed
	by data for the same reason: societies name these, imports refer to them,
	and the key is the stable identifier. Which documents a society recognises
	is its own business, so the seeded set is a starting point rather than a
	closed list.

	Nothing in this app branches on a key. The vocabulary exists so a person may
	be recorded holding a national ID *and* a passport, which flat
	`passport_number` / `id_number` fields could never express.
	"""

	def validate(self):
		self.identification_type_name = (self.identification_type_name or "").strip()
