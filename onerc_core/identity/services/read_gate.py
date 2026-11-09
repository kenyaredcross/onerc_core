# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Read gating for affiliation rows.

An Affiliation Type may set `requires_gated_read`. The thing being protected is
not the detail of the affiliation but its *existence*: that someone appears in
the register as a beneficiary is itself sensitive. So gated rows are removed
from the document before it reaches a reader who lacks the type's gating
capability — server-side, on the read path, never by hiding a grid in the UI.

**Capabilities are not built in this app.** A capability is what a user is
allowed to *do*; affiliation is what a person *is*. Whichever app owns
capabilities registers a resolver in its `hooks.py`::

    onerc_capability_resolver = "some_app.capabilities.has_capability"

... where `resolver(user, capability) -> bool`.

**With no resolver installed, every gated row is hidden — from everyone,
Administrator included.** Nothing can prove a reader holds a capability when
nothing implements capabilities, and a gate that fails open is not a gate.
Installing a resolver is what opens it.
"""

import frappe
from frappe import _

CAPABILITY_RESOLVER_HOOK = "onerc_capability_resolver"


def apply(profile_doc, user: str | None = None) -> None:
	"""Strip gated rows from a profile document in place.

	Called from `RedProfile.onload()`, so the desk form and every API that
	returns a whole document go through it.
	"""
	rows = profile_doc.get("affiliations") or []

	if not rows:
		return

	visible = [row for row in rows if is_visible(row.affiliation_type, user)]

	if len(visible) == len(rows):
		return

	profile_doc.set("affiliations", [row.as_dict() for row in visible])


def get_affiliations(profile, user: str | None = None) -> list[dict]:
	"""A profile's affiliation rows, gated ones removed.

	The supported read path for code. Pass a docname or a loaded document.

	`frappe.get_doc("Red Profile", ...)` does not gate anything — it is trusted
	server-side access. That is exactly why this function exists: any read that
	will reach a user goes through here.
	"""
	profile_doc = profile if hasattr(profile, "doctype") else frappe.get_doc("Red Profile", profile)

	return [
		row.as_dict()
		for row in (profile_doc.get("affiliations") or [])
		if is_visible(row.affiliation_type, user)
	]


def is_visible(affiliation_type: str, user: str | None = None) -> bool:
	"""May `user` know that an affiliation of this type exists?"""
	capability = gated_capabilities().get(affiliation_type)

	if not capability:
		return True

	return has_capability(capability, user)


def gated_capabilities() -> dict[str, str]:
	"""{affiliation type: capability that opens it}, for gated types only.

	A type with `requires_gated_read` and no capability cannot occur — the
	doctype refuses to save in that state — so anything listed here has a key.
	"""
	rows = frappe.get_all(
		"Affiliation Type",
		filters={"requires_gated_read": 1},
		fields=["name", "gating_capability"],
	)

	return {row.name: row.gating_capability for row in rows if row.gating_capability}


def has_capability(capability: str, user: str | None = None) -> bool:
	"""Ask the installed capability resolver. No resolver means no.

	Fails closed by construction: `frappe.get_hooks` returns an empty list when
	nothing registers the hook, and an empty list of resolvers cannot grant
	anything.
	"""
	resolver = _resolver()

	if resolver is None:
		return False

	return bool(resolver(user or frappe.session.user, capability))


def _resolver():
	"""The single registered capability resolver, or None."""
	paths = list(frappe.get_hooks(CAPABILITY_RESOLVER_HOOK))

	if not paths:
		return None

	if len(paths) > 1:
		# Two apps answering "may this user do X" differently is not something
		# core can arbitrate, and silently picking one would decide who sees
		# beneficiary rows by app install order.
		frappe.throw(
			_("More than one capability resolver is registered ({0}). Exactly one app may own {1}.").format(
				", ".join(paths), frappe.bold(CAPABILITY_RESOLVER_HOOK)
			),
			title=_("Ambiguous Capability Resolver"),
		)

	return frappe.get_attr(paths[0])
