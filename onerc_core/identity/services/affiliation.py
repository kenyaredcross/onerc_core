# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Affiliation index services — the only supported way to write the index.

Design 2. A Red Profile's `affiliations` child table is a denormalised index,
never a source of truth. What makes someone an active volunteer is a Volunteer
satellite existing and being active, in whichever app owns volunteering; the row
here is a summary that satellite writes through `set_affiliation()`.

Two consequences run through this module:

1. **No business logic may read a row.** Deployability, approval eligibility and
   the rest read the satellite. Rows are allowed to be stale.
2. **The list is reconstructable.** `rebuild_affiliations()` must be able to
   throw every row away and rebuild from live satellites without losing
   anything. If a rebuild would lose information, the row has wrongly become a
   source of truth.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from onerc_core.onerc_core.doctype.red_profile_affiliation.red_profile_affiliation import (
	SATELLITE_OWNED_FIELDS,
	allowed_statuses,
)

# Satellite apps register their providers under this hook. See
# rebuild_affiliations() for the contract.
AFFILIATION_PROVIDER_HOOK = "onerc_affiliation_providers"

_CLAIM_FIELDS = ("affiliation_type", *SATELLITE_OWNED_FIELDS)


def set_affiliation(
	profile: str,
	affiliation_type: str,
	status: str,
	reference_doctype: str,
	reference_name: str,
	start_date: str | None = None,
	end_date: str | None = None,
) -> str:
	"""Write or update one satellite's row on a profile's affiliation index.

	The single controlled entry point. Satellites call this; nothing writes the
	child table directly.

	Idempotent: called twice with the same values, the second call does not
	touch the database — no save, no version row, no `modified` bump.

	Returns the affiliation row's docname.
	"""
	claim = _validated_claim(
		{
			"affiliation_type": affiliation_type,
			"status": status,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"start_date": start_date,
			"end_date": end_date,
		},
		source=_("set_affiliation()"),
	)

	profile_doc = frappe.get_doc("Red Profile", profile)
	row, changed = _upsert(profile_doc, claim)

	if changed:
		_save(profile_doc)

	return row.name


def rebuild_affiliations(profile: str) -> dict:
	"""Regenerate a profile's affiliation index from its live satellites.

	The safety net for Design 2 — and the reason core never needs to trust the
	index it stores.

	**How core discovers what to rebuild from.** It does not import satellites:
	they live in apps core must not depend on, and today in apps that do not
	exist yet. Discovery is inverted. Each satellite app registers a provider in
	its own `hooks.py`::

	    onerc_affiliation_providers = ["vmmsx.volunteer.affiliations.provide"]

	A provider is called with a Red Profile docname and returns::

	    {
	        "reference_doctypes": ["Volunteer"],
	        "affiliations": [
	            {
	                "affiliation_type": "volunteer",
	                "status": "Active",
	                "reference_doctype": "Volunteer",
	                "reference_name": "VOL-00042",
	                "start_date": "2026-01-04",  # optional
	                "end_date": None,  # optional
	            },
	        ],
	    }

	`reference_doctypes` is the provider's **declared ownership** — the satellite
	doctypes it speaks for, whether or not it has anything to say about this
	particular profile. That declaration is what makes removal safe. A row is
	deleted only when a registered provider owns its `reference_doctype` and did
	not claim it: that combination is the one case where core *knows* the
	satellite is gone. Rows owned by no registered provider are reported and
	left strictly alone.

	**With no satellites installed** that rule needs no special case: no
	providers means no declared ownership, which means nothing is eligible for
	removal, so the rebuild is a read-only no-op that reports what it found.
	Core installed on its own can never wipe an index it has no way to rebuild.

	**Collect, then apply.** Every provider is called and every claim validated
	before the document is touched. A provider that raises, or returns a
	malformed declaration, aborts the rebuild having changed nothing — a partial
	view of the satellites is not something core can reconcile against.

	Returns a summary::

	    {
	        "providers": 2,  # providers consulted
	        "owned_doctypes": [...],  # declared ownership, union
	        "claimed": 3,  # claims received
	        "written": 1,  # rows added or changed
	        "removed": 1,  # rows whose satellite is gone
	        "unclaimed": [...],  # rows owned by nobody — left alone
	        "changed": True,  # whether the profile was saved
	    }
	"""
	profile_doc = frappe.get_doc("Red Profile", profile)
	providers, owned, claims = _collect(profile)

	surviving, removed, unclaimed = _reconcile(profile_doc.affiliations, owned, claims)

	if removed:
		profile_doc.set("affiliations", [row.as_dict() for row in surviving])

	written = 0
	for claim in claims:
		_, changed = _upsert(profile_doc, claim)
		written += int(changed)

	changed = bool(removed or written)
	if changed:
		_save(profile_doc)

	return {
		"providers": len(providers),
		"owned_doctypes": sorted(owned),
		"claimed": len(claims),
		"written": written,
		"removed": len(removed),
		"unclaimed": unclaimed,
		"changed": changed,
	}


def _collect(profile: str) -> tuple[list[str], set[str], list[dict]]:
	"""Call every registered provider and validate everything it returned."""
	providers = list(frappe.get_hooks(AFFILIATION_PROVIDER_HOOK))
	owned: set[str] = set()
	claims: list[dict] = []
	claimed_by: dict[str, str] = {}

	for path in providers:
		declaration = _declaration(path, profile)
		declared = {str(doctype) for doctype in declaration.get("reference_doctypes") or []}
		owned |= declared

		for raw in declaration.get("affiliations") or []:
			claim = _validated_claim(raw, source=path)

			if claim["reference_doctype"] not in declared:
				frappe.throw(
					_(
						"Provider {0} claimed a {1} affiliation without declaring {1} in"
						" reference_doctypes. A provider may only speak for what it owns."
					).format(frappe.bold(path), frappe.bold(claim["reference_doctype"])),
					title=_("Undeclared Affiliation Claim"),
				)

			owner = claimed_by.get(claim["affiliation_type"])
			if owner:
				frappe.throw(
					_(
						"Providers {0} and {1} both claim affiliation type {2}. A profile holds one"
						" row per type, so exactly one provider may own it."
					).format(frappe.bold(owner), frappe.bold(path), frappe.bold(claim["affiliation_type"])),
					title=_("Conflicting Affiliation Claims"),
				)

			claimed_by[claim["affiliation_type"]] = path
			claims.append(claim)

	return providers, owned, claims


def _declaration(path: str, profile: str) -> dict:
	"""Resolve one provider and call it, failing with the path in the message."""
	try:
		provider = frappe.get_attr(path)
	except Exception as exc:
		frappe.throw(
			_("Affiliation provider {0} could not be resolved: {1}. Check the {2} hook.").format(
				frappe.bold(path), exc, frappe.bold(AFFILIATION_PROVIDER_HOOK)
			),
			title=_("Bad Affiliation Provider"),
		)

	declaration = provider(profile)

	if not isinstance(declaration, dict) or "reference_doctypes" not in declaration:
		frappe.throw(
			_(
				"Affiliation provider {0} must return a dict with keys reference_doctypes and"
				" affiliations. Got {1}."
			).format(frappe.bold(path), frappe.bold(type(declaration).__name__)),
			title=_("Bad Affiliation Provider"),
		)

	return declaration


def _reconcile(rows, owned: set[str], claims: list[dict]) -> tuple[list, list, list[str]]:
	"""Split the current rows into survivors and casualties.

	A row dies only when a registered provider owns its `reference_doctype` and
	did not claim it. Everything else survives — including rows nobody owns,
	which are reported instead, because "the owning app is not installed right
	now" and "the satellite was deleted" are not distinguishable from here.
	"""
	claimed = {
		(claim["affiliation_type"], claim["reference_doctype"], claim["reference_name"]) for claim in claims
	}

	surviving, removed, unclaimed = [], [], []

	for row in rows:
		if row.reference_doctype not in owned:
			unclaimed.append(row.affiliation_type)
			surviving.append(row)
		elif (row.affiliation_type, row.reference_doctype, row.reference_name) in claimed:
			surviving.append(row)
		else:
			removed.append(row)

	return surviving, removed, unclaimed


def _upsert(profile_doc, claim: dict) -> tuple[object, bool]:
	"""Apply one claim in memory. Returns the row and whether anything changed."""
	existing = [row for row in profile_doc.affiliations if row.affiliation_type == claim["affiliation_type"]]

	if len(existing) > 1:
		frappe.throw(
			_(
				"{0} holds {1} rows for affiliation type {2}. A profile holds one row per type; this"
				" index was written outside set_affiliation()."
			).format(frappe.bold(profile_doc.name), len(existing), frappe.bold(claim["affiliation_type"])),
			title=_("Duplicate Affiliation Rows"),
		)

	if not existing:
		return profile_doc.append("affiliations", claim), True

	row = existing[0]
	changed = False

	for field in SATELLITE_OWNED_FIELDS:
		if _comparable(row.get(field)) != _comparable(claim.get(field)):
			row.set(field, claim.get(field))
			changed = True

	return row, changed


def _validated_claim(raw: dict, source: str) -> dict:
	"""Normalise and check one claim, naming `source` in any complaint."""
	claim = {field: raw.get(field) for field in _CLAIM_FIELDS}

	for field in ("affiliation_type", "status", "reference_doctype", "reference_name"):
		if not claim.get(field):
			frappe.throw(
				_("{0} is required on an affiliation claim from {1}.").format(
					frappe.bold(field), frappe.bold(source)
				),
				frappe.MandatoryError,
				title=_("Incomplete Affiliation Claim"),
			)

	if not frappe.db.exists("Affiliation Type", claim["affiliation_type"]):
		frappe.throw(
			_("Affiliation Type {0} does not exist (claimed by {1}).").format(
				frappe.bold(claim["affiliation_type"]), frappe.bold(source)
			),
			frappe.DoesNotExistError,
			title=_("Unknown Affiliation Type"),
		)

	statuses = allowed_statuses()
	if claim["status"] not in statuses:
		frappe.throw(
			_("{0} is not an affiliation status. Expected one of: {1}.").format(
				frappe.bold(claim["status"]), ", ".join(statuses)
			),
			title=_("Unknown Affiliation Status"),
		)

	if not frappe.db.exists("DocType", claim["reference_doctype"]):
		frappe.throw(
			_("{0} is not a doctype, so it cannot own an affiliation (claimed by {1}).").format(
				frappe.bold(claim["reference_doctype"]), frappe.bold(source)
			),
			frappe.DoesNotExistError,
			title=_("Unknown Satellite Doctype"),
		)

	if not frappe.db.exists(claim["reference_doctype"], claim["reference_name"]):
		frappe.throw(
			_("{0} {1} does not exist, so it cannot be the source of an affiliation.").format(
				claim["reference_doctype"], frappe.bold(claim["reference_name"])
			),
			frappe.DoesNotExistError,
			title=_("Missing Satellite Record"),
		)

	if (
		claim["start_date"]
		and claim["end_date"]
		and getdate(claim["end_date"]) < getdate(claim["start_date"])
	):
		frappe.throw(
			_("An affiliation cannot end ({0}) before it starts ({1}).").format(
				frappe.bold(claim["end_date"]), frappe.bold(claim["start_date"])
			),
			title=_("Invalid Affiliation Dates"),
		)

	return claim


def _save(profile_doc) -> None:
	"""Persist a service-authored change to the index.

	The flag is how RedProfile.validate() tells a service write from a direct
	one. Permissions are deliberately *not* ignored: a satellite that must write
	on behalf of an unprivileged user should arrange for that explicitly rather
	than have core quietly bypass the check for every caller.
	"""
	profile_doc.flags.affiliations_from_service = True

	try:
		profile_doc.save()
	finally:
		profile_doc.flags.affiliations_from_service = False


def _comparable(value) -> str:
	"""Flatten a field value for comparison — dates arrive as both str and date."""
	return "" if value is None else str(value)
