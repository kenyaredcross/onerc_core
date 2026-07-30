# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

TOP_LEVEL_ORDER = 1


class GeoLevel(Document):
	def validate(self):
		self.validate_single_lowest_level()
		self.validate_top_level_has_no_parent()

	def validate_single_lowest_level(self):
		"""At most one *active* level may be flagged as the lowest.

		Enforced as at-most-one rather than exactly-one: exactly-one cannot hold
		while the first level of a hierarchy is being created.
		"""
		if not (self.is_active and self.is_lowest_level):
			return

		conflict = frappe.db.get_value(
			"Geo Level",
			{
				"name": ("!=", self.name),
				"is_active": 1,
				"is_lowest_level": 1,
			},
			"name",
		)

		if conflict:
			frappe.throw(
				_("{0} is already the lowest active level. Only one active level may be the lowest.").format(
					frappe.bold(conflict)
				),
				title=_("Duplicate Lowest Level"),
			)

	def validate_top_level_has_no_parent(self):
		"""The level at the top of the hierarchy cannot require a parent."""
		if self.geo_level_order == TOP_LEVEL_ORDER and self.requires_parent:
			frappe.throw(
				_("The level at order {0} is the top of the hierarchy and cannot have {1} set.").format(
					frappe.bold(TOP_LEVEL_ORDER), frappe.bold(_("Requires Parent"))
				),
				title=_("Invalid Top Level"),
			)
