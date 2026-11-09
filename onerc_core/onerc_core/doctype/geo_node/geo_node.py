# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils.nestedset import NestedSet

GEO_NODE_NAMING_SERIES = "GEO-.#####"

# Decimal degrees. Not a society's business and not configuration: these are the
# bounds of the coordinate system, the same in every country.
LATITUDE_RANGE = (-90.0, 90.0)
LONGITUDE_RANGE = (-180.0, 180.0)


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
		self.validate_coordinates()

	def has_point(self) -> bool:
		"""Is there a coordinate pair on this node?

		A Float left empty is `0.0`, so this asks whether either value is
		non-zero rather than whether either is set. The cost is that the one point
		on the earth at exactly 0, 0 cannot be recorded; it is in the Atlantic, and
		a society whose branch is there has a larger problem.
		"""
		return bool(self.latitude) or bool(self.longitude)

	def validate_coordinates(self):
		"""A node's point is either on the earth or it is nothing.

		Both rules are about the pair being usable rather than about any society's
		geography. **Half a pair is the more insidious of the two**: an empty Float
		stores as `0.0`, so a node with a latitude typed in and a longitude left
		blank would be drawn confidently in the Gulf of Guinea — and unlike a
		missing point, which every reader already handles, a wrong one looks like
		an answer.
		"""
		if not self.has_point():
			return

		if not (self.latitude and self.longitude):
			frappe.throw(
				_(
					"A Geo Node needs both a latitude and a longitude, or neither. One on its own"
					" cannot be put on a map, and it would be drawn somewhere it is not. Leave both"
					" empty to keep this node without a point."
				),
				frappe.ValidationError,
				title=_("Half A Coordinate"),
			)

		for value, (low, high), label in (
			(self.latitude, LATITUDE_RANGE, _("Latitude")),
			(self.longitude, LONGITUDE_RANGE, _("Longitude")),
		):
			if low <= float(value) <= high:
				continue

			frappe.throw(
				_(
					"{0} {1} is not on the earth — it must be between {2} and {3}. The commonest"
					" cause is the two typed the wrong way round."
				).format(label, frappe.bold(value), low, high),
				frappe.ValidationError,
				title=_("Not A Point On The Earth"),
			)

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

		**Same-or-deeper refuses; skipping a rung only warns.** They are different
		mistakes. A parent at the same or a deeper level is a contradiction, and
		there is no reading under which it is what somebody meant. A parent two
		rungs up is merely unusual: a society that files a few nodes directly
		under the region because the county tier does not apply there has done
		nothing wrong, and refusing it would reject a valid tree. See
		`warn_on_skipped_level`.
		"""
		if not (self.geo_level and self.parent_geo_node):
			return

		own_order = frappe.db.get_value("Geo Level", self.geo_level, "geo_level_order")
		parent_level = frappe.db.get_value("Geo Node", self.parent_geo_node, "geo_level")
		parent_order = (
			frappe.db.get_value("Geo Level", parent_level, "geo_level_order") if parent_level else None
		)

		# Either level is unreadable, which in practice means a Link to a level
		# that has gone: `geo_level_order` is a mandatory Int, so its column is
		# NOT NULL and no surviving row can carry a blank one. Not this rule's
		# business to fix either way — whatever removed that level is already
		# broken, and a comparison against None would throw a TypeError rather
		# than say anything useful.
		#
		# It *is* this rule's business to say that it stood down. Returning in
		# silence disables the guard invisibly: every node saved under the
		# orphaned parent would pass a check that never ran, and the first anybody
		# would hear of it is a hierarchy nested in an order its own ladder
		# contradicts.
		if own_order is None or parent_order is None:
			self.log_unreadable_order(parent_level, own_order, parent_order)

			return

		if parent_order < own_order:
			self.warn_on_skipped_level(parent_level, own_order, parent_order)

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

	def warn_on_skipped_level(self, parent_level: str, own_order: int, parent_order: int) -> None:
		"""Say so when a parent is more than one rung up. Never block.

		**Why this is not a rule.** Strict adjacency — a Ward may only sit under
		a County, never straight under a Region — is a policy some societies hold
		and others do not. A district that has no sub-district, a city that is its
		own county, a national programme registering directly under the country:
		all of them skip a rung legitimately, and a hard rule would reject the
		real tree in favour of an idealised ladder. So the entry surface points it
		out and the society decides.

		A configurable strict mode is the obvious next step if a society asks for
		it. It is deliberately not built here: an unconfigurable rule is worse
		than no rule, and a configurable one nobody has asked for is a setting to
		maintain forever.
		"""
		if parent_order >= own_order - 1:
			return

		frappe.msgprint(
			_(
				"{0} is at level {1} (order {2}) and this node is at {3} (order {4}), so a rung has"
				" been skipped. That is allowed, and it is worth checking: it usually means the"
				" level in between was meant to be filled in."
			).format(
				frappe.bold(self.parent_geo_node),
				frappe.bold(parent_level),
				frappe.bold(parent_order),
				frappe.bold(self.geo_level),
				frappe.bold(own_order),
			),
			title=_("A Level Was Skipped"),
			indicator="orange",
		)

	def log_unreadable_order(self, parent_level: str | None, own_order, parent_order) -> None:
		"""Record that the shallower-parent guard could not run, and why.

		Logged rather than thrown. The tree is the truth and it is already
		written; refusing the save would punish whoever happens to touch a node
		next for a level somebody else left malformed. But a guard that stands
		down without saying so is indistinguishable from a guard that passed,
		which is how a broken ladder survives unnoticed for a year.
		"""
		missing = "this node's level" if own_order is None else "the parent's level"

		frappe.log_error(
			title="Geo Node parent-level check skipped",
			message=(
				f"Could not compare levels for Geo Node {self.name or '(new)'}: {missing} has no"
				f" readable geo_level_order.\n\n"
				f"  node level   : {self.geo_level} (order {own_order})\n"
				f"  parent       : {self.parent_geo_node}\n"
				f"  parent level : {parent_level} (order {parent_order})\n\n"
				"The parent-is-shallower guard did not run for this save. Either the level was"
				" deleted while nodes still pointed at it, or it was written without an order."
			),
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
