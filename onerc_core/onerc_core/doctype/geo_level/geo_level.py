# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Geo Level — the ladder a society names, and the guard rails around entering it.

**`geo_level_order` is presentation and a data-entry guard. It is not
structure.** Nothing in this file, and nothing downstream of it, may make
ancestry, nearness, routing or scope depend on it. Those read the tree:
`adapter.get_ancestors` orders by `lft` descending, `resolve_upward` walks that
list, `matches_scope` compares nested-set bounds, and `get_root_regions` finds
parentless nodes rather than order 1. The order exists so that a form can lay a
ladder out top-down, and so that a human entering one is told when they have
contradicted themselves.

That distinction decides the shape of every rule below. **The only hard refusals
here are the ones that cannot mean anything else**: a top-of-ladder level cannot
require a parent. Everything else — a reused order, a lowest marker that is not
the deepest rung — is a *warning*, because each has a legitimate reading:

* **A reused order is legal.** Two societies on one site each number their own
  ladder from 1, and the test suites build exactly that shape on purpose, to
  prove the engine holds no opinion about a society's hierarchy. A site-wide
  unique order would forbid it. So a collision is reported, with the two levels
  named, and the save goes through.
* **A lowest marker that is not the deepest rung** may simply mean a society has
  stopped registering records at its deepest tier without retiring the level.

**The lowest marker moves rather than blocks.** Marking a level lowest used to
throw when another already carried the flag, so adding a deeper tier meant
finding and clearing the incumbent by hand before the new row would save at all.
It now takes the marker: the previous holder is unset in the same transaction,
and at-most-one-active-lowest holds afterwards as a *result* rather than as a
refusal. Inactive levels are still exempt, and still ignored.

**There is no `is_highest` field and there will not be one.** The top is derived
— `adapter.top_levels()` and `adapter.is_top_level()` — and handed to the form
through `onload`. A stored flag would be a third answer to "where does the
hierarchy begin", alongside the order and the parentage rule, and the day two of
them disagreed nobody could say which was right.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from onerc_core.geo.services import adapter

TOP_LEVEL_ORDER = 1

DOCTYPE = "Geo Level"


class GeoLevel(Document):
	def onload(self):
		"""Hand the form the derived ladder, so it can show the top without a flag."""
		self.set_onload("hierarchy", adapter.hierarchy_overview())

	def before_insert(self):
		self.suggest_order()

	def validate(self):
		self.validate_top_level_has_no_parent()
		self.warn_on_duplicate_order()
		self.warn_if_lowest_is_not_the_deepest()

	def before_save(self):
		self.take_the_lowest_marker()

	# --- the order --------------------------------------------------------

	def suggest_order(self):
		"""Fill a blank order with the next rung down. A default, never a rule.

		The common case is a society adding one level at a time to a ladder it is
		building top-down, and making somebody count the existing rows and type a
		number is how two levels end up sharing one.

		**It only ever fills a blank.** An explicit order is left exactly as
		given, which is what keeps every fixture that numbers its own ladder
		working, and what lets a society insert a tier between two others.

		Zero counts as blank: the field's own guidance is to start from 1, so
		there is no rung 0 anybody could have meant.
		"""
		if cint(self.geo_level_order) > 0:
			return

		self.geo_level_order = next_available_order()

	def warn_on_duplicate_order(self):
		"""Say so when another active level is already on this rung. Never block.

		**Why this is a message and not a refusal.** A duplicated order is
		ambiguous rather than wrong: on a single-society site it is almost
		certainly a slip, and on a site carrying two societies it is the expected
		shape, because each numbers its own ladder from 1. Refusing it would
		forbid the second society outright.

		So the message says which reading applies, where that can be established
		cheaply. Two levels are in the same hierarchy when a node at one and a
		node at the other sit under a common root — a fact about the tree, which
		is the only thing here entitled to settle a structural question. A
		brand-new level has no nodes yet, so the answer is usually "cannot tell",
		and the wording says that rather than guessing.
		"""
		if not (self.is_active and cint(self.geo_level_order) > 0):
			return

		clashes = frappe.get_all(
			DOCTYPE,
			filters={
				"name": ("!=", self.name),
				"is_active": 1,
				"geo_level_order": cint(self.geo_level_order),
			},
			pluck="name",
		)

		if not clashes:
			return

		shared = [other for other in clashes if shares_a_hierarchy(self.name, other)]

		if shared:
			message = _(
				"{0} is already at order {1}, in the same hierarchy as this level. Two rungs with"
				" the same number cannot be laid out in sequence, and a Geo Node at one of them"
				" cannot be filed under a node at the other. Saved anyway, because the tree is what"
				" decides structure, but this wants correcting."
			).format(", ".join(frappe.bold(other) for other in shared), frappe.bold(self.geo_level_order))
		else:
			message = _(
				"{0} is also at order {1}. If they belong to different hierarchies that is expected"
				" and nothing is wrong. If they belong to the same one, give this level its own"
				" number: the two cannot be laid out in sequence, and a Geo Node at one cannot be"
				" filed under a node at the other."
			).format(", ".join(frappe.bold(other) for other in clashes), frappe.bold(self.geo_level_order))

		frappe.msgprint(message, title=_("Order Already In Use"), indicator="orange")

	def validate_top_level_has_no_parent(self):
		"""The level at the top of the hierarchy cannot require a parent.

		The one order-based rule that refuses, because it is a contradiction
		rather than an ambiguity: a rung numbered as the first cannot also demand
		something above it.
		"""
		if cint(self.geo_level_order) == TOP_LEVEL_ORDER and self.requires_parent:
			frappe.throw(
				_("The level at order {0} is the top of the hierarchy and cannot have {1} set.").format(
					frappe.bold(TOP_LEVEL_ORDER), frappe.bold(_("Requires Parent"))
				),
				title=_("Invalid Top Level"),
			)

	# --- the lowest marker ------------------------------------------------

	def take_the_lowest_marker(self):
		"""Become the lowest active level, unseating whoever held it. Idempotent.

		**It moves the marker; it does not refuse.** Before this, a society
		adding a deeper tier and marking it lowest was told that another level
		already was, and had to go and clear that one by hand before the new row
		would save. Adding a rung is the ordinary way a hierarchy grows, and the
		software should follow that intent rather than object to it.

		At-most-one-active-lowest still holds — it is now the *result* of this
		method rather than a rule enforced by throwing. Inactive levels are exempt
		on both sides: they neither claim the marker nor lose it, so a retired
		tier keeps its flag and does not fight the live one.

		In `before_save`, so the incumbent is cleared before this row is written
		and there is never an instant, even inside the transaction, when two
		active levels carry the flag.

		`db.set_value` rather than a full save: the incumbent is losing a flag it
		no longer qualifies for, and re-running its own validation would only
		re-warn about things nobody changed.
		"""
		if not (self.is_active and self.is_lowest_level):
			return

		incumbents = frappe.get_all(
			DOCTYPE,
			filters={"name": ("!=", self.name), "is_active": 1, "is_lowest_level": 1},
			pluck="name",
		)

		if not incumbents:
			return

		for previous in incumbents:
			frappe.db.set_value(DOCTYPE, previous, "is_lowest_level", 0)
			frappe.clear_document_cache(DOCTYPE, previous)

		frappe.msgprint(
			_("{0} is no longer the lowest level. {1} is.").format(
				", ".join(frappe.bold(previous) for previous in incumbents), frappe.bold(self.name)
			),
			title=_("Lowest Level Moved"),
			indicator="blue",
		)

	def warn_if_lowest_is_not_the_deepest(self):
		"""Flag a lowest marker sitting above a deeper rung. Never block.

		Order is guidance, so a mismatch is a question rather than an error: a
		society may have stopped registering records at its deepest tier without
		retiring the level. Worth saying out loud all the same, because the usual
		cause is the marker having been put on the wrong row.
		"""
		if not (self.is_active and self.is_lowest_level and cint(self.geo_level_order) > 0):
			return

		deeper = frappe.get_all(
			DOCTYPE,
			filters={
				"name": ("!=", self.name),
				"is_active": 1,
				"geo_level_order": (">", cint(self.geo_level_order)),
			},
			pluck="name",
		)

		if not deeper:
			return

		frappe.msgprint(
			_(
				"{0} sits below this level in the ladder, so this is not the deepest rung. That is"
				" allowed, and it is worth checking: the lowest level is normally the last one a"
				" society still registers records at."
			).format(", ".join(frappe.bold(other) for other in deeper)),
			title=_("Lowest Is Not The Deepest"),
			indicator="orange",
		)


# --- module-level helpers -------------------------------------------------


@frappe.whitelist()
def next_available_order() -> int:
	"""The rung below the deepest active level, or 1 on an empty ladder.

	Whitelisted so the desk form can pre-fill a new level rather than leaving
	somebody to count the rows themselves. Gated on create permission for Geo
	Level: it is a small disclosure, but it is a disclosure about a society's
	configuration, and there is no reason for anybody who cannot add a level to
	be asking.

	Inactive levels are ignored, so retiring a tier frees its number.
	"""
	frappe.has_permission(DOCTYPE, ptype="create", throw=True)

	deepest = frappe.db.sql(
		"""
		SELECT MAX(geo_level_order)
		FROM `tabGeo Level`
		WHERE is_active = 1
		"""
	)[0][0]

	return cint(deepest) + 1


def shares_a_hierarchy(level: str, other: str) -> bool:
	"""Do these two levels have nodes in the same tree?

	Asked of the tree and nothing else: a node at each, both enclosed by one
	parentless root. Nested-set containment, so it costs one query and no
	recursion.

	False when either level has no nodes yet, which is the ordinary case while a
	society is still writing its ladder down. It means "cannot tell", and the
	caller words its message accordingly rather than treating it as "no".
	"""
	if not (level and other):
		return False

	return bool(
		frappe.db.sql(
			"""
			SELECT 1
			FROM `tabGeo Node` mine
			INNER JOIN `tabGeo Node` theirs ON theirs.geo_level = %(other)s
			INNER JOIN `tabGeo Node` root
				ON IFNULL(root.parent_geo_node, '') = ''
				AND root.lft <= mine.lft AND mine.rgt <= root.rgt
				AND root.lft <= theirs.lft AND theirs.rgt <= root.rgt
			WHERE mine.geo_level = %(level)s
			LIMIT 1
			""",
			{"level": level, "other": other},
		)
	)
