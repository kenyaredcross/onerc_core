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
		self.normalise_terminology()
		self.normalise_feature_toggles()

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
					frappe.bold(self.time_zone), frappe.bold("Africa/Nairobi")
				),
				title=_("Unknown Time Zone"),
			)

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
