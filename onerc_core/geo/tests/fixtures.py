# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Hierarchy fixtures for geo tests.

Two shapes get built — a 3-level and a 5-level hierarchy — so the adapter is
exercised at more than one depth. Nothing in the adapter may assume a fixed
number of levels, and these fixtures are how that is proved.
"""

import frappe

THREE_LEVEL_PREFIX = "T3"
FIVE_LEVEL_PREFIX = "T5"
_ALL_PREFIXES = (THREE_LEVEL_PREFIX, FIVE_LEVEL_PREFIX)


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
