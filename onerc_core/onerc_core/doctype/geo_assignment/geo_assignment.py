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

**What an assignment grants is defined once, in this module, and nowhere else.**
It grants nothing unless two things hold together:

1. it is **live** — active, and today inside its validity window;
2. the user **still holds the Frappe role** the row names.

The second is what makes off-boarding work. A Geo Assignment does not create
authority on its own; it places authority a user already has somewhere in the
tree. Strip the role and the placement has nothing left to place — so removing a
role revokes every assignment that named it, instantly and everywhere, without
anyone having to remember to deactivate rows as well. Either half of an
off-boarding — role removal or deactivating the assignment — fully revokes.

Both the SQL and the in-Python form of the rule live here so the two cannot
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

# The role-held rule, as SQL. A join rather than `frappe.get_roles`, because
# the queries this goes into answer for many users at once — `holders_at()`
# does not know whose rows it is about until the query has run.
#
# The Administrator branch mirrors `frappe.get_roles`, which answers "every
# role" for Administrator without there being a Has Role row to prove it.
# Without the branch the SQL and the Python below would disagree about exactly
# one user. It is a framework primitive, not a society role — the same
# exception, for the same reason, as the bypass in the scope service.
ROLE_HELD_SQL = """
	(
		assignment.user = 'Administrator'
		OR EXISTS (
			SELECT 1
			FROM `tabHas Role` held
			WHERE held.parenttype = 'User'
				AND held.parent = assignment.user
				AND held.role = assignment.role
		)
	)
"""

# What every reader of this table actually wants to ask. Callers alias
# `tabGeo Assignment` to `assignment` and bind `on_date`; nobody composes the
# two halves themselves, because a caller who took only `LIVE_SQL` would grant
# authority to a user who no longer holds the role.
GRANTS_AUTHORITY_SQL = f"({LIVE_SQL}) AND {ROLE_HELD_SQL}"

# What is read when a row arrives as a docname. Named once so `is_live()` and
# `grants_authority()` cannot fetch different halves of the same row.
_RULE_FIELDS = ["user", "role", "is_active", "valid_from", "valid_to"]


def _row(assignment):
	"""Accept a document, a dict, or a docname; return something with `.get()`."""
	if not isinstance(assignment, str):
		return assignment

	return frappe.db.get_value("Geo Assignment", assignment, _RULE_FIELDS, as_dict=True)


def is_live(assignment, on_date: str | None = None) -> bool:
	"""The liveness half of the rule: active, and inside its validity window.

	Mirrors `LIVE_SQL` exactly. Takes a document, a dict, or a docname. Use this
	rather than re-testing `is_active` and the dates at the call site — that
	restatement is how the query path and the document path drift apart.

	Liveness alone is not authority. `grants_authority()` is the question worth
	asking about a row; this is one of its two halves, kept separate only
	because "is this row still current" is a fair thing to ask on its own.
	"""
	assignment = _row(assignment)

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


def holds_role(user: str | None, role: str | None) -> bool:
	"""Does `user` currently hold `role`?

	`frappe.get_roles` rather than a Has Role query of our own: it is the
	framework's own answer to the question, and it already treats Administrator
	as holding every role — which is what `ROLE_HELD_SQL` spells out by hand.
	"""
	if not (user and role):
		return False

	return role in frappe.get_roles(user)


def grants_authority(assignment, on_date: str | None = None) -> bool:
	"""Does this row grant anything right now?

	The whole rule, mirroring `GRANTS_AUTHORITY_SQL`: live, *and* the role it
	names still held by the user it names. This is what callers holding a row
	should ask — `is_live()` on its own would honour an assignment belonging to
	someone who was off-boarded by having their roles removed.
	"""
	assignment = _row(assignment)

	if not assignment:
		return False

	return is_live(assignment, on_date) and holds_role(assignment.get("user"), assignment.get("role"))


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
