# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""The three enforcement layers.

A scope set that nothing consults is documentation. These are the three places a
record can be reached, and all three answer from `get_user_geo_scope()`:

1. **Query filter** — `get_permission_query_conditions` injects a `WHERE ... IN`
   over the registered geo field. Scopes list views, reports, link searches and
   anything else built on the query engine.
2. **Document read** — `has_permission` checks one record's geo field against
   the scope set. This is what closes the hole the query filter cannot: a
   guessed docname, a bookmarked URL, an `frappe.client.get` call. Filtering a
   list is not access control if the detail view is reachable directly.
3. **API guard** — `guard()`, for custom whitelisted endpoints. An endpoint that
   assembles its own response never passes through the desk permission layer, so
   it needs somewhere explicit to make the same check.

**None of them re-implements the scope logic.** Each resolves the registration,
asks the scope service, and applies the answer in the shape its layer needs.
That is deliberate: three copies of "which nodes may this user see" would be
three chances to disagree, and the one that disagreed most permissively would
silently become the real policy.

Core registers both framework hooks under the `"*"` wildcard, so registering a
scopeable doctype takes exactly one declaration in the owning app — see
`registry`. The handlers return "no opinion" for any doctype nobody registered,
which is what keeps a site with no product apps completely unaffected.
"""

import frappe
from frappe import _

from onerc_core.access.services import registry, scope

# A condition that is false for every row. Returned when a user's scope is
# empty: the layer must express "matches nothing", and an empty string would
# mean "no filter" — the exact inversion of what an empty scope means.
DENY_ALL = "1=0"


def get_permission_query_conditions(user: str | None = None, doctype: str | None = None, **kwargs) -> str:
	"""SQL predicate restricting a list query to the user's scope.

	Frappe calls this as `fn(user, doctype=...)` for every doctype, because core
	registers it under `"*"`. Unregistered doctypes get an empty string, which
	the query builder treats as no condition at all.
	"""
	registration = registry.for_doctype(doctype)

	if not registration:
		return ""

	user = user or frappe.session.user

	if scope.has_unrestricted_scope(user):
		return ""

	field = registry.geo_node_field(doctype)
	role = registry.resolve_role(registration)

	if not role:
		# The registration names a role that cannot be resolved. `resolve_role`
		# has already logged it; fail closed rather than throw, because throwing
		# here would break every list view on the site instead of one doctype's.
		return DENY_ALL

	nodes = scope.get_user_geo_scope(user, role)

	if not nodes:
		return DENY_ALL

	allowed = ", ".join(frappe.db.escape(node) for node in sorted(nodes))

	# Rows with an empty geo field are excluded by `IN` and that is intended: an
	# unplaced record is not inside anybody's scope. The document layer below
	# reaches the same verdict, so the two layers agree about it.
	return f"`tab{doctype}`.`{field}` IN ({allowed})"


def has_permission(doc=None, ptype: str | None = None, user: str | None = None, **kwargs) -> bool:
	"""Is this one document inside the user's scope?

	Registered under `"*"`, so Frappe calls it for every document permission
	check. Controller hooks may only deny — never grant — which suits a layer
	whose whole job is to take access away from records elsewhere in the tree.
	"""
	if doc is None or not getattr(doc, "doctype", None):
		return True

	registration = registry.for_doctype(doc.doctype)

	if not registration:
		return True

	field = registry.geo_node_field(doc.doctype)

	return is_in_scope(doc.doctype, doc.get(field), user)


def is_in_scope(doctype: str, geo_node: str | None, user: str | None = None) -> bool:
	"""The shared verdict: may `user` reach a record of `doctype` at `geo_node`?

	Used by the document layer and the API guard so the two cannot drift. Returns
	True for an unregistered doctype — this layer has no opinion about doctypes
	nobody declared, and must not start denying them.
	"""
	registration = registry.for_doctype(doctype)

	if not registration:
		return True

	user = user or frappe.session.user

	if scope.has_unrestricted_scope(user):
		return True

	if not geo_node:
		return False

	role = registry.resolve_role(registration)

	if not role:
		# Logged by `resolve_role`. Denying is the only safe answer: an
		# unresolvable role means nobody's authority over this doctype can be
		# established, and granting on "we could not tell" is how a scope layer
		# becomes decorative.
		return False

	return geo_node in scope.get_user_geo_scope(user, role)


def guard(doctype: str, name: str, user: str | None = None) -> None:
	"""Raise `frappe.PermissionError` unless the record is in the user's scope.

	What a custom endpoint calls before returning anything about a record.

	The geo field is read with `frappe.db.get_value` rather than `get_doc`: this
	runs *inside* the access check, so loading the document through the
	permission layer would re-enter it.

	A record that does not exist is refused as a permission error rather than a
	missing-document error, deliberately. Distinguishing the two would let a
	caller outside the scope map the tree by watching which names answer
	differently.
	"""
	registration = registry.for_doctype(doctype)

	if not registration:
		return

	field = registry.geo_node_field(doctype)
	geo_node = frappe.db.get_value(doctype, name, field) if name else None

	if is_in_scope(doctype, geo_node, user):
		return

	# The resolved role, so the message names the role the society actually
	# configured rather than the settings fieldname holding it. An unresolvable
	# role has already been logged by `is_in_scope`; the refusal still stands
	# and says as much rather than naming a role that does not exist.
	role = registry.resolve_role(registration)

	if not role:
		frappe.throw(
			_(
				"You are not permitted to act on {0} {1}. The role that scopes {0} is not"
				" configured, so nobody's area can be established — ask an administrator to set it"
				" in National Society Settings."
			).format(doctype, frappe.bold(name)),
			frappe.PermissionError,
			title=_("Scope Role Not Configured"),
		)

	frappe.throw(
		_("You are not permitted to act on {0} {1} — it is outside the area you hold {2} in.").format(
			doctype, frappe.bold(name), frappe.bold(role)
		),
		frappe.PermissionError,
		title=_("Outside Your Area"),
	)
