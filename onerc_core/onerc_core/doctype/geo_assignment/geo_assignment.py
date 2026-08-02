# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Geo Assignment — a role held at a place in the geo tree.

Frappe Roles answer *what* a user may do. This doctype adds *where*: it binds a
role to a Geo Node, and the scope it grants is that node together with
everything beneath it.

One record is deliberately not enough to describe a user's authority. ACC-01: a
user may hold the same role at several unrelated nodes, and that is expressed as
several rows, not as one row with a list. Nothing here prevents it, and
`get_user_geo_scope()` unions the subtrees.

**Liveness is defined once, in this module, and nowhere else.** An assignment
grants nothing unless it is active and today falls inside its validity window.
Both the SQL and the in-Python form of that rule live here so the two cannot
drift; every caller — the scope service, approver routing, all three enforcement
layers — reads it from here rather than restating `is_active = 1 AND ...`.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import getdate, today

GEO_ASSIGNMENT_NAMING_SERIES = "GA-.#####"

# The liveness rule, as SQL. Callers alias `tabGeo Assignment` to `assignment`
# and bind `on_date`. A NULL bound means unbounded in that direction, and
# IFNULL-ing it to the date under test is what makes "unbounded" pass without a
# second branch. Frappe stores an empty Date as NULL, so there is no '' case.
LIVE_SQL = """
	assignment.is_active = 1
	AND IFNULL(assignment.valid_from, %(on_date)s) <= %(on_date)s
	AND IFNULL(assignment.valid_to, %(on_date)s) >= %(on_date)s
"""


def is_live(assignment, on_date: str | None = None) -> bool:
	"""The liveness rule in Python, for a single row already in hand.

	Mirrors `LIVE_SQL` exactly. Takes a document, a dict, or a docname. Use this
	rather than re-testing `is_active` and the dates at the call site — that
	restatement is how the query path and the document path drift apart.
	"""
	if isinstance(assignment, str):
		assignment = frappe.db.get_value(
			"Geo Assignment", assignment, ["is_active", "valid_from", "valid_to"], as_dict=True
		)

		if not assignment:
			return False

	on_date = getdate(on_date or today())

	if not assignment.get("is_active"):
		return False

	valid_from = assignment.get("valid_from")
	valid_to = assignment.get("valid_to")

	if valid_from and getdate(valid_from) > on_date:
		return False

	return not (valid_to and getdate(valid_to) < on_date)


class GeoAssignment(Document):
	def autoname(self):
		# Opaque key. Every field on this record is mutable — a user can be
		# renamed, an assignment moved to another node, a window extended — and
		# none of that may rewrite a primary key.
		self.name = make_autoname(GEO_ASSIGNMENT_NAMING_SERIES)

	def validate(self):
		self.validate_validity_window()

	def validate_validity_window(self):
		"""An assignment may not end before it begins.

		Note what is *not* validated: overlapping or duplicate rows for the same
		user, role and node. Two windows at one node is how an acting coordinator
		serving twice is recorded, and ACC-01 requires the same role at unrelated
		nodes. Scope unions and approver lists de-duplicate, so redundancy here is
		harmless — while a uniqueness rule would forbid legitimate history.
		"""
		if not (self.valid_from and self.valid_to):
			return

		if getdate(self.valid_to) < getdate(self.valid_from):
			frappe.throw(
				_("An assignment cannot end ({0}) before it starts ({1}).").format(
					frappe.bold(self.valid_to), frappe.bold(self.valid_from)
				),
				title=_("Invalid Validity Window"),
			)
