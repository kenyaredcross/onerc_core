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
