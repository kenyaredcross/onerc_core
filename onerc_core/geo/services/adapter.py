# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Geo adapter — the only supported way to read the geo hierarchy.

No app outside `onerc_core` may import Geo Node or Geo Level directly.
Everything geo goes through this module.

Two rules hold throughout:

1. Ancestry and descent are resolved with the NestedSet `lft`/`rgt` bounds,
   never by walking parent links recursively — and *ordered* by those bounds
   too, so "nearest ancestor" means nearest in the tree rather than nearest in
   the level ladder.
2. Level order comes from joining to Geo Level. There is no denormalised
   `geo_level_order` on Geo Node, and no framework default ordering is
   trusted — every ordered query names its ORDER BY explicitly.
"""

from collections.abc import Callable

import frappe
from frappe import _

PATH_SEPARATOR = " — "

# Selected for every node dict this module returns. `geo_level_order` here is a
# join result, not a stored field on Geo Node.
_NODE_FIELDS = """
	node.name AS name,
	node.geo_node_name AS geo_node_name,
	node.geo_code AS geo_code,
	node.geo_level AS geo_level,
	node.parent_geo_node AS parent_geo_node,
	node.is_group AS is_group,
	node.lft AS lft,
	node.rgt AS rgt,
	lvl.geo_level_order AS geo_level_order
"""


def _bounds(node: str) -> tuple[int, int]:
	"""Return the (lft, rgt) bounds of a node, or throw if it does not exist."""
	row = frappe.db.get_value("Geo Node", node, ["lft", "rgt"], as_dict=True)

	if not row:
		frappe.throw(_("Geo Node {0} does not exist").format(frappe.bold(node)), frappe.DoesNotExistError)

	return row.lft, row.rgt


def get_root_regions() -> list[dict]:
	"""Top-of-tree nodes — those with no parent.

	Parentless, deliberately — not `geo_level_order = 1`. In a well-formed
	hierarchy the two coincide, and only the parent link is structural: level
	order is configuration a society can renumber, so filtering on it would
	make this query answer a different question than the one it is named for.
	"""
	return frappe.db.sql(
		f"""
		SELECT {_NODE_FIELDS}
		FROM `tabGeo Node` node
		INNER JOIN `tabGeo Level` lvl ON lvl.name = node.geo_level
		WHERE IFNULL(node.parent_geo_node, '') = ''
		ORDER BY node.geo_node_name ASC
		""",
		as_dict=True,
	)


def get_children(node: str) -> list[dict]:
	"""Direct children of a node, one level down."""
	return frappe.db.sql(
		f"""
		SELECT {_NODE_FIELDS}
		FROM `tabGeo Node` node
		INNER JOIN `tabGeo Level` lvl ON lvl.name = node.geo_level
		WHERE node.parent_geo_node = %(node)s
		ORDER BY node.geo_node_name ASC
		""",
		{"node": node},
		as_dict=True,
	)


def get_ancestors(node: str) -> list[dict]:
	"""Ancestors of a node, NEAREST FIRST — immediate parent first, root last.

	Nearest-first is the contract, and nearest means *nearest in the tree*.
	Ordering is `lft` descending, which is tree position and nothing else: every
	ancestor of a node encloses it, so no two of them can partially overlap, and
	the one whose `lft` is largest is the innermost — the immediate parent.

	It deliberately does not order by `geo_level_order`. In a well-formed
	hierarchy the two agree, and Geo Node now refuses a parent at the same or a
	deeper level so new rows cannot disagree. But level order is configuration a
	society can renumber, and rows written before that rule existed are still on
	disk; if the two ever diverge, the tree is the truth. Deriving nearness from
	the level ladder is how approver routing walks past the true nearest holder.
	"""
	lft, rgt = _bounds(node)

	return frappe.db.sql(
		f"""
		SELECT {_NODE_FIELDS}
		FROM `tabGeo Node` node
		INNER JOIN `tabGeo Level` lvl ON lvl.name = node.geo_level
		WHERE node.lft < %(lft)s AND node.rgt > %(rgt)s
		ORDER BY node.lft DESC
		""",
		{"lft": lft, "rgt": rgt},
		as_dict=True,
	)


def get_descendants(node: str) -> list[str]:
	"""Every node beneath this one, at any depth. Names only, top-down."""
	lft, rgt = _bounds(node)

	return frappe.db.sql(
		"""
		SELECT node.name
		FROM `tabGeo Node` node
		WHERE node.lft > %(lft)s AND node.rgt < %(rgt)s
		ORDER BY node.lft ASC
		""",
		{"lft": lft, "rgt": rgt},
		pluck=True,
	)


def get_level(node: str) -> dict:
	"""The Geo Level a node sits at: {key, name, order, is_lowest}."""
	row = frappe.db.sql(
		"""
		SELECT
			lvl.name AS `key`,
			lvl.geo_level_name AS name,
			lvl.geo_level_order AS `order`,
			lvl.is_lowest_level AS is_lowest
		FROM `tabGeo Node` node
		INNER JOIN `tabGeo Level` lvl ON lvl.name = node.geo_level
		WHERE node.name = %(node)s
		""",
		{"node": node},
		as_dict=True,
	)

	if not row:
		frappe.throw(_("Geo Node {0} does not exist").format(frappe.bold(node)), frappe.DoesNotExistError)

	return row[0]


def level_labels() -> list[dict]:
	"""Active levels top-down: [{key, name, order, is_lowest}, ...].

	What a UI renders as its hierarchy labels — "Region", "County", "Ward".
	"""
	return frappe.db.sql(
		"""
		SELECT
			lvl.name AS `key`,
			lvl.geo_level_name AS name,
			lvl.geo_level_order AS `order`,
			lvl.is_lowest_level AS is_lowest
		FROM `tabGeo Level` lvl
		WHERE lvl.is_active = 1
		ORDER BY lvl.geo_level_order ASC
		""",
		as_dict=True,
	)


def is_leaf(node: str) -> bool:
	"""True when a node has no children.

	Read from the NestedSet bounds, not the `is_group` flag — the bounds are
	maintained by the framework and cannot drift from reality.
	"""
	lft, rgt = _bounds(node)

	return (rgt - lft) == 1


def get_full_path(node: str) -> str:
	"""Readable path from the node upward, e.g. "Kihara — Kiambu — Central"."""
	names = [frappe.db.get_value("Geo Node", node, "geo_node_name")]
	names.extend(ancestor.geo_node_name for ancestor in get_ancestors(node))

	return PATH_SEPARATOR.join(name for name in names if name)


def resolve_upward(node: str, predicate: Callable[[str], bool]) -> str | None:
	"""Walk [node] + ancestors nearest-first; return the first match.

	`predicate` receives a Geo Node docname. Returns None when nothing in the
	chain matches. Deliberately generic — approval routing and scope resolution
	both reduce to "find the nearest node upward that satisfies X".
	"""
	for candidate in [node, *(ancestor.name for ancestor in get_ancestors(node))]:
		if predicate(candidate):
			return candidate

	return None


def matches_scope(node: str, target: str, allow_ancestor: bool = True) -> bool:
	"""Is `node` within the scope of `target`?

	True when `node` is `target` itself, a descendant of it, or — when
	`allow_ancestor` — an ancestor of it. Containment is a bounds comparison,
	so depth is irrelevant.
	"""
	if node == target:
		return True

	node_lft, node_rgt = _bounds(node)
	target_lft, target_rgt = _bounds(target)

	is_descendant = target_lft < node_lft and node_rgt < target_rgt

	if is_descendant:
		return True

	if allow_ancestor:
		return node_lft < target_lft and target_rgt < node_rgt

	return False
