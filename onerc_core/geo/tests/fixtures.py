# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Hierarchy fixtures for geo tests.

Two well-formed shapes get built — a 3-level and a 5-level hierarchy — so the
adapter is exercised at more than one depth. Nothing in the adapter may assume a
fixed number of levels, and these fixtures are how that is proved.

There is a third, deliberately malformed shape: `build_misnested_chain()`, a
tree whose nesting does not follow the level ladder. It is what proves the
adapter reads depth from the tree rather than from Geo Level.
"""

import frappe

THREE_LEVEL_PREFIX = "T3"
FIVE_LEVEL_PREFIX = "T5"
MISNESTED_PREFIX = "TX"
_ALL_PREFIXES = (THREE_LEVEL_PREFIX, FIVE_LEVEL_PREFIX, MISNESTED_PREFIX)


def make_level(
	key: str,
	label: str,
	order: int,
	*,
	is_lowest: bool = False,
	is_active: bool = True,
	requires_parent: bool | None = None,
) -> str:
	"""Create one Geo Level. `requires_parent` follows the order unless overridden."""
	if requires_parent is None:
		requires_parent = order > 1

	level = frappe.get_doc(
		{
			"doctype": "Geo Level",
			"geo_level_key": key,
			"geo_level_name": label,
			"geo_level_order": order,
			"is_lowest_level": int(is_lowest),
			"requires_parent": int(requires_parent),
			"is_active": int(is_active),
		}
	)
	level.insert()

	return level.name


def make_levels(prefix: str, labels: list[str]) -> list[str]:
	"""Create a full ladder of levels, top-down. The last one is the lowest."""
	deepest = len(labels)

	return [
		make_level(f"{prefix}-{order}", label, order, is_lowest=(order == deepest))
		for order, label in enumerate(labels, start=1)
	]


def make_node(label: str, level: str, parent: str | None = None, *, is_group: bool = False) -> str:
	node = frappe.get_doc(
		{
			"doctype": "Geo Node",
			"geo_node_name": label,
			"geo_level": level,
			"parent_geo_node": parent,
			"is_group": int(is_group),
		}
	)
	node.insert()

	return node.name


def make_chain(levels: list[str], labels: list[str], root_parent: str | None = None) -> list[str]:
	"""Create a single path down the hierarchy, one node per level."""
	nodes = []
	parent = root_parent

	for depth, (level, label) in enumerate(zip(levels, labels, strict=True)):
		parent = make_node(label, level, parent, is_group=(depth < len(levels) - 1))
		nodes.append(parent)

	return nodes


def build_misnested_chain(prefix: str) -> dict:
	"""A four-node chain whose depth and level ladder disagree.

	Geo Node refuses a parent at the same or a deeper level, so this shape cannot
	be built through the controller — which is the point. Rows written before
	that rule existed can still look like this, and a society is free to renumber
	its levels underneath a tree that is already there. The chain is therefore
	built valid and then two of its nodes are repointed with a direct write::

	    Root   (level order 1)
	    └── Mid    (level order 3)   ← a deeper level than the node below it
	        └── Inner  (level order 2)
	            └── Leaf   (level order 4)

	Ordering the ancestors of Leaf by `geo_level_order` gives Mid, Inner, Root.
	Ordering by tree position gives Inner, Mid, Root — and Inner is the true
	nearest. Anything that routes upward must reach Inner first.

	No level here is flagged `is_lowest_level`: only one active level may carry
	that flag, and a caller building this alongside another hierarchy would
	otherwise collide with it.
	"""
	levels = [
		make_level(f"{prefix}-{order}", label, order)
		for order, label in enumerate(("One", "Two", "Three", "Four"), start=1)
	]
	root, mid, inner, leaf = make_chain(levels, ["Root", "Mid", "Inner", "Leaf"])

	force_level(mid, levels[2])
	force_level(inner, levels[1])

	return {"levels": levels, "root": root, "mid": mid, "inner": inner, "leaf": leaf}


def force_level(node: str, level: str) -> None:
	"""Repoint a node at a level without going through validation.

	The only supported way to produce a tree nested out of level order, and it is
	supported only here — nothing outside these fixtures may write a Geo Node
	field behind the controller's back.
	"""
	frappe.db.set_value("Geo Node", node, "geo_level", level, update_modified=False)


def reset() -> None:
	"""Drop any fixture rows left over from an earlier run.

	IntegrationTestCase rolls the transaction back at class teardown, so this is
	belt-and-braces — it only matters if a previous run committed. Nodes go
	first, deepest before shallowest, because NestedSet refuses to delete a node
	that still has children.
	"""
	levels = frappe.get_all("Geo Level", filters={"name": ("like", "T_-%")}, pluck="name")
	levels = [level for level in levels if level.split("-")[0] in _ALL_PREFIXES]

	if not levels:
		return

	nodes = frappe.get_all(
		"Geo Node", filters={"geo_level": ("in", levels)}, order_by="lft desc", pluck="name"
	)

	for node in nodes:
		frappe.delete_doc("Geo Node", node, force=True)

	for level in levels:
		frappe.delete_doc("Geo Level", level, force=True)
