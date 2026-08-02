# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils.nestedset import NestedSet

GEO_NODE_NAMING_SERIES = "GEO-.#####"


class GeoNode(NestedSet):
	# Declared explicitly rather than relying on NestedSet deriving it. The
	# derivation in on_trash() is `frappe.scrub(doctype) + "_parent"`, which
	# would yield "geo_node_parent" — not our field — so leaving this implicit
	# is load-bearing on __setup__ having read it from the doctype meta first.
	nsm_parent_field = "parent_geo_node"

	def autoname(self):
		# Opaque key. The docname must never carry field values: geo_node_name
		# and geo_level are both mutable, and two same-named nodes under one
		# level are legitimate (Kihara in Kiambu, Kihara in Nairobi).
		self.name = make_autoname(GEO_NODE_NAMING_SERIES)

	def validate(self):
		self.geo_node_name = (self.geo_node_name or "").strip()
		self.validate_parent_requirement()
		self.validate_parent_is_shallower()
		self.validate_sibling_name_is_unique()

	def validate_parent_requirement(self):
		"""Enforce Geo Level's `requires_parent` server-side.

		This used to be a client-side `mandatory_depends_on` reading a
		denormalised `geo_level_order` on this doctype. That field is gone —
		order and parent policy are read from Geo Level.
		"""
		if not self.geo_level:
			return

		requires_parent = frappe.db.get_value("Geo Level", self.geo_level, "requires_parent")

		if requires_parent and not self.parent_geo_node:
			frappe.throw(
				_("{0} is required for a Geo Node at level {1}").format(
					frappe.bold(_("Parent Geo Node")), frappe.bold(self.geo_level)
				),
				frappe.MandatoryError,
			)

	def validate_parent_is_shallower(self):
		"""A parent must sit at a strictly shallower level than its child.

		Nothing used to relate the tree to the level ladder, so a County could be
		filed under a Ward and nobody would hear about it. Two things then go
		wrong at once: the hierarchy stops meaning what its levels say, and any
		code that reads depth off the level ladder — approver routing did — walks
		the chain in an order that is not the tree's.

		The adapter no longer trusts level order for ancestry, so this is not
		load-bearing for correctness any more. It is here because the malformed
		tree is a data-entry mistake worth refusing at the point it is made,
		rather than a shape the rest of the app has to keep tolerating.

		Order 1 is the top of the hierarchy, so "shallower" is a *lower* order.
		"""
		if not (self.geo_level and self.parent_geo_node):
			return

		own_order = frappe.db.get_value("Geo Level", self.geo_level, "geo_level_order")
		parent_level = frappe.db.get_value("Geo Node", self.parent_geo_node, "geo_level")
		parent_order = (
			frappe.db.get_value("Geo Level", parent_level, "geo_level_order") if parent_level else None
		)

		# Either level is unreadable — a Link to a level that has gone, or a level
		# saved without an order. Not this rule's business: whatever wrote that is
		# already broken, and a comparison against None would throw a TypeError
		# rather than say anything useful.
		if own_order is None or parent_order is None:
			return

		if parent_order < own_order:
			return

		frappe.throw(
			_(
				"{0} is at level {1} (order {2}), which is not above level {3} (order {4}). "
				"A Geo Node's parent must sit at a shallower level than the node itself."
			).format(
				frappe.bold(self.parent_geo_node),
				frappe.bold(parent_level),
				frappe.bold(parent_order),
				frappe.bold(self.geo_level),
				frappe.bold(own_order),
			),
			title=_("Parent Is Not Above This Level"),
		)

	def validate_sibling_name_is_unique(self):
		"""Two children of one parent may not share a name, case-insensitively.

		Scoped to siblings on purpose. The same name under *different* parents
		stays legal — Kihara in Kiambu and Kihara in Nairobi are two real places,
		and that case is what removing the `{geo_level}-{geo_node_name}` docname
		bought us. Only a collision *within* one parent is genuinely ambiguous:
		nothing downstream could tell the two apart.

		`IFNULL(..., '')` groups the roots together, matching how the adapter
		identifies them. `LOWER()` is explicit rather than leaning on the
		column's collation, which happens to be case-insensitive today but is
		not part of any contract.
		"""
		if not self.geo_node_name:
			return

		conflict = frappe.db.sql(
			"""
			SELECT name
			FROM `tabGeo Node`
			WHERE name != %(name)s
				AND IFNULL(parent_geo_node, '') = %(parent)s
				AND LOWER(geo_node_name) = %(label)s
			LIMIT 1
			""",
			{
				"name": self.name or "",
				"parent": self.parent_geo_node or "",
				"label": self.geo_node_name.lower(),
			},
			pluck=True,
		)

		if not conflict:
			return

		where = (
			_("under {0}").format(frappe.bold(self.parent_geo_node))
			if self.parent_geo_node
			else _("at the top of the hierarchy")
		)

		frappe.throw(
			_("A Geo Node named {0} already exists {1} ({2}). Sibling names must be unique.").format(
				frappe.bold(self.geo_node_name), where, conflict[0]
			),
			title=_("Duplicate Sibling Name"),
		)


def get_full_path(node: str) -> str:
	"""Readable ancestor path for a node, e.g. "Kihara — Kiambu — Central".

	Thin delegation to the geo adapter, which owns the geo_level_order join.
	Kept here so the doctype module exposes the helper, without a second
	implementation of the ordering rule.
	"""
	from onerc_core.geo.services import adapter

	return adapter.get_full_path(node)
