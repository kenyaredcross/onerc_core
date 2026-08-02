# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Geo scope — *where* a user may exercise a role.

Frappe Roles answer what a user may do. This service answers where, by reading
Geo Assignment: a role bound to a node in the geo tree, granting that node and
everything beneath it.

Three properties hold throughout, and the tests are written to break them:

1. **Fail closed.** No live assignment means an empty set, and an empty set
   means nothing is visible. Every enforcement layer treats "empty" as deny, so
   a user who was never granted anything is denied by construction rather than
   by a rule someone remembered to write.
2. **The role argument is load-bearing.** "Where may I approve volunteers" and
   "where may I view members" are different questions with different answers.
   Scope is never cached or passed around without the role that produced it.
3. **One source of truth.** Scope and approver routing both read Geo Assignment
   through the liveness rule in its controller, so they cannot disagree about
   who holds what, where.

Subtree expansion goes through the geo adapter's nested-set queries — no
recursion, and no direct Geo Node access even from inside core.
"""

import frappe
from frappe.utils import getdate, today

from onerc_core.geo.services import adapter
from onerc_core.onerc_core.doctype.geo_assignment.geo_assignment import LIVE_SQL

# The bypass, stated explicitly rather than left implicit in a permission check.
#
# CLAUDE.md forbids hardcoded role names, and this is the deliberate exception:
# "System Manager" is a Frappe framework primitive, not a society role. The rule
# exists so that society-specific roles — Volunteer Approver, Branch Coordinator
# — stay configurable per national society. Those never appear in this module;
# they arrive as the `role` argument. Anything a society names is config.
UNRESTRICTED_ROLES = ("System Manager",)


def has_unrestricted_scope(user: str | None = None) -> bool:
	"""May this user act everywhere, regardless of Geo Assignment?

	Kept as its own predicate so the enforcement layers can skip filtering
	entirely instead of building an `IN` clause over every node in the country.
	Being a separate function is also what makes the bypass testable in
	isolation — an implicit bypass buried in a permission check is not.
	"""
	user = user or frappe.session.user

	if user == "Administrator":
		return True

	return bool(set(UNRESTRICTED_ROLES) & set(frappe.get_roles(user)))


def get_user_geo_scope(user: str | None, role: str, on_date: str | None = None) -> set[str]:
	"""The geo nodes `user` may act on when exercising `role`.

	Each live assignment contributes its node plus every descendant; the results
	are unioned. ACC-01 falls out of that union: assignments at two unrelated
	counties yield both subtrees and nothing between them, because a union of
	two disjoint subtrees cannot reach a sibling of either.

	Returns an empty set when nothing is granted — the caller must treat that as
	"sees nothing", never as "unfiltered".
	"""
	if has_unrestricted_scope(user):
		return _every_node()

	scope: set[str] = set()

	for node in live_assignment_nodes(user, role, on_date):
		scope.add(node)
		scope.update(_descendants(node))

	return scope


def live_assignment_nodes(user: str | None, role: str, on_date: str | None = None) -> list[str]:
	"""Distinct nodes where `user` holds a live assignment for `role`.

	The one place a live assignment is looked up by user and role. Liveness is
	`LIVE_SQL` from the Geo Assignment controller — this module does not restate
	`is_active = 1 AND ...`, so the query path and `is_live()` cannot drift.
	"""
	user = user or frappe.session.user

	if not (user and role):
		return []

	return frappe.db.sql(
		f"""
		SELECT DISTINCT assignment.geo_node
		FROM `tabGeo Assignment` assignment
		WHERE assignment.user = %(user)s
			AND assignment.role = %(role)s
			AND {LIVE_SQL}
		""",
		{"user": user, "role": role, "on_date": getdate(on_date or today())},
		pluck=True,
	)


def holders_at(node: str, role: str, on_date: str | None = None) -> list[str]:
	"""Users holding a live assignment for `role` at exactly this node.

	Exactly this node — not its subtree. Approver routing walks upward one node
	at a time and asks this question at each step, which is what makes "nearest
	ancestor" mean nearest rather than "anyone above".
	"""
	if not (node and role):
		return []

	return frappe.db.sql(
		f"""
		SELECT DISTINCT assignment.user
		FROM `tabGeo Assignment` assignment
		WHERE assignment.geo_node = %(node)s
			AND assignment.role = %(role)s
			AND {LIVE_SQL}
		ORDER BY assignment.user ASC
		""",
		{"node": node, "role": role, "on_date": getdate(on_date or today())},
		pluck=True,
	)


def _descendants(node: str) -> list[str]:
	"""Subtree of a node, or nothing if the node has gone missing.

	A Geo Assignment holds a Link to Geo Node, so the framework will not let the
	node be deleted while an assignment points at it and this should not happen.
	If it somehow does, the row grants nothing rather than raising: these
	functions run inside `get_permission_query_conditions`, where an exception
	would break every list view on the site. Failing closed means granting
	nothing, not crashing.
	"""
	try:
		return adapter.get_descendants(node)
	except frappe.DoesNotExistError:
		frappe.log_error(
			title="Geo Assignment points at a missing Geo Node",
			message=f"Geo Node {node} does not exist; the assignments naming it granted no scope.",
		)
		return []


def _every_node() -> set[str]:
	"""Every node in the tree, for the unrestricted bypass.

	Built from the adapter's roots plus their subtrees rather than a direct
	`tabGeo Node` read, so this module holds no Geo Node query of its own.
	"""
	nodes: set[str] = set()

	for root in adapter.get_root_regions():
		nodes.add(root["name"])
		nodes.update(_descendants(root["name"]))

	return nodes
