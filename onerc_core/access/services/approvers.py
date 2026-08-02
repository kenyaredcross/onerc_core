# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Approver routing — *who* can approve at a place in the geo tree.

This is the second reader of Geo Assignment, and it reads it through the same
helpers as the scope service. That is the whole point of routing and read scope
sharing one source of truth: the user who appears in `resolve_approvers()` for a
ward is, necessarily, a user whose `get_user_geo_scope()` covers that ward. They
are two questions answered from one table, so they cannot disagree.

**What this module does not decide.** How many approvers must act, in what
order, whether one may delegate, what happens on rejection — none of that is
here. That is the approval engine, and it lives in the product app. This
function answers exactly one question: who can approve here.
"""

import frappe
from frappe import _

from onerc_core.access.services import scope
from onerc_core.geo.services import adapter

RULE_NEAREST_ANCESTOR = "nearest_ancestor"
RULE_AT_LEVEL = "at_level"
RULES = (RULE_NEAREST_ANCESTOR, RULE_AT_LEVEL)


def resolve_approvers(
	geo_node: str,
	role: str,
	rule: str = RULE_NEAREST_ANCESTOR,
	geo_level: str | None = None,
	on_date: str | None = None,
) -> list[str]:
	"""Users who can approve at `geo_node` for `role`.

	`rule="nearest_ancestor"` (the default) walks from the node upward and stops
	at the first node — the node itself counts — where anybody holds a live
	assignment for the role, returning the holders there. Authority granted high
	in the tree therefore covers everything below it without needing a row per
	ward, and a nearer holder always wins over a more distant one.

	`rule="at_level"` ignores nearness and resolves at a named Geo Level: it
	finds the node at that level in the chain and returns its holders. Use it
	when a decision belongs to a tier by policy — "county approves, always" —
	rather than to whoever happens to be nearest.

	Returns an empty list when nothing resolves all the way to the root, or when
	the named level holds nobody. **The caller decides what an unresolvable
	approval means** — core will not invent a fallback approver, because every
	sensible fallback is a product policy.
	"""
	if rule not in RULES:
		frappe.throw(
			_("{0} is not an approver routing rule. Expected one of: {1}.").format(
				frappe.bold(rule), ", ".join(RULES)
			),
			title=_("Unknown Routing Rule"),
		)

	if not (geo_node and role):
		return []

	if rule == RULE_AT_LEVEL:
		return _at_level(geo_node, role, geo_level, on_date)

	return _nearest_ancestor(geo_node, role, on_date)


def _nearest_ancestor(geo_node: str, role: str, on_date: str | None) -> list[str]:
	"""First node upward that has holders, then those holders.

	`resolve_upward` is the adapter's generic "walk up until X" — the same
	primitive the geo layer exposes for exactly this shape of problem. Results
	are memoised because the predicate and the return both need the holders of
	the node that matched, and asking twice would double the queries.
	"""
	found: dict[str, list[str]] = {}

	def has_holders(candidate: str) -> bool:
		found[candidate] = scope.holders_at(candidate, role, on_date)

		return bool(found[candidate])

	match = adapter.resolve_upward(geo_node, has_holders)

	return found.get(match, []) if match else []


def _at_level(geo_node: str, role: str, geo_level: str | None, on_date: str | None) -> list[str]:
	"""Holders at the node sitting at `geo_level`, in this node's chain."""
	if not geo_level:
		frappe.throw(
			_("Routing rule {0} needs a Geo Level to resolve at.").format(frappe.bold(RULE_AT_LEVEL)),
			frappe.MandatoryError,
			title=_("Missing Geo Level"),
		)

	def is_at_level(candidate: str) -> bool:
		return adapter.get_level(candidate)["key"] == geo_level

	match = adapter.resolve_upward(geo_node, is_at_level)

	# No node in the chain sits at that level — the level is below this node, or
	# not part of this branch at all. Nobody to return, and not an error: asking
	# "who approves at county level" about a record that has no county is a fair
	# question with an empty answer.
	if not match:
		return []

	return scope.holders_at(match, role, on_date)
