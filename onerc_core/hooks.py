app_name = "onerc_core"
app_title = "Onerc Core"
app_publisher = "Kelvin Njenga"
app_description = "One RC Core"
app_email = "njengasheba@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "onerc_core",
# 		"logo": "/assets/onerc_core/logo.png",
# 		"title": "Onerc Core",
# 		"route": "/onerc_core",
# 		"has_permission": "onerc_core.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/onerc_core/css/onerc_core.css"
# app_include_js = "/assets/onerc_core/js/onerc_core.js"

# include js, css files in header of web template
# web_include_css = "/assets/onerc_core/css/onerc_core.css"
# web_include_js = "/assets/onerc_core/js/onerc_core.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "onerc_core/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "onerc_core/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "onerc_core.utils.jinja_methods",
# 	"filters": "onerc_core.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "onerc_core.install.before_install"
# after_install = "onerc_core.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "onerc_core.uninstall.before_uninstall"
# after_uninstall = "onerc_core.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "onerc_core.utils.before_app_install"
# after_app_install = "onerc_core.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "onerc_core.utils.before_app_uninstall"
# after_app_uninstall = "onerc_core.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "onerc_core.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways
#
# Geo scoping, registered under the "*" wildcard. Frappe resolves these hooks as
# `hooks.get(doctype, []) + hooks.get("*", [])`, so a wildcard handler is called
# for every doctype and decides for itself whether it has anything to say.
#
# That is what keeps the inversion to a single declaration: an app makes its
# doctype geo-scoped by adding one `onerc_scopeable_doctypes` entry, and does
# not also have to wire these two hooks. Both handlers return "no opinion" —
# empty condition, permission granted — for any doctype nobody registered, so a
# site with no product apps installed is unaffected.
#
# See onerc_core/access/services/enforcement.py.

permission_query_conditions = {"*": "onerc_core.access.services.enforcement.get_permission_query_conditions"}

has_permission = {"*": "onerc_core.access.services.enforcement.has_permission"}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"onerc_core.tasks.all"
# 	],
# 	"daily": [
# 		"onerc_core.tasks.daily"
# 	],
# 	"hourly": [
# 		"onerc_core.tasks.hourly"
# 	],
# 	"weekly": [
# 		"onerc_core.tasks.weekly"
# 	],
# 	"monthly": [
# 		"onerc_core.tasks.monthly"
# 	],
# }

scheduler_events = {
	"cron": {"*/5 * * * *": ["onerc_core.onerc_core.doctype.article.article.publish_scheduled_articles"]}
}

fixtures = [
	{
		"dt": "Stakeholder Entity",
		"filters": [
			[
				"entity_name",
				"in",
				[
					"Organisation",
					"Consortium",
					"Individual",
				],
			]
		],
	},
	{
		"dt": "Stakeholder Classification",
		"filters": [
			[
				"classification_name",
				"in",
				[
					"Government",
					"Private Sector",
					"Donor",
					"Peer Organization",
					"Implementing Partner",
					"Potential Donor",
				],
			]
		],
	},
]
# Testing
# -------

# before_tests = "onerc_core.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "onerc_core.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "onerc_core.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "onerc_core.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["onerc_core.utils.before_request"]
# after_request = ["onerc_core.utils.after_request"]

# Job Events
# ----------
# before_job = ["onerc_core.utils.before_job"]
# after_job = ["onerc_core.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"onerc_core.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

# Hooks onerc_core consumes from other apps
# -----------------------------------------
#
# Core defines these; satellite apps implement them. Core never imports a
# satellite, so both are dependency-inverted: the other app registers itself.
#
# onerc_affiliation_providers — how rebuild_affiliations() discovers what to
# rebuild a Red Profile's affiliation index from. Each provider declares the
# satellite doctypes it owns and returns the profile's live affiliations:
#
# 	onerc_affiliation_providers = ["vmmsx.volunteer.affiliations.provide"]
#
# 	def provide(profile: str) -> dict:
# 		return {
# 			"reference_doctypes": ["Volunteer"],
# 			"affiliations": [
# 				{
# 					"affiliation_type": "volunteer",
# 					"status": "Active",
# 					"reference_doctype": "Volunteer",
# 					"reference_name": "VOL-00042",
# 				}
# 			],
# 		}
#
# A row is only ever removed when a registered provider owns its
# reference_doctype and did not claim it. No providers means no ownership, so a
# rebuild on a site with no satellites installed is a read-only no-op.
# See onerc_core/identity/services/affiliation.py.
#
# onerc_capability_resolver — how the read gate asks whether a user holds a
# capability. Exactly one app may own it, and with none installed every gated
# affiliation row is hidden from everyone:
#
# 	onerc_capability_resolver = "some_app.capabilities.has_capability"
#
# 	def has_capability(user: str, capability: str) -> bool: ...
#
# See onerc_core/identity/services/read_gate.py.
#
# onerc_scopeable_doctypes — which doctypes are geo-scoped, and on what field.
# Core owns the scoping engine but must never name a product doctype, so each
# app declares its own:
#
# 	onerc_scopeable_doctypes = [
# 		{
# 			"doctype": "Volunteer",
# 			"geo_node_field": "home_geo_node",
# 			"role": "Volunteer Approver",
# 		},
# 	]
#
# Read as: scope my Volunteer doctype on its home_geo_node field, for the
# Volunteer Approver role. Core generates all three enforcement layers from that
# — list query, document read and the API guard — without importing the app.
#
# Exactly one app may register a given doctype: two apps scoping one doctype
# differently would make a security boundary depend on install order. With
# nothing registered the engine is inert and no doctype is scoped.
#
# See onerc_core/access/services/registry.py.
