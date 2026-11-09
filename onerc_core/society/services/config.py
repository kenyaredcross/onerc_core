# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

"""Society configuration service — one call for everything a product UI needs.

`get_ui_config()` is the supported way to read National Society Settings. Not
because reading a field is hard, but because the *fallbacks* are the contract:

* unset locale falls back to System Settings, so this doctype never becomes a
  second, competing source of truth for site formatting;
* the dark logo falls back to the main logo;
* a missing terminology override falls back to the key itself;
* an absent feature toggle falls back to the caller's default, because core does
  not own the list of features and cannot have an opinion on one it never
  defined.

Read a field directly and you get none of that. The payload's shape is also
deliberately independent of the form layout — `primary_language` sits in the
Society tab and belongs in `locale` here.
"""

import re

import frappe

SETTINGS_DOCTYPE = "National Society Settings"

_THEME_COLOR_TOKENS = (
	"primary_color",
	"secondary_color",
	"accent_color",
	"background",
	"surface_color",
	"text_color",
	"muted_text_color",
	"border_color",
	"success_color",
	"warning_color",
	"danger_color",
	"info_color",
)

_THEME_SHAPE_TOKENS = ("font_family", "base_font_size", "border_radius")


def settings():
	"""The settings single, cached per request.

	Works before anyone has ever opened the form: a Single that has never been
	saved still loads, with every field empty. Every reader below treats blank
	as "not configured" rather than as a value, so a fresh site degrades to
	defaults instead of throwing.
	"""
	return frappe.get_cached_doc(SETTINGS_DOCTYPE)


@frappe.whitelist()
def get_ui_config() -> dict:
	"""Everything a product UI needs from society configuration, in one call.

	Authenticated deliberately — feature toggles and validation policy describe
	how a product behaves internally. A guest-safe branding subset can be split
	out when there is a public portal that needs one.
	"""
	config = settings()

	return {
		"society": _society(config),
		"theme": _theme(config),
		"locale": _locale(config),
		"terminology": terminology(),
		"features": features(),
		"validation": {"phone": phone_policy()},
		"social_media": _social_media(config),
	}


def _society(config) -> dict:
	return {
		"name": config.organization_name,
		"short_name": config.organization_short_name,
		"country": config.country,
		"website": config.official_website,
		"telephone": config.telephone,
		"physical_address": config.physical_address,
		"logo": config.logo,
		# Falls back, so a UI on a dark surface always has something to draw.
		"logo_dark": config.logo_dark or config.logo,
		"favicon": config.favicon,
	}


def _theme(config) -> dict:
	"""Only tokens that are actually set.

	A blank token is omitted rather than returned as None, so a consuming UI
	spreads this over its own defaults without blanking them out.
	"""
	tokens = {token: config.get(token) for token in (*_THEME_COLOR_TOKENS, *_THEME_SHAPE_TOKENS)}

	return {token: value for token, value in tokens.items() if value}


def _locale(config) -> dict:
	"""Society locale, falling back to System Settings field by field."""
	system = frappe.get_cached_doc("System Settings")

	return {
		"primary_language": config.primary_language or system.language,
		"secondary_languages": [row.language for row in config.secondary_languages if row.language],
		"currency": config.currency,
		"time_zone": config.time_zone or system.time_zone,
		"date_format": config.date_format or system.date_format,
		"time_format": config.time_format or system.time_format,
		"first_day_of_week": config.first_day_of_week or system.first_day_of_the_week,
		# Sourced from System Settings only. Duplicating it here would create two
		# answers to one question, with no consumer asking for a second.
		"number_format": system.number_format,
		"float_precision": system.float_precision,
	}


def _social_media(config) -> list[dict]:
	return [
		{"site": row.social_media_site, "url": row.url, "icon": row.icon}
		for row in config.social_media
		if row.url
	]


def terminology() -> dict[str, dict]:
	"""{term key: {singular, plural}} for every configured override."""
	return {
		row.term_key: {
			"singular": row.singular,
			"plural": row.plural or f"{row.singular}s",
		}
		for row in settings().terminology
		if row.term_key and row.singular
	}


def term(key: str, plural: bool = False) -> str:
	"""This society's word for `key`, or the key back if it has no opinion.

	Falling back to the key means a product never renders an empty label, and a
	term nobody has configured is obvious on screen rather than invisible.
	"""
	override = terminology().get(key)

	if not override:
		return key

	return override["plural"] if plural else override["singular"]


def features() -> dict[str, bool]:
	"""{feature key: enabled} for every configured toggle."""
	return {row.feature_key: bool(row.is_enabled) for row in settings().feature_toggles if row.feature_key}


def is_feature_enabled(key: str, default: bool = False) -> bool:
	"""Is `key` switched on for this society?

	`default` is the caller's, because core does not define features and cannot
	know whether an unconfigured one should be on. An absent key is absent, not
	off.
	"""
	return features().get(key, default)


def phone_policy() -> dict:
	"""{pattern, example} — the society's phone number rule, if it has one."""
	config = settings()

	return {"pattern": config.phone_number_pattern, "example": config.phone_number_example}


def validate_phone_number(value: str | None, fieldlabel: str | None = None) -> None:
	"""Check a number against the society's pattern. No pattern, no check.

	Lives here rather than on Red Profile so every doctype that stores a phone
	number gets the same rule from the same place, and so the regex is never
	written in code.
	"""
	from frappe import _

	value = (value or "").strip()
	policy = phone_policy()

	if not value or not policy["pattern"]:
		return

	if re.fullmatch(policy["pattern"], value):
		return

	label = fieldlabel or _("Phone")
	example = policy["example"]

	if example:
		frappe.throw(
			_("{0} {1} is not valid for this society. Expected something like {2}.").format(
				label, frappe.bold(value), frappe.bold(example)
			),
			title=_("Invalid Phone Number"),
		)

	frappe.throw(
		_("{0} {1} is not valid for this society.").format(label, frappe.bold(value)),
		title=_("Invalid Phone Number"),
	)
