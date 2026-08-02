# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Which doctypes are geo-scoped — declared by the apps that own them.

Core provides the scoping engine. It must not know that a Volunteer exists:
Volunteer lives in a product app that core may not import and, today, may not
even be installed. So discovery is inverted, the same way affiliation providers
and the capability resolver are. Each app declares its own scopeable doctypes in
its `hooks.py`::

    onerc_scopeable_doctypes = [
        {
            "doctype": "Volunteer",
            "geo_node_field": "home_geo_node",
            "role": "Volunteer Approver",
        },
    ]

Read that as: *scope my Volunteer doctype on its home_geo_node field, for the
Volunteer Approver role.* Core reads the declaration and generates the
enforcement from it; it never names Volunteer, and nothing here imports the app
that did.

**With nothing registered the engine is inert.** `frappe.get_hooks` returns an
empty list, no doctype is scoped, and the enforcement layers hand back "no
opinion" — core standalone behaves exactly as if this layer did not exist.
That is a tested property, not an incidental one.
"""

import frappe
from frappe import _

SCOPEABLE_DOCTYPE_HOOK = "onerc_scopeable_doctypes"

REQUIRED_KEYS = ("doctype", "geo_node_field", "role")


def registrations() -> dict[str, dict]:
	"""Every declared scopeable doctype, keyed by doctype name.

	Structure is validated here; the existence of the doctype and its field is
	not. That check belongs at the point of use, where the doctype is being
	queried and therefore certainly exists — validating it here would make a
	registration for a not-yet-migrated doctype break `bench migrate`.
	"""
	declared: dict[str, dict] = {}

	for raw in frappe.get_hooks(SCOPEABLE_DOCTYPE_HOOK) or []:
		entry = _validated(raw)
		doctype = entry["doctype"]

		if doctype in declared:
			# Two apps scoping one doctype differently is not something core can
			# arbitrate, and picking one would make a security boundary depend on
			# app install order.
			frappe.throw(
				_(
					"{0} is registered as scopeable more than once. Exactly one app may declare"
					" the geo field and role for a doctype."
				).format(frappe.bold(doctype)),
				title=_("Conflicting Scope Registration"),
			)

		declared[doctype] = entry

	return declared


def for_doctype(doctype: str) -> dict | None:
	"""The registration governing a doctype, or None if it is not scoped.

	None means "this layer has no opinion" — the caller must not read it as
	"denied". An unregistered doctype is simply not geo-scoped.
	"""
	if not doctype:
		return None

	return registrations().get(doctype)


def scoped_doctypes() -> list[str]:
	"""Names of the registered scopeable doctypes, sorted."""
	return sorted(registrations())


def geo_node_field(doctype: str) -> str:
	"""The registered geo field, checked against the doctype's actual meta.

	A registration naming a field that does not exist is a misconfiguration of
	the security layer, and it throws rather than degrading. The alternatives are
	worse: silently skipping the filter would leak every record of the doctype to
	every user, and silently denying everything would look like a data problem
	instead of the wiring mistake it is.
	"""
	registration = for_doctype(doctype)

	if not registration:
		frappe.throw(
			_("{0} is not registered as a scopeable doctype.").format(frappe.bold(doctype)),
			title=_("Doctype Not Scopeable"),
		)

	field = registration["geo_node_field"]

	if not frappe.get_meta(doctype).get_field(field):
		frappe.throw(
			_(
				"{0} is registered as scopeable on field {1}, which {0} does not have. Fix the"
				" {2} entry in the app that declared it."
			).format(frappe.bold(doctype), frappe.bold(field), frappe.bold(SCOPEABLE_DOCTYPE_HOOK)),
			title=_("Bad Scope Registration"),
		)

	return field


def _validated(raw) -> dict:
	"""Check one declaration's shape, naming what is wrong with it."""
	if not isinstance(raw, dict):
		frappe.throw(
			_("A {0} entry must be a dict with keys {1}. Got {2}.").format(
				frappe.bold(SCOPEABLE_DOCTYPE_HOOK), ", ".join(REQUIRED_KEYS), frappe.bold(type(raw).__name__)
			),
			title=_("Bad Scope Registration"),
		)

	missing = [key for key in REQUIRED_KEYS if not raw.get(key)]

	if missing:
		frappe.throw(
			_("A {0} entry is missing {1}. Every entry needs {2}.").format(
				frappe.bold(SCOPEABLE_DOCTYPE_HOOK), ", ".join(missing), ", ".join(REQUIRED_KEYS)
			),
			frappe.MandatoryError,
			title=_("Incomplete Scope Registration"),
		)

	return {key: str(raw[key]) for key in REQUIRED_KEYS}
