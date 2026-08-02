# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import re
from zoneinfo import available_timezones

import frappe
from frappe import _
from frappe.model.document import Document


class NationalSocietySettings(Document):
	"""Per-society configuration. The answer to every "no hardcoded X" rule.

	Country, currency, phone pattern, terminology, theme and feature switches all
	live here, so a second national society can deploy the same products without
	a code change.

	Read through `onerc_core.society.services.config.get_ui_config()`, not field
	by field — the service applies the fallbacks (System Settings for unset
	locale, the main logo for the dark one) that individual fields cannot.
	"""

	def validate(self):
		self.validate_time_zone()
		self.validate_phone_number_pattern()
		self.validate_scope_roles()
		self.normalise_terminology()
		self.normalise_feature_toggles()

	def validate_scope_roles(self):
		"""A settings field naming which role scopes a doctype must name a real one.

		The config-time half of the access layer's fail-loud rule. An app may
		register a scopeable doctype whose role comes from a field here
		(`role_from_setting`); if that field holds a role that does not exist,
		every user is denied that doctype, and the symptom — an empty list view —
		looks exactly like "nobody has been granted anything yet".

		So a **non-empty** value is checked against `tabRole` and refused here,
		while the administrator is still looking at the form. An **empty** value
		saves fine: a society that has not chosen the role yet has not made a
		mistake, and enforcement fails closed and logs until they do.

		Reading core's own registry hook is not a dependency on a product app —
		it is the aggregated declaration, and core never learns a doctype's name
		any other way.
		"""
		from onerc_core.access.services import registry

		try:
			settings_backed = registry.settings_backed_registrations()
		except frappe.ValidationError:
			# Some app's registration is malformed. That is already loud in every
			# enforcement path, and blocking this form would lock an
			# administrator out of the one screen that fixes configuration.
			frappe.log_error(
				title="Scope registrations could not be read while validating settings",
				message=frappe.get_traceback(),
			)

			return

		for registration in settings_backed:
			fieldname = registration[registry.ROLE_SETTING_KEY]
			role = (self.get(fieldname) or "").strip()

			if not role or frappe.db.exists("Role", role):
				continue

			frappe.throw(
				_(
					"{0} is set to {1}, which is not a Frappe role. It decides who may see {2}, so"
					" a name matching nothing would deny everybody."
				).format(
					frappe.bold(_(self.meta.get_label(fieldname) or fieldname)),
					frappe.bold(role),
					frappe.bold(registration["doctype"]),
				),
				title=_("Unknown Scope Role"),
			)

	def validate_time_zone(self):
		"""An unrecognised zone is worse than a blank one — it fails at use.

		Checked against the system's own IANA database rather than a list
		hardcoded here, which would rot.
		"""
		self.time_zone = (self.time_zone or "").strip()

		if not self.time_zone:
			return

		# Membership test rather than constructing a ZoneInfo and catching: it
		# reads plainly, and it covers both an unknown name and a malformed one
		# without a two-exception except clause.
		if self.time_zone not in available_timezones():
			frappe.throw(
				_("{0} is not an IANA time zone name. Expected something like {1}.").format(
					frappe.bold(self.time_zone), frappe.bold(self.time_zone_example())
				),
				title=_("Unknown Time Zone"),
			)

	@staticmethod
	def time_zone_example() -> str:
		"""A worked example for the message above, relevant to this site.

		The site's own zone, collected by Frappe at setup. It used to be a
		hardcoded "Africa/Nairobi", which reads as an instruction to every
		society that is not Kenyan — the same reason no country, currency or
		phone pattern is hardcoded anywhere else in this app.

		`Region/City` when System Settings has nothing to offer: a shape rather
		than a place, which is what the message is really demonstrating.
		"""
		return frappe.db.get_single_value("System Settings", "time_zone") or "Region/City"

	def validate_phone_number_pattern(self):
		"""A pattern that does not compile would reject every number entered.

		Fail here, once, at configuration time — not on every profile save.
		"""
		self.phone_number_pattern = (self.phone_number_pattern or "").strip()

		if not self.phone_number_pattern:
			return

		try:
			re.compile(self.phone_number_pattern)
		except re.error as exc:
			frappe.throw(
				_("{0} is not a valid regular expression: {1}").format(
					frappe.bold(self.phone_number_pattern), exc
				),
				title=_("Invalid Phone Number Pattern"),
			)

	def normalise_terminology(self):
		self._normalise_keyed_table("terminology", "term_key", _("Terminology"))

		for row in self.terminology:
			row.singular = (row.singular or "").strip()
			row.plural = (row.plural or "").strip()

	def normalise_feature_toggles(self):
		self._normalise_keyed_table("feature_toggles", "feature_key", _("Feature Toggles"))

	def _normalise_keyed_table(self, fieldname: str, keyfield: str, label: str):
		"""Lower snake case the keys, and reject a duplicate.

		Products look these up by key, so "Self Service" and "self_service" being
		two rows means one of them silently never gets read.
		"""
		seen: dict[str, int] = {}

		for row in self.get(fieldname) or []:
			key = re.sub(r"[\s-]+", "_", (row.get(keyfield) or "").strip().lower())
			row.set(keyfield, key)

			if not key:
				continue

			if key in seen:
				frappe.throw(
					_("{0} row {1} repeats the key {2}, already used in row {3}.").format(
						label, row.idx, frappe.bold(key), seen[key]
					),
					title=_("Duplicate Key"),
				)

			seen[key] = row.idx
