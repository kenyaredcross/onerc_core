# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname

from onerc_core.onerc_core.doctype.red_profile_affiliation.red_profile_affiliation import (
	SATELLITE_OWNED_FIELDS,
)

RED_PROFILE_NAMING_SERIES = "RP-.#####"

IDENTIFICATION_DOCTYPE = "Red Profile Identification"

# What makes two affiliation rows the same row, for the purpose of noticing that
# something wrote to the table without going through the service.
_ROW_IDENTITY_FIELDS = ("affiliation_type", *SATELLITE_OWNED_FIELDS)


class RedProfile(Document):
	"""One record per party, ever. The identity spine.

	Thin on purpose: who someone is, and an index of their affiliations. No
	domain data — a volunteer's skills and a member's fee live in satellite
	doctypes in other apps that link back here.

	The personal fields — gender, date of birth, citizenship, residence, and the
	documents someone holds — are not an exception to that. They are
	person-facts, true whatever roles the person holds, which is why they belong
	on the spine rather than being copied into every satellite that wants one.
	All of them are optional: a profile is created at registration with a name
	and an email, and whichever affiliation process needs more asks for it then.
	"""

	def autoname(self):
		# Opaque, like Geo Node and for the same reason. `email` is the current
		# identifier, but it is a *field*: keeping it out of the primary key is
		# what makes improving identity resolution a config change later rather
		# than a migration of every foreign key in every app.
		self.name = make_autoname(RED_PROFILE_NAMING_SERIES)

	def onload(self):
		# Gated affiliations are stripped server-side, before the document
		# reaches any client. The *existence* of such an affiliation is itself
		# sensitive, so this cannot be left to the UI.
		from onerc_core.identity.services import read_gate

		read_gate.apply(self)

	def validate(self):
		self.normalise_email()
		self.set_full_name()
		self.validate_phone_number()
		self.reconcile_residence()
		self.validate_identifications()
		self.guard_affiliations_are_service_written()

	def normalise_email(self):
		"""Lowercased and trimmed, so uniqueness means what it looks like.

		Without this, Ann@example.com and ann@example.com are two people on a
		case-sensitive collation and one duplicate-key error on a case-
		insensitive one. Neither is the behaviour anyone wants from an
		identifier.
		"""
		self.email = (self.email or "").strip().lower()

	def set_full_name(self):
		"""Composed, read-only. Display only — never logic."""
		parts = (self.first_name, self.middle_name, self.last_name)
		self.full_name = " ".join(part.strip() for part in parts if part and part.strip())

	def validate_phone_number(self):
		"""Checked against the society's configured pattern — never a regex here.

		A society that has not declared its numbering plan does not get one
		invented for it: no pattern configured means no check.
		"""
		from onerc_core.society.services import config

		self.phone = (self.phone or "").strip()

		config.validate_phone_number(self.phone, self.meta.get_label("phone"))

	def reconcile_residence(self):
		"""Keep the two residence shapes mutually exclusive.

		A local residence is a Geo Node in the society's own tree. An address
		abroad has no honest node in that tree, so it is a country and free-text
		address instead. Switching the toggle clears the answer that no longer
		applies rather than leaving two conflicting current residences on the
		person.
		"""
		if self.residency_type == "Abroad":
			self.home_geo_node = None
		elif self.residency_type == "Local":
			self.country_of_residence = None
			self.residence_address = None

	def validate_identifications(self):
		"""Tidy the rows, and keep "primary" meaning one thing.

		Nothing here is required — a profile may carry no documents at all, and
		completeness is a question the volunteer and member affiliation
		processes ask when they need an answer. What is worth refusing is a
		second primary: whoever later asks "which document do we quote for this
		person" must get one answer, not a choice.

		Two rows of the same type are fine and deliberately allowed. Dual
		citizenship may mean two passports, and a society that could not record
		both would be back at the flat fields this table replaced.
		"""
		primary = 0

		for row in self.identifications:
			row.id_number = (row.id_number or "").strip()
			primary += 1 if row.is_primary else 0

		if primary > 1:
			label = frappe.get_meta(IDENTIFICATION_DOCTYPE).get_label("is_primary")

			frappe.throw(
				_("Only one identification may be marked {0}.").format(frappe.bold(_(label))),
				title=_("More Than One Primary"),
			)

	def guard_affiliations_are_service_written(self):
		"""Keep the affiliation index derived, by refusing writes from elsewhere.

		Design 2: this table is a denormalised index whose truth lives in
		satellite doctypes in other apps. A write that did not come through
		`set_affiliation()` cannot have been checked against a satellite, so it
		is not applied. Field-level `read_only` stops the form; this stops the
		API, an import, and a satellite that reached into the child table.

		The two cases differ on purpose:

		* On an **existing** profile the persisted rows are put back and the
		  save continues. A reader whose gated rows were stripped on load will
		  post the document back without them, and must still be able to edit
		  an unrelated field like `phone` without silently deleting rows they
		  were never allowed to see.
		* On a **new** profile there is nothing to put back and no such reader,
		  so inline rows can only be a programming error. Those are rejected
		  loudly rather than dropped quietly.
		"""
		if self.flags.affiliations_from_service:
			return

		# Populated by check_if_latest() before validate() runs — but only for
		# updates. None here means this is an insert.
		before = self.get_doc_before_save()

		if before is None:
			if self.affiliations:
				frappe.throw(
					_(
						"Affiliations cannot be set directly. Insert the profile first, then let the"
						" satellite record write its own row through set_affiliation()."
					),
					title=_("Affiliations Are Derived"),
				)

			return

		if _signature(self.affiliations) == _signature(before.affiliations):
			return

		self.set("affiliations", [row.as_dict() for row in before.affiliations])


def _signature(rows) -> list[tuple]:
	"""Order-independent content fingerprint of an affiliation table."""
	return sorted(tuple(str(row.get(field) or "") for field in _ROW_IDENTITY_FIELDS) for row in (rows or []))
