# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SocietyFeatureToggle(Document):
	"""One per-society switch.

	Core defines no feature list. The product reading a key owns its meaning and
	its default when the key is absent — absent is not off.
	"""
