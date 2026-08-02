# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Which doctypes are geo-scoped — declared by the apps that own them.

Core provides the scoping engine. It must not know that a Volunteer exists:
Volunteer lives in a product app that core may not import and, today, may not
even be installed. So discovery is inverted, the same way affiliation providers
and the capability resolver are. Each app declares its own scopeable doctypes in
its `hooks.py`::

    onerc_scopeable_doctypes = [
        {
            "doctype": "Volunteer",
            "geo_node_field": "home_geo_node",
            "role": "Volunteer Approver",
        },
    ]

Read that as: *scope my Volunteer doctype on its home_geo_node field, for the
Volunteer Approver role.* Core reads the declaration and generates the
enforcement from it; it never names Volunteer, and nothing here imports the app
that did.

**With nothing registered the engine is inert.** `frappe.get_hooks` returns an
empty list, no doctype is scoped, and the enforcement layers hand back "no
opinion" — core standalone behaves exactly as if this layer did not exist.
That is a tested property, not an incidental one.

Naming the role
---------------

A literal `role` hardcodes *which* Frappe role scopes a doctype into an app's
source, and which role a society gives its membership officers or its volunteer
coordinators is exactly the kind of thing that differs between national
societies. So a registration may instead name a **National Society Settings
field whose value is the role**::

    onerc_scopeable_doctypes = [
        {
            "doctype": "Volunteer",
            "geo_node_field": "home_geo_node",
            "role_from_setting": "volunteer_scope_role",
        },
    ]

Exactly one of `role` and `role_from_setting` is given. `role` is unchanged and
keeps behaving identically — this is an addition, not a migration.

**Settings keys only.** A callable or a dotted path would put an
arbitrary-code-execution surface inside the access layer, reachable from a hook
that any installed app can write. A settings fieldname can only ever name a
role, which is all this needs to do.

**Resolution failures are loud, never silent.** The bug this shape exists to
kill is a role that names nothing: `get_user_geo_scope` would match no
assignment, return an empty set, and every layer would deny everybody with no
signal at all — a site-wide outage that looks exactly like "nobody has been
granted anything yet". So the two are now distinguishable:

* a role that resolves and legitimately has no assignments → empty scope, no
  error, and that is *normal*;
* a role that cannot be resolved → an Error Log entry and a closed door.

See `resolve_role()` below, and `NationalSocietySettings.validate()` for the
config-time half that stops a bad value being saved in the first place.
"""

import frappe
from frappe import _

SCOPEABLE_DOCTYPE_HOOK = "onerc_scopeable_doctypes"

# Always required: what is being scoped, and on which field.
BASE_KEYS = ("doctype", "geo_node_field")

# Exactly one of these names the role. `role` is a literal Frappe role name;
# `role_from_setting` is the fieldname of a National Society Settings field
# whose *value* is the role name.
ROLE_KEY = "role"
ROLE_SETTING_KEY = "role_from_setting"
ROLE_KEYS = (ROLE_KEY, ROLE_SETTING_KEY)

# Kept for message text and for anything reading the historical name. A static
# registration still consists of exactly these three keys and nothing else.
REQUIRED_KEYS = (*BASE_KEYS, ROLE_KEY)

# Named so the signal is a fact a test can assert on rather than prose that
# drifts. Every unresolvable role logs under this title.
UNRESOLVED_ROLE_LOG_TITLE = "Scopeable doctype role could not be resolved"


def registrations() -> dict[str, dict]:
	"""Every declared scopeable doctype, keyed by doctype name.

	Structure is validated here; the existence of the doctype and its field is
	not. That check belongs at the point of use, where the doctype is being
	queried and therefore certainly exists — validating it here would make a
	registration for a not-yet-migrated doctype break `bench migrate`.
	"""
	declared: dict[str, dict] = {}

	for raw in frappe.get_hooks(SCOPEABLE_DOCTYPE_HOOK) or []:
		entry = _validated(raw)
		doctype = entry["doctype"]

		if doctype in declared:
			# Two apps scoping one doctype differently is not something core can
			# arbitrate, and picking one would make a security boundary depend on
			# app install order.
			frappe.throw(
				_(
					"{0} is registered as scopeable more than once. Exactly one app may declare"
					" the geo field and role for a doctype."
				).format(frappe.bold(doctype)),
				title=_("Conflicting Scope Registration"),
			)

		declared[doctype] = entry

	return declared


def for_doctype(doctype: str) -> dict | None:
	"""The registration governing a doctype, or None if it is not scoped.

	None means "this layer has no opinion" — the caller must not read it as
	"denied". An unregistered doctype is simply not geo-scoped.
	"""
	if not doctype:
		return None

	return registrations().get(doctype)


def scoped_doctypes() -> list[str]:
	"""Names of the registered scopeable doctypes, sorted."""
	return sorted(registrations())


def geo_node_field(doctype: str) -> str:
	"""The registered geo field, checked against the doctype's actual meta.

	A registration naming a field that does not exist is a misconfiguration of
	the security layer, and it throws rather than degrading. The alternatives are
	worse: silently skipping the filter would leak every record of the doctype to
	every user, and silently denying everything would look like a data problem
	instead of the wiring mistake it is.
	"""
	registration = for_doctype(doctype)

	if not registration:
		frappe.throw(
			_("{0} is not registered as a scopeable doctype.").format(frappe.bold(doctype)),
			title=_("Doctype Not Scopeable"),
		)

	field = registration["geo_node_field"]

	if not frappe.get_meta(doctype).get_field(field):
		frappe.throw(
			_(
				"{0} is registered as scopeable on field {1}, which {0} does not have. Fix the"
				" {2} entry in the app that declared it."
			).format(frappe.bold(doctype), frappe.bold(field), frappe.bold(SCOPEABLE_DOCTYPE_HOOK)),
			title=_("Bad Scope Registration"),
		)

	return field


def resolve_role(registration: dict) -> str | None:
	"""The Frappe role this registration scopes by, or None if it cannot be found.

	The single place the two registration shapes converge, so all three
	enforcement layers ask one question and get one answer. Everything
	downstream — `get_user_geo_scope`, `resolve_approvers` — still receives a
	plain role-name string and is untouched by this.

	A literal `role` is returned as-is and is **not** checked for existence.
	That is deliberate: it is exactly today's behaviour, and adding a lookup
	would change how every existing registration performs and behaves for no
	benefit the config-time check does not already give.

	`role_from_setting` is read through `config.settings()` — the same cached
	single every other society-configuration reader uses, so this adds no
	database round trip to the enforcement hot path.

	Returns None when the setting is unset, names a field that does not exist,
	or names a role that does not. Each of those is logged under
	`UNRESOLVED_ROLE_LOG_TITLE`; the caller fails closed. None is never
	"unfiltered" and never "allow".
	"""
	literal = registration.get(ROLE_KEY)

	if literal:
		return literal

	fieldname = registration.get(ROLE_SETTING_KEY)

	if not fieldname:
		# Unreachable through registrations(), which enforces the XOR. Guarded
		# anyway because this is the access layer and a caller may hand-build a
		# registration dict.
		_unresolved(registration, "the registration names no role at all")

		return None

	from onerc_core.society.services import config

	role = (config.settings().get(fieldname) or "").strip()

	if not role:
		_unresolved(
			registration,
			f"National Society Settings has no value for {fieldname!r}"
			" — the society has not chosen which role scopes this doctype yet",
		)

		return None

	if not frappe.db.exists("Role", role):
		_unresolved(
			registration,
			f"National Society Settings {fieldname!r} names role {role!r}, which does not exist",
		)

		return None

	return role


def settings_backed_registrations() -> list[dict]:
	"""Every registration whose role comes from a settings field.

	What `NationalSocietySettings.validate()` iterates to check the values being
	saved. Returned as whole registrations so the caller never has to know the
	key names.
	"""
	return [entry for entry in registrations().values() if entry.get(ROLE_SETTING_KEY)]


def _unresolved(registration: dict, reason: str) -> None:
	"""Record that a scoped doctype has no usable role. The detectable signal.

	Logged on every occurrence rather than deduplicated. A misconfigured access
	boundary denies every user of that doctype, which is an outage; the noise is
	the alarm, and the config-time check in National Society Settings is what
	stops it reaching production in the first place.

	`scope._descendants` already logs from inside the same hot path for the same
	reason, so this is the established shape here rather than a new risk.
	"""
	frappe.log_error(
		title=UNRESOLVED_ROLE_LOG_TITLE,
		message=(
			f"{registration.get('doctype')} is registered as geo-scoped, but its role could not be"
			f" resolved: {reason}. Every user was denied access to it. Registration: {registration}"
		),
	)


def _validated(raw) -> dict:
	"""Check one declaration's shape, naming what is wrong with it.

	Returns the entry with the base keys plus **whichever one** role key was
	given — so a static registration comes back as exactly
	`{doctype, geo_node_field, role}`, byte for byte what it was before this
	capability existed. Nothing downstream can tell the difference, which is the
	point.
	"""
	if not isinstance(raw, dict):
		frappe.throw(
			_("A {0} entry must be a dict with keys {1}. Got {2}.").format(
				frappe.bold(SCOPEABLE_DOCTYPE_HOOK), ", ".join(REQUIRED_KEYS), frappe.bold(type(raw).__name__)
			),
			title=_("Bad Scope Registration"),
		)

	missing = [key for key in BASE_KEYS if not raw.get(key)]

	if missing:
		frappe.throw(
			_("A {0} entry is missing {1}. Every entry needs {2}.").format(
				frappe.bold(SCOPEABLE_DOCTYPE_HOOK), ", ".join(missing), ", ".join(REQUIRED_KEYS)
			),
			frappe.MandatoryError,
			title=_("Incomplete Scope Registration"),
		)

	entry = {key: str(raw[key]) for key in BASE_KEYS}
	entry[_role_key(raw)] = str(raw[_role_key(raw)])

	return entry


def _role_key(raw: dict) -> str:
	"""Which of the two role keys this entry uses. Exactly one, or it throws.

	Both is refused rather than resolved by precedence: a registration carrying
	a literal *and* a settings key has two answers to one question, and picking
	one silently would mean the security boundary depended on which key the
	reader happened to look at first.
	"""
	given = [key for key in ROLE_KEYS if raw.get(key)]

	if len(given) == 1:
		return given[0]

	if given:
		frappe.throw(
			_(
				"A {0} entry for {1} gives both {2} and {3}. Exactly one names the role: a literal"
				" role, or the settings field holding it."
			).format(
				frappe.bold(SCOPEABLE_DOCTYPE_HOOK),
				frappe.bold(str(raw.get("doctype"))),
				frappe.bold(ROLE_KEY),
				frappe.bold(ROLE_SETTING_KEY),
			),
			title=_("Ambiguous Scope Registration"),
		)

	frappe.throw(
		_(
			"A {0} entry for {1} names no role. Give either {2} (a Frappe role name) or {3} (the"
			" National Society Settings field holding one)."
		).format(
			frappe.bold(SCOPEABLE_DOCTYPE_HOOK),
			frappe.bold(str(raw.get("doctype"))),
			frappe.bold(ROLE_KEY),
			frappe.bold(ROLE_SETTING_KEY),
		),
		frappe.MandatoryError,
		title=_("Incomplete Scope Registration"),
	)
