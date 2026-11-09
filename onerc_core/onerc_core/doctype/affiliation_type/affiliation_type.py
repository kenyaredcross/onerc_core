# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AffiliationType(Document):
	def validate(self):
		self.affiliation_type_name = (self.affiliation_type_name or "").strip()
		self.validate_gating_capability()

	def validate_gating_capability(self):
		"""A gated type must name the capability that opens it.

		`requires_gated_read` on its own would be a gate with no key: the read
		service would have nothing to ask the capability resolver, and would
		(correctly) fail closed forever. Better to refuse the configuration.

		The capability is free text, not a Link, because capabilities are not
		built in this app — and it is a capability, never a role name.
		"""
		self.gating_capability = (self.gating_capability or "").strip()

		if self.requires_gated_read and not self.gating_capability:
			frappe.throw(
				_("{0} is required when {1} is set.").format(
					frappe.bold(_("Gating Capability")), frappe.bold(_("Requires Gated Read"))
				),
				frappe.MandatoryError,
				title=_("Gate Without a Key"),
			)

		if not self.requires_gated_read:
			# Cleared rather than kept, so a stale capability can never read as
			# though a gate were still in force.
			self.gating_capability = None
