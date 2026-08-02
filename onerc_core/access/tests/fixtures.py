# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Fixtures for the access layer.

**The stand-in doctype is created for real.** Core must not name a product
doctype, so these tests register one of their own — a genuine DocType with a
genuine table and a genuine Link to Geo Node — and declare it through the real
`onerc_scopeable_doctypes` hook. Every layer then runs unmocked: the query
filter goes through Frappe's query engine against a real table, the document
check goes through `frappe.has_permission`, and the guard reads a real row.

Using a purpose-made doctype rather than borrowing ToDo is deliberate. ToDo
registers its own `get_permission_query_conditions`, which restricts a list to
its owner. That condition would AND with ours, and a user who saw nothing would
not tell us *which* rule refused them — exactly the ambiguity a negative test
cannot afford. A doctype with no permission rules of its own means an empty
result set has one possible cause.

The tree, built once per test class::

    Rift Valley (region)
    ├── County A          ← approver_a holds the approver role here
    │   ├── Ward A1
    │   └── Ward A2
    ├── County B          ← approver_b holds the approver role here
    │   └── Ward B1
    └── County C          ← nobody holds anything here
        └── Ward C1
"""

import frappe

from onerc_core.geo.tests import fixtures as geo_fixtures

TEST_PREFIX = "ACC-TEST"

# The stand-in scopeable doctype. Custom, so it lives in the database rather
# than on disk, and is torn down when the class finishes.
SCOPED_DOCTYPE = "ACC Scoped Record"
GEO_FIELD = "home_geo_node"

# Society-named roles, which is what a real registration carries. Nothing in the
# access services names them — they arrive as the `role` argument.
APPROVER_ROLE = f"{TEST_PREFIX} Volunteer Approver"
VIEWER_ROLE = f"{TEST_PREFIX} Member Viewer"
TEST_ROLES = (APPROVER_ROLE, VIEWER_ROLE)

LEVEL_PREFIX = "TA"
USER_DOMAIN = "@acc.test"


def registration(role: str = APPROVER_ROLE, doctype: str = SCOPED_DOCTYPE, field: str = GEO_FIELD) -> dict:
	"""What an owning app would put in its `onerc_scopeable_doctypes`."""
	return {"doctype": doctype, "geo_node_field": field, "role": role}


def make_role(name: str) -> str:
	if not frappe.db.exists("Role", name):
		frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert()

	return name


def ensure_scoped_doctype() -> str:
	"""Create the stand-in doctype, once.

	Creating a DocType is DDL, which commits implicitly — so this runs before any
	other fixture. Anything created after it still rolls back with the test
	transaction; anything created before would not.
	"""
	for role in TEST_ROLES:
		make_role(role)

	if frappe.db.exists("DocType", SCOPED_DOCTYPE):
		return SCOPED_DOCTYPE

	frappe.get_doc(
		{
			"doctype": "DocType",
			"name": SCOPED_DOCTYPE,
			"module": "Onerc Core",
			"custom": 1,
			"autoname": "hash",
			"fields": [
				{"fieldname": "title", "fieldtype": "Data", "label": "Title", "reqd": 1},
				{
					"fieldname": GEO_FIELD,
					"fieldtype": "Link",
					"options": "Geo Node",
					"label": "Home Geo Node",
				},
			],
			"permissions": [
				{"role": role, "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1}
				for role in ("System Manager", *TEST_ROLES)
			],
		}
	).insert()

	return SCOPED_DOCTYPE


def build_tree() -> dict:
	"""The three-county hierarchy. Returns {label: geo node docname}."""
	levels = [
		geo_fixtures.make_level(f"{LEVEL_PREFIX}-1", "Region", 1),
		geo_fixtures.make_level(f"{LEVEL_PREFIX}-2", "County", 2),
		geo_fixtures.make_level(f"{LEVEL_PREFIX}-3", "Ward", 3, is_lowest=True),
	]
	region_level, county_level, ward_level = levels

	tree = {"levels": dict(zip(("region", "county", "ward"), levels, strict=True))}
	tree["region"] = geo_fixtures.make_node("Rift Valley", region_level, None, is_group=True)

	for county, wards in (("A", ("A1", "A2")), ("B", ("B1",)), ("C", ("C1",))):
		key = f"county_{county.lower()}"
		tree[key] = geo_fixtures.make_node(f"County {county}", county_level, tree["region"], is_group=True)

		for ward in wards:
			tree[f"ward_{ward.lower()}"] = geo_fixtures.make_node(f"Ward {ward}", ward_level, tree[key])

	return tree


def make_user(handle: str, roles: list[str] | None = None) -> str:
	"""A System User with the given roles and nothing else.

	Deliberately not a System Manager — that role is the documented scope bypass,
	so a test user holding it would pass every check for the wrong reason.
	"""
	email = f"{handle}{USER_DOMAIN}"

	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True)

	for role in roles or []:
		make_role(role)

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": handle.replace("_", " ").title(),
			"send_welcome_email": 0,
			"user_type": "System User",
			"roles": [{"role": role} for role in roles or []],
		}
	)
	user.insert()
	frappe.clear_cache(user=email)

	return email


def make_assignment(
	user: str,
	role: str,
	geo_node: str,
	*,
	is_active: bool = True,
	valid_from: str | None = None,
	valid_to: str | None = None,
) -> str:
	make_role(role)

	doc = frappe.get_doc(
		{
			"doctype": "Geo Assignment",
			"user": user,
			"role": role,
			"geo_node": geo_node,
			"is_active": int(is_active),
			"valid_from": valid_from,
			"valid_to": valid_to,
		}
	)
	doc.insert()

	return doc.name


def make_record(title: str, geo_node: str | None) -> str:
	doc = frappe.get_doc({"doctype": SCOPED_DOCTYPE, "title": f"{TEST_PREFIX} {title}", GEO_FIELD: geo_node})
	doc.insert()

	return doc.name


def reset() -> None:
	"""Drop fixture rows left behind by a run that committed.

	Order matters: records and assignments hold Links to Geo Nodes, and NestedSet
	refuses to delete a node that still has children, so nodes go deepest first.
	"""
	if frappe.db.exists("DocType", SCOPED_DOCTYPE):
		for record in frappe.get_all(SCOPED_DOCTYPE, pluck="name"):
			frappe.delete_doc(SCOPED_DOCTYPE, record, force=True)

	for user in frappe.get_all("User", filters={"email": ("like", f"%{USER_DOMAIN}")}, pluck="name"):
		frappe.delete_doc("User", user, force=True)

	levels = frappe.get_all("Geo Level", filters={"name": ("like", f"{LEVEL_PREFIX}-%")}, pluck="name")

	if levels:
		nodes = frappe.get_all(
			"Geo Node", filters={"geo_level": ("in", levels)}, order_by="lft desc", pluck="name"
		)

		for node in nodes:
			for assignment in frappe.get_all("Geo Assignment", filters={"geo_node": node}, pluck="name"):
				frappe.delete_doc("Geo Assignment", assignment, force=True)

			frappe.delete_doc("Geo Node", node, force=True)

		for level in levels:
			frappe.delete_doc("Geo Level", level, force=True)


def teardown() -> None:
	"""Remove the stand-in doctype and its roles. Mirrors ensure_scoped_doctype()."""
	reset()

	if frappe.db.exists("DocType", SCOPED_DOCTYPE):
		frappe.delete_doc("DocType", SCOPED_DOCTYPE, force=True)

	for role in TEST_ROLES:
		if frappe.db.exists("Role", role):
			frappe.delete_doc("Role", role, force=True)
