"""Build the onerc_core testing and verification guide as a Word document.

Run it from the app root with the bench environment's Python::

    env/bin/python apps/onerc_core/docs/generate_verification_guide.py

Every observed-output block in here was copied from a real run against the
reference bench while the document was written. When the code changes, re-run
the checks and update the blocks — a guide whose expected output is invented is
worse than no guide, because it teaches the reader to ignore a mismatch.
"""

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

OUTPUT = Path(__file__).resolve().parent / "onerc_core-verification-guide.docx"

# The palette. Kept here rather than inline so the document reads as one thing.
INK = RGBColor(0x1A, 0x1A, 0x1A)
CRIMSON = RGBColor(0x8B, 0x0F, 0x1D)
GREY = RGBColor(0x5A, 0x5A, 0x5A)
FAINT = RGBColor(0xBB, 0xBB, 0xBB)
GREEN_INK = RGBColor(0x1B, 0x4B, 0x2A)
GREEN_RULE = "1B6B3A"
AMBER_INK = RGBColor(0x8A, 0x64, 0x00)
AMBER_RULE = "C79100"
RED_INK = RGBColor(0xB3, 0x1B, 0x1B)
RED_RULE = "B31B1B"

CODE_FILL = "F2F2F2"
OBSERVED_FILL = "EDF5EE"
AMBER_FILL = "FCF7E8"
RED_FILL = "FBEFEF"
HEADER_FILL = "EDEDED"

CODE_FONT = "Consolas"
CODE_SIZE = Pt(8.5)

TICK = "☐"


# --------------------------------------------------------------------------
# low-level helpers
# --------------------------------------------------------------------------


def shade(paragraph, fill):
	shd = OxmlElement("w:shd")
	shd.set(qn("w:val"), "clear")
	shd.set(qn("w:fill"), fill)
	paragraph._p.get_or_add_pPr().append(shd)


def left_rule(paragraph, colour, size=24, space=8):
	borders = OxmlElement("w:pBdr")
	edge = OxmlElement("w:left")
	edge.set(qn("w:val"), "single")
	edge.set(qn("w:sz"), str(size))
	edge.set(qn("w:space"), str(space))
	edge.set(qn("w:color"), colour)
	borders.append(edge)
	paragraph._p.get_or_add_pPr().append(borders)


def top_rule(paragraph, colour="D9D9D9", size=6, space=4):
	borders = OxmlElement("w:pBdr")
	edge = OxmlElement("w:top")
	edge.set(qn("w:val"), "single")
	edge.set(qn("w:sz"), str(size))
	edge.set(qn("w:space"), str(space))
	edge.set(qn("w:color"), colour)
	borders.append(edge)
	paragraph._p.get_or_add_pPr().append(borders)


def monospace(run):
	run.font.name = CODE_FONT
	run.font.size = CODE_SIZE
	return run


_INLINE = re.compile(r"`([^`]+)`|\*\*([^*]+)\*\*")


def write_inline(paragraph, text, size=None, colour=None):
	"""Add text, rendering `code` spans in the code face and **bold** in bold."""
	position = 0

	def plain(chunk):
		if not chunk:
			return
		run = paragraph.add_run(chunk)
		if size:
			run.font.size = size
		if colour:
			run.font.color.rgb = colour

	for match in _INLINE.finditer(text):
		plain(text[position : match.start()])
		code, bold = match.group(1), match.group(2)

		if code is not None:
			monospace(paragraph.add_run(code))
		else:
			# A bold span may itself contain `code`, so split it again rather
			# than emitting the backticks as literal text.
			for index, chunk in enumerate(re.split(r"`([^`]+)`", bold)):
				if not chunk:
					continue

				run = paragraph.add_run(chunk)
				run.bold = True

				if index % 2:
					monospace(run)
					continue

				if size:
					run.font.size = size
				if colour:
					run.font.color.rgb = colour

		position = match.end()

	plain(text[position:])

	return paragraph


# --------------------------------------------------------------------------
# block builders
# --------------------------------------------------------------------------


class Guide:
	def __init__(self):
		self.doc = Document()
		self.checks = 0
		self._configure_styles()
		self._configure_page()

	def _configure_styles(self):
		styles = self.doc.styles

		normal = styles["Normal"]
		normal.font.name = "Calibri"
		normal.font.size = Pt(10.5)
		normal.font.color.rgb = INK
		normal.paragraph_format.space_after = Pt(6)
		normal.paragraph_format.line_spacing = 1.15

		for name, size, colour, before, after in (
			("Heading 1", 20, CRIMSON, 18, 8),
			("Heading 2", 14, INK, 14, 6),
			("Heading 3", 11.5, CRIMSON, 12, 4),
		):
			style = styles[name]
			style.font.name = "Calibri"
			style.font.size = Pt(size)
			style.font.bold = True
			style.font.color.rgb = colour
			style.paragraph_format.space_before = Pt(before)
			style.paragraph_format.space_after = Pt(after)

	def _configure_page(self):
		section = self.doc.sections[0]
		section.top_margin = section.bottom_margin = Pt(56.7)
		section.left_margin = section.right_margin = Pt(62.4)

	# -- structure ------------------------------------------------------

	def title(self, wordmark, subtitle):
		p = self.doc.add_paragraph()
		p.paragraph_format.space_after = Pt(2)
		run = p.add_run(wordmark)
		run.bold = True
		run.font.size = Pt(30)
		run.font.color.rgb = CRIMSON

		p = self.doc.add_paragraph()
		p.paragraph_format.space_after = Pt(14)
		run = p.add_run(subtitle)
		run.font.size = Pt(16)
		run.font.color.rgb = INK

	def h1(self, text):
		self.doc.add_heading(text, level=1)

	def h2(self, text):
		self.doc.add_heading(text, level=2)

	def h3(self, text):
		self.doc.add_heading(text, level=3)

	def check(self, number, title, verifying):
		"""A numbered check: heading, then the one-line claim under test."""
		self.checks += 1
		self.h3(f"{number}  {title}")
		p = self.doc.add_paragraph()
		p.paragraph_format.space_after = Pt(6)
		lead = p.add_run("What we're verifying:  ")
		lead.bold = True
		write_inline(p, verifying)

	# -- prose ----------------------------------------------------------

	def para(self, text, after=6):
		p = self.doc.add_paragraph()
		p.paragraph_format.space_after = Pt(after)
		write_inline(p, text)
		return p

	def bullet(self, text, lead=None):
		p = self.doc.add_paragraph(style="List Bullet")
		p.paragraph_format.space_after = Pt(2)
		if lead:
			run = p.add_run(f"{lead} ")
			run.bold = True
		write_inline(p, text)
		return p

	def label(self, text):
		p = self.doc.add_paragraph()
		p.paragraph_format.space_after = Pt(2)
		run = p.add_run(text)
		run.font.size = Pt(9)
		run.font.color.rgb = GREY
		return p

	# -- code and output -------------------------------------------------

	def _block(self, text, fill, colour=None, before=4):
		p = self.doc.add_paragraph()
		fmt = p.paragraph_format
		fmt.space_before = Pt(before)
		fmt.space_after = Pt(8)
		fmt.line_spacing_rule = WD_LINE_SPACING.SINGLE
		fmt.left_indent = Pt(11.35)
		shade(p, fill)

		for index, line in enumerate(text.strip("\n").split("\n")):
			run = monospace(p.add_run())
			if index:
				run.add_break()
			run.add_text(line)
			if colour:
				run.font.color.rgb = colour

		return p

	def code(self, text):
		return self._block(text, CODE_FILL, before=4)

	def observed(self, text, label="Observed on the reference bench:"):
		if label:
			self.label(label)
		return self._block(text, OBSERVED_FILL, GREEN_INK, before=2)

	def expected(self, text=None, bullets=()):
		if text:
			p = self.doc.add_paragraph()
			p.paragraph_format.space_after = Pt(4)
			run = p.add_run("Expected:  ")
			run.bold = True
			write_inline(p, text)
		else:
			p = self.doc.add_paragraph()
			p.paragraph_format.space_after = Pt(4)
			run = p.add_run("Expected:")
			run.bold = True

		for item in bullets:
			self.bullet(item)

	def tickbox(self):
		p = self.doc.add_paragraph()
		top_rule(p)
		p.paragraph_format.space_before = Pt(4)
		p.paragraph_format.space_after = Pt(14)
		run = p.add_run(f"{TICK}  Verified as expected          {TICK}  Deviation — note: ")
		run.font.size = Pt(9.5)
		run.font.color.rgb = GREY
		run = p.add_run("_" * 46)
		run.font.size = Pt(9.5)
		run.font.color.rgb = FAINT

	# -- callouts --------------------------------------------------------

	def callout(self, kind, heading, body):
		ink, rule, fill = {
			"observation": (AMBER_INK, AMBER_RULE, AMBER_FILL),
			"defect": (RED_INK, RED_RULE, RED_FILL),
			"resolved": (GREEN_INK, GREEN_RULE, OBSERVED_FILL),
		}[kind]

		p = self.doc.add_paragraph()
		left_rule(p, rule)
		shade(p, fill)
		p.paragraph_format.space_before = Pt(8)
		p.paragraph_format.space_after = Pt(4)

		run = p.add_run(heading)
		run.bold = True
		run.font.size = Pt(10.5)
		run.font.color.rgb = ink
		run.add_break()

		write_inline(p, body, size=Pt(10))
		return p

	# -- tables ----------------------------------------------------------

	def table(self, headers, rows, mono_columns=(), widths=None):
		table = self.doc.add_table(rows=1, cols=len(headers))
		table.style = "Table Grid"

		for cell, heading in zip(table.rows[0].cells, headers, strict=True):
			shade(cell.paragraphs[0], HEADER_FILL)
			run = cell.paragraphs[0].add_run(heading)
			run.bold = True
			run.font.size = Pt(9.5)

		for row in rows:
			cells = table.add_row().cells
			for index, (cell, value) in enumerate(zip(cells, row, strict=True)):
				p = cell.paragraphs[0]
				p.paragraph_format.space_after = Pt(2)
				if index in mono_columns:
					monospace(p.add_run(str(value)))
				else:
					write_inline(p, str(value), size=Pt(9))

		if widths:
			for row in table.rows:
				for cell, width in zip(row.cells, widths, strict=True):
					cell.width = width

		self.doc.add_paragraph().paragraph_format.space_after = Pt(2)
		return table

	def save(self):
		self.doc.save(OUTPUT)
		return OUTPUT


# --------------------------------------------------------------------------
# the document
# --------------------------------------------------------------------------


def build():
	g = Guide()

	g.title("onerc_core", "Testing & Verification Guide")
	g.para(
		"A hands-on script for confirming that the shared identity, geography, access and"
		" society-configuration foundation does what it claims — and, above all, that it carries no"
		" hardcoded assumptions about any one National Society. Work top to bottom. Every command below"
		" was executed against the reference bench while this document was written; the outputs shown are"
		" real, not illustrative."
	)

	g.table(
		["Field", "Value"],
		[
			("App under test", "onerc_core"),
			("Branch", "vmmsx-edition"),
			("Commit verified against", "0e9ff8e  chore(core): finalise doctype descriptions"),
			(
				"Working tree",
				"Not clean. The personal-identity work on Red Profile is uncommitted and this guide covers it — see 0.1.",
			),
			("Reference bench / site", "/home/nigel/frappe/main-bench  —  site vmms.localhost"),
			("Document date", "4 August 2026"),
			("Automated suite", "321 tests pass; 5 classes error in setUpClass for a bench reason — see 0.3"),
			("Checks in this guide", "72 manual checks across 6 sections"),
			("Supersedes", "The edition of 2 August 2026, written against ef5cbfb"),
		],
		mono_columns=(1,),
	)

	# ------------------------------------------------------------------
	g.h1("What changed since the last edition")
	g.para(
		"The 2 August edition raised three findings and recorded two cosmetic observations. **All three"
		" findings are now closed in code**, and both observations with them. Two things also changed"
		" underneath the guide that have nothing to do with those fixes: the access layer gained a way to"
		" take the scoping role from configuration rather than from an app's source, and the reference"
		" bench is no longer a bench where core stands alone."
	)

	g.table(
		["What", "Then", "Now"],
		[
			(
				"Ancestor ordering (finding 1)",
				"`get_ancestors()` ordered by `geo_level_order`, so a tree nested out of level order routed approvals to the wrong person.",
				"Fixed in 62007b3. Ordering is `lft` descending — tree position. Geo Node also refuses a parent that is not strictly shallower. Checks 3.11 and 3.12.",
			),
			(
				"Stale role authority (finding 2)",
				"A Geo Assignment granted scope and routing even after the user lost the role it named.",
				"Fixed in 62007b3. `GRANTS_AUTHORITY_SQL` requires the role still to be held. Checks 4.14 and 4.15.",
			),
			(
				"Mandatory logo (finding 3)",
				"National Society Settings could not be saved without an image, blocking all other configuration.",
				"Fixed in 62007b3. The logo is optional. Check 5.1b.",
			),
			(
				"The Kenyan time-zone example",
				"The unknown-time-zone error always read “Expected something like Africa/Nairobi”.",
				"Fixed. The example is the site's own System Settings zone. Check 5.4.",
			),
			(
				"Which role scopes a doctype",
				"A literal role name in the registering app's `hooks.py`.",
				"May now be a National Society Settings field instead — `role_from_setting`, added in be14a58. Checks 1.12, 4.16, 4.17, 5.7.",
			),
			(
				"The reference bench",
				"Nothing registered scopeable doctypes, affiliation providers or a capability resolver.",
				"vmmsx now registers two scopeable doctypes and two affiliation providers. Checks 0.4 and 0.5, and finding 1 below.",
			),
			(
				"Identity",
				"Red Profile held a name, an email, a phone and a login.",
				"It also holds the person-facts — gender, date of birth, nationality, citizenship, and a table of identity documents. Checks 2.13 to 2.16.",
			),
		],
	)

	g.para(
		"Where a check exists only to confirm a fix, it says so in its heading. Do not skip those: a"
		" regression in one of them is the most likely way this system breaks quietly."
	)

	# ------------------------------------------------------------------
	g.h1("How to use this document")
	g.para(
		"Each check states what is being verified, the exact commands to run, the expected result, and a"
		" box to tick. Where the reference run produced output worth comparing against, it is shown in"
		" green. Your identifiers (docnames, emails) will differ; the shapes and verdicts should not."
	)

	g.h2("Conventions")
	g.bullet(
		"“In the console” means bench's IPython shell: `bench --site vmms.localhost console`.",
		lead="Console.",
	)
	g.bullet(
		"“In the desk” means the browser UI at your site's `/app` URL, signed in as Administrator.",
		lead="Desk.",
	)
	g.bullet(
		"Shell commands run from the bench root, `/home/nigel/frappe/main-bench`, unless a `cd` is shown.",
		lead="Shell.",
	)

	g.h2("Four things about the console that will otherwise cost you an hour")
	g.bullet(
		"`bench console` registers a cleanup that calls `frappe.db.rollback()`. Anything you create and do"
		" not explicitly `frappe.db.commit()` disappears when you quit. This is a feature for this guide —"
		" you can run the whole thing and leave no trace — but it surprises people who go looking in the"
		" desk for a record they just made.",
		lead="The console rolls back when you exit.",
	)
	g.bullet(
		"MariaDB commits implicitly on DDL. Section 4 creates a stand-in DocType and a Custom Field; do"
		" that step first, or the identity and geography records you made earlier will be committed along"
		" with it and will need deleting by hand.",
		lead="Creating a DocType or a Custom Field commits everything before it.",
	)
	g.bullet(
		"Multi-line blocks pasted into IPython can misbehave. Save a snippet to a file and run"
		" `exec(open('/path/file.py').read(), globals())` — the `globals()` argument is not optional:"
		" without it, imports made inside the file are invisible to functions defined in it, and you will"
		" get confusing NameErrors.",
		lead="Paste long blocks from a file.",
	)
	g.bullet(
		"Red Profile, Geo Node, Geo Level, Geo Assignment, Affiliation Type and National Society Settings"
		" all ship with a single permission rule: System Manager. Identification Type is the one exception"
		" — it also grants read to All, because a user who could not read the vocabulary could not pick a"
		" document type on their own profile. A test user without System Manager sees nothing in the desk"
		" for the rest, and that is configuration, not a scoping decision.",
		lead="Read the desk permissions before blaming the code.",
	)

	g.h2("Cleaning up afterwards")
	g.para(
		"If you commit anything (or if a DDL step commits it for you), Appendix C has a teardown snippet"
		" that removes every artefact this guide creates. All fixture names are prefixed so nothing else is"
		" touched. It was run at the end of the reference pass and left the site with no Geo Level, Geo"
		" Node, Geo Assignment or Red Profile rows at all."
	)

	# ==================================================================
	g.h1("Section 0 — Preflight")
	g.para(
		"Five minutes that stop you debugging the wrong thing. Confirm you are testing the code you think you are."
	)

	g.check(
		"0.1",
		"You are on the right branch and commit",
		"That the working tree matches the code this guide was written against.",
	)
	g.code(
		"cd /home/nigel/frappe/main-bench/apps/onerc_core\n"
		"git branch --show-current\n"
		"git log -1 --oneline\n"
		"git status --short"
	)
	g.observed(
		"vmmsx-edition\n"
		"0e9ff8e chore(core): finalise doctype descriptions (dash-free) and remove desk-generated js cruft\n"
		" M onerc_core/hooks.py\n"
		" M onerc_core/identity/tests/fixtures.py\n"
		" M onerc_core/onerc_core/doctype/red_profile/red_profile.json\n"
		" M onerc_core/onerc_core/doctype/red_profile/red_profile.py\n"
		" M onerc_core/onerc_core/doctype/red_profile/test_red_profile.py\n"
		" M onerc_core/onerc_core/doctype/red_profile_affiliation/red_profile_affiliation.json\n"
		"?? docs/\n"
		"?? onerc_core/fixtures/identification_type.json\n"
		"?? onerc_core/onerc_core/doctype/identification_type/\n"
		"?? onerc_core/onerc_core/doctype/red_profile_identification/"
	)
	g.expected(
		bullets=[
			"Branch is `vmmsx-edition`.",
			"HEAD is `0e9ff8e` or a descendant — note the ref you actually tested.",
			"`git status` is **not** clean, and that is expected this time. The personal-identity work on"
			" Red Profile — the new fields, the `Identification Type` vocabulary and the"
			" `Red Profile Identification` table — is uncommitted, and section 2 covers it. If your tree is"
			" clean, checks 2.13 to 2.16 will not apply to you.",
		]
	)
	g.tickbox()

	g.check(
		"0.2",
		"The app is installed on the site and migrated",
		"That the site carries onerc_core's doctypes at their current definitions.",
	)
	g.code("bench --site vmms.localhost list-apps\nbench --site vmms.localhost migrate")
	g.observed(
		"frappe         17.x.x-develop (5299379) develop\n"
		"payments       0.0.1                    develop\n"
		"lms            2.45.2                   develop\n"
		"onerc_payments 0.0.1                    vmmsx-edition\n"
		"buzz           1.0.0                    main\n"
		"vmmsx          0.0.1                    vmmsx-edition\n"
		"onerc_core     0.0.1                    vmmsx-edition\n"
		"raven          2.8.11                   develop\n"
		"erpnext        17.x.x-develop (a30f3dd) develop\n"
		"hrms           17.0.0-dev               develop"
	)
	g.expected(
		"`onerc_core` appears in the list. `migrate` completes without a traceback. A migrate that reports"
		" nothing to do is a pass."
	)
	g.para(
		"Note what else is on this bench. It is not a clean single-app site, and section 0.5 is about what"
		" that changes."
	)
	g.tickbox()

	g.check(
		"0.3",
		"The automated suite runs",
		"The baseline. If this fails, stop — the manual checks below will only tell you the same thing more slowly.",
	)
	g.code("bench --site vmms.localhost run-tests --app onerc_core")
	g.observed(
		"Ran 321 tests in 22.477s\n"
		"\n"
		"FAILED (errors=5)\n"
		"\n"
		"ERROR  setUpClass (…national_society_settings.test_national_society_settings.TestBrandingIsOptional)\n"
		"ERROR  setUpClass (…national_society_settings.test_national_society_settings.TestTimeZoneValidation)\n"
		"ERROR  setUpClass (…geo_assignment.test_geo_assignment.TestGeoAssignment)\n"
		"ERROR  setUpClass (…geo_assignment.test_geo_assignment.TestGrantsAuthority)\n"
		"ERROR  setUpClass (…geo_assignment.test_geo_assignment.TestLiveness)\n"
		"\n"
		"frappe.exceptions.NameError: Year start date or end date is overlapping with\n"
		"Fiscal Year 2026-2027. To avoid please set company"
	)
	g.expected(
		bullets=[
			"321 tests pass. Access layer 135, identity 92, geography 62, society configuration 32.",
			"Five classes error in `setUpClass`, before any of their tests run. **This is a property of the"
			" bench, not of this app.** Frappe generates test records for every doctype a Link reaches, and"
			" on a site with ERPNext installed that chain reaches a Fiscal Year which collides with a real"
			" one. The Red Profile tests declare `IGNORE_TEST_RECORD_DEPENDENCIES` to step around it; these"
			" five have not been given the same treatment.",
			"Note what the five cover: the optional-logo change and the time-zone validation, and all three"
			" Geo Assignment classes — including `TestGrantsAuthority`, which is the automated half of"
			" finding 2. **Checks 4.14, 4.15 and 5.1b exercise those behaviours by hand instead.** Until the"
			" five run, the suite under-reports what is covered; record it as a gap.",
		]
	)
	g.para(
		"Coverage is uneven by design: the identity, geo, access and society modules are heavily tested;"
		" the CMS doctypes that predate this work (Article, Stakeholder, FAQ, Feedback, Region, SMS"
		" Campaign) have test files with no tests in them. Section 6 lists this."
	)
	g.tickbox()

	g.check(
		"0.4",
		"Which apps have registered themselves with core",
		"The three inversion hooks — and, this time, they are not all empty.",
	)
	g.code(
		"frappe.db.get_value('DocType', 'Red Profile', 'name')\n"
		"frappe.get_hooks('onerc_scopeable_doctypes')\n"
		"frappe.get_hooks('onerc_affiliation_providers')\n"
		"frappe.get_hooks('onerc_capability_resolver')"
	)
	g.observed(
		"'Red Profile'\n"
		"\n"
		"[{'doctype': 'VMMS Membership', 'geo_node_field': 'geo_node',\n"
		"  'role_from_setting': 'vmms_membership_scope_role'},\n"
		" {'doctype': 'VMMS Volunteer',  'geo_node_field': 'home_geo_node',\n"
		"  'role_from_setting': 'vmms_volunteer_scope_role'}]\n"
		"\n"
		"['vmmsx.member.affiliations.provide', 'vmmsx.volunteer.affiliations.provide']\n"
		"\n"
		"[]        # still no capability resolver anywhere"
	)
	g.expected(
		bullets=[
			"Red Profile exists.",
			"**Two of the three hooks are now populated**, because vmmsx is installed on this bench. The"
			" previous edition of this guide observed three empty lists and several of its checks depended"
			" on that; those checks have been rewritten.",
			"If your bench has no product app installed, all three come back empty and that is equally"
			" correct — it is the state core ships in. Note which case you are in, because it changes the"
			" expected results in checks 2.12, 4.12 and 4.17.",
			"Both scopeable registrations use `role_from_setting` rather than a literal `role`. That is the"
			" capability added in be14a58 and the subject of checks 1.12, 4.16 and 4.17.",
		]
	)
	g.tickbox()

	g.check(
		"0.5",
		"What the registered doctypes currently resolve to",
		"Whether the access layer on this bench is configured, or merely wired up.",
	)
	g.code(
		"from onerc_core.access.services import registry\n"
		"registry.scoped_doctypes()\n"
		"for name, reg in registry.registrations().items():\n"
		"    print(name, reg['role_from_setting'],\n"
		"          repr(frappe.db.get_single_value('National Society Settings',\n"
		"                                          reg['role_from_setting'])),\n"
		"          registry.resolve_role(reg))\n"
		"\n"
		"from onerc_core.access.services.registry import UNRESOLVED_ROLE_LOG_TITLE\n"
		"frappe.db.count('Error Log', {'method': UNRESOLVED_ROLE_LOG_TITLE})"
	)
	g.observed(
		"['VMMS Membership', 'VMMS Volunteer']\n"
		"\n"
		"VMMS Membership vmms_membership_scope_role '' None\n"
		"VMMS Volunteer  vmms_volunteer_scope_role  '' None\n"
		"\n"
		"717"
	)
	g.expected(
		bullets=[
			"Both settings are **empty**, so neither role resolves, so every user without the System Manager"
			" bypass is denied both doctypes.",
			"The Error Log count is the alarm. Seven hundred entries is the design working exactly as"
			" intended — see the note below — but it is also a live configuration gap on this site. It is"
			" finding 1 in section 6.",
			"On a correctly configured site this count stops growing and both roles resolve to a real"
			" Frappe role. Record which you see.",
		]
	)
	g.callout(
		"observation",
		"OBSERVATION — This is the trap the design exists to close, caught in the act",
		"An unresolvable scope role denies everybody, and an empty list view looks exactly like “nobody has"
		" been granted anything yet”. So `resolve_role()` logs every failure under a fixed title and the"
		" caller fails closed, which is what makes a misconfiguration distinguishable from a legitimately"
		" empty scope. On this bench the alarm is ringing and nobody has answered it. Set"
		" `vmms_volunteer_scope_role` and `vmms_membership_scope_role` in National Society Settings and both"
		" the denials and the logging stop.",
	)
	g.tickbox()

	# ==================================================================
	g.h1("Section 1 — The configurability check")
	g.para(
		"This is the point of the system, so it is checked first and hardest. The claim under test is"
		" narrow and falsifiable: no source file in onerc_core makes a decision that depends on a word one"
		" particular National Society happens to use. Not “County”, not “Ward”, not “County Coordinator”,"
		" not Kenya. Society-specific words may appear in prose, in help text and in test fixtures; they"
		" may not appear in logic."
	)

	g.h2("How to classify a hit")
	g.para(
		"Every grep below will return hits. A hit is not a defect — what matters is whether the string reaches executable code. Use this table for every hit you find."
	)
	g.table(
		["Class", "Looks like", "Verdict"],
		[
			(
				"Prose",
				'Inside a `#` comment or a `"""docstring"""`. Explains a rule, gives an example.',
				"Acceptable. Prose does not execute.",
			),
			(
				"Help text",
				"A `description`, `label` or placeholder in a doctype `.json`.",
				"Acceptable. Shown to an administrator as guidance; changing it changes nothing but the hint.",
			),
			(
				"Test fixture",
				"Under a `tests/` directory or in a `test_*.py` file.",
				"Acceptable. Fixtures must name something; a test that used only abstract names would prove less.",
			),
			(
				"Seed data",
				"A `fixtures` entry in `hooks.py`, or a `default` on a field in `.json`.",
				"Acceptable only if an administrator can change it afterwards. Record what it seeds.",
			),
			(
				"Framework role",
				"“System Manager”, “Administrator”, “Guest”, “All”.",
				"Acceptable, and the documented exemption. These are Frappe primitives, not society roles.",
			),
			(
				"Logic",
				"A literal that is assigned, compared, passed as an argument, or used as a dict key at runtime.",
				"DEFECT. This is what the check exists to find.",
			),
		],
	)

	g.check(
		"1.1",
		"Society words in Python, outside tests",
		"That no non-test Python file uses a society-specific word in executable code.",
	)
	g.code(
		"cd /home/nigel/frappe/main-bench/apps/onerc_core\n"
		"grep -rniE 'county|coordinator|ward|kenya|province|district|nairobi|kiambu' \\\n"
		"  --include='*.py' onerc_core/ | grep -v '/tests/' | grep -v 'test_'"
	)
	g.observed(
		"33 hits. Every one of them is one of:\n"
		"  • a copyright header      api/article.py:1  '# Copyright (c) 2026, Kenya Red Cross Society'\n"
		'  • a docstring example     geo/services/adapter.py:159  \'… "Region", "County", "Ward"\'\n'
		"  • a docstring example     geo_node.py:22  '… (Kihara in Kiambu, Kihara in Nairobi)'\n"
		"  • a comment               scope.py:45  '… Volunteer Approver, Branch Coordinator'\n"
		"  • the word 'upward'       approvers.py:41,80,92,109  ('ward' matches inside 'upward')\n"
		"  • a docstring saying the  national_society_settings.py:110\n"
		"    Kenyan example is gone  'hardcoded \"Africa/Nairobi\", which reads as an instruction…'"
	)
	g.expected(
		bullets=[
			"Every hit falls in the Prose class. There is no longer any exception.",
			"Note the false positives: ‘ward’ matches inside ‘upward’ and ‘towards’. Read each hit; do not count them.",
			"No hit is an assignment, comparison or argument.",
		]
	)
	g.callout(
		"resolved",
		"RESOLVED — the one Kenyan string that reached user-facing output is gone",
		"The previous edition recorded that `national_society_settings.py` built the unknown-time-zone error"
		" with `frappe.bold('Africa/Nairobi')`, so every society that mistyped a zone was shown a Kenyan"
		" example. It now calls `time_zone_example()`, which reads the site's own System Settings zone and"
		" falls back to the shape `Region/City`. The only remaining occurrence of the string is the"
		" docstring explaining why it was removed. Check 5.4 shows the new message.",
	)
	g.tickbox()

	g.check(
		"1.2",
		"Society words in doctype JSON",
		"That schema files carry society words only as administrator help text, never as defaults or options.",
	)
	g.code(
		"grep -rniE 'county|coordinator|ward|kenya|province|district|nairobi' --include='*.json' onerc_core/"
	)
	g.observed(
		'geo_level.json:64        "description": "eg. Region, County, District etc"\n'
		'national_society_settings.json:323  "description": "IANA name, eg. Africa/Nairobi"\n'
		'geo_assignment.json:71   "description": "… eg. an acting coordinator …"\n'
		'geo_node.json:68         "description": "The actual name of the place eg. Nairobi, Kampala"'
	)
	g.expected(
		bullets=[
			"Exactly four hits, all on the `description` key — the grey hint under a field on the form.",
			"None is on `default`, `options`, or `fetch_from`.",
			"Confirm the key name yourself: a hit on `default` would be seed data and a hit on `options`"
			" would be a fixed vocabulary, both of which need judging.",
		]
	)
	g.tickbox()

	g.check(
		"1.3",
		"No hardcoded country, currency or time zone default in the schema",
		"That a fresh install does not arrive pre-set to one country's answers.",
	)
	g.code(
		"grep -rnE '\"default\": *\"(KES|Kenya|USD|Africa/[A-Za-z_]+)\"' --include='*.json' onerc_core/\n"
		"\n"
		"# then, in the console, ask the schema rather than the data:\n"
		"meta = frappe.get_meta('National Society Settings')\n"
		"[(f, meta.get_field(f).default) for f in ('country','currency','time_zone','primary_language')]"
	)
	g.observed(
		"(the grep returns nothing)\n[('country', None), ('currency', None), ('time_zone', None), ('primary_language', None)]"
	)
	g.expected(
		"The grep returns nothing and every default is `None`. Country, currency, time zone and language are unset in code and must be chosen per site."
	)
	g.callout(
		"observation",
		"OBSERVATION — Your site probably still answers “Kenya” — that is data, not code",
		"On the reference bench `get_ui_config()['society']['country']` returns `'Kenya'`. It comes from a"
		" stored row in the Singles table and from System Settings, which the site was created with. Prove"
		" the distinction yourself: the field's schema default is `None`, while"
		" `frappe.db.get_single_value('National Society Settings', 'country')` is `'Kenya'`. Code clean,"
		" site configured. Do not confuse the two — it is the single easiest way to mis-read this section.",
	)
	g.tickbox()

	g.h2("The mechanical scan")
	g.para(
		"Greps find words. The scan below finds something stricter: string constants that reach executable"
		" code and match something a society actually named — a live Role, a live Geo Level, a live Geo"
		" Node. It parses every file rather than reading lines, so docstrings are excluded automatically"
		" and comments never appear at all. The script is in Appendix A; save it and run it in the console."
	)

	g.check(
		"1.4",
		"No society-named role, level or node reaches executable code",
		"The central claim of the whole system, tested mechanically rather than by eye.",
	)
	g.code(
		"# save Appendix A as /tmp/scan_hardcoding.py, then in the console:\nexec(open('/tmp/scan_hardcoding.py').read(), globals())"
	)
	g.observed(
		"matching against 72 roles, 0 levels, 0 nodes\n"
		"\n"
		"A. live ROLE names: 8 hit(s)\n"
		"  access/services/scope.py:48        'System Manager'\n"
		"  access/services/scope.py:61        'Administrator'\n"
		"  api/article.py:112,169             'Guest'\n"
		"  api/feedback.py:29,77              'Guest', 'System Manager'\n"
		"  feedback/doctype/feedback:14,25    'Guest'\n"
		"B. live GEO LEVEL names: 0 hit(s)\n"
		"C. live GEO NODE names:  0 hit(s)\n"
		"D. other society words:  0 hit(s)\n"
		"\n"
		"VERDICT\n"
		"society role names in logic : none\n"
		"geo level names in logic    : none\n"
		"geo node names in logic     : none\n"
		"framework roles (exempt)    : ['Administrator', 'Guest', 'System Manager']",
	)
	g.label("Second run, after section 3 has built a Zone / Sector / Cell hierarchy:")
	g._block(
		"matching against 72 roles, 6 levels, 3 nodes\n"
		"\n"
		"A. live ROLE names: 8 hit(s)          (identical — the same eight framework roles)\n"
		"B. live GEO LEVEL names: 0 hit(s)\n"
		"C. live GEO NODE names:  0 hit(s)\n"
		"D. other society words:  0 hit(s)",
		OBSERVED_FILL,
		GREEN_INK,
		before=2,
	)
	g.expected(
		bullets=[
			"Sections B, C and D are empty on both runs.",
			"Section A contains only framework roles. Any other role name is a defect — the script prints"
			" them separately under “society role names in logic”, which must read `none`.",
		]
	)
	g.para(
		"**Run this check twice.** The first run, on a site with no geo data, compares against an empty set"
		" of level and node names — B and C pass vacuously and prove nothing. Come back after section 3 has"
		" created Zone / Sector / Cell and re-run it; only then are B and C meaningful. The script prints"
		" the size of each set it is matching against for exactly this reason. Both runs are shown above."
	)
	g.tickbox()

	g.check(
		"1.5",
		"The one hardcoded role in logic is the documented exemption",
		"That the single role name the access layer knows is a Frappe primitive, not a society role.",
	)
	g.code(
		"grep -rn 'UNRESTRICTED_ROLES' --include='*.py' onerc_core/ | grep -v tests\n"
		"\n"
		"from onerc_core.access.services import scope\n"
		"scope.UNRESTRICTED_ROLES\n"
		"scope.has_unrestricted_scope('Administrator')"
	)
	g.observed(
		'access/services/scope.py:48  UNRESTRICTED_ROLES = ("System Manager",)\n'
		"access/services/scope.py:64  return bool(set(UNRESTRICTED_ROLES) & set(frappe.get_roles(user)))\n"
		"\n"
		"('System Manager',)\n"
		"True"
	)
	g.expected(
		"`UNRESTRICTED_ROLES` is exactly `('System Manager',)`, sits behind a comment that names it as the"
		" deliberate exception, and is used in one place. Society roles reach the layer only as arguments."
	)
	g.tickbox()

	g.check(
		"1.6",
		"Nothing assumes a level called “County” exists",
		"The question asked directly: is there a controller, service or doctype that expects that word?",
	)
	g.code(
		"grep -rn 'County' --include='*.py' --include='*.json' onerc_core/ | grep -v '/tests/' | grep -v test_"
	)
	g.observed(
		'geo/services/adapter.py:159   (docstring: \'… hierarchy labels — "Region", "County", "Ward"\')\n'
		"geo_node.py:54                (docstring: '… so a County could be filed under a Ward')\n"
		'geo_level.json:64             ("description": "eg. Region, County, District etc")'
	)
	g.expected(
		bullets=[
			"Two docstrings and one field description. No code path.",
			"Cross-check with 1.4 section B, which matches level names against the live Geo Level table and returns nothing.",
			"Answer to record: no. Level identity is a Geo Level docname chosen by the society; the adapter"
			" joins to `geo_level_order` for ordering and never to a name.",
		]
	)
	g.tickbox()

	g.check(
		"1.7",
		"Nothing assumes a role called “County Coordinator” exists",
		"The same question for roles — the more dangerous case, because approval routing resolves against roles.",
	)
	g.code(
		"grep -rniE 'coordinator|approver' --include='*.py' onerc_core/ | grep -v '/tests/' | grep -v test_"
	)
	g.observed(
		'access/services/registry.py:16   "role": "Volunteer Approver",   <- inside the docstring showing\n'
		"                                                            an app how to register a doctype\n"
		"access/services/scope.py:45      # … society-specific roles — Volunteer Approver, Branch Coordinator\n"
		"geo_assignment.py:165            # … an acting coordinator serving twice\n"
		"hooks.py:365,370                 # the same worked example, commented out"
	)
	g.expected(
		bullets=[
			"Docstring examples and comments. Nothing executable.",
			"`resolve_approvers(geo_node, role, rule)` takes the role as an argument; the argument comes from configuration in the product app.",
			"Answer to record: no.",
		]
	)
	g.tickbox()

	g.check(
		"1.8",
		"A society with no counties: does anything break?",
		"The empirical version of 1.6 and 1.7 — run the whole system on a hierarchy that shares no vocabulary with Kenya, and see whether any layer notices.",
	)
	g.para(
		"This is not a separate procedure: it is sections 3 and 4, which deliberately build a Zone / Sector"
		" / Cell hierarchy and run identity, geography, scoping and approver routing on top of it. Perform"
		" them, then return here and record the verdict."
	)
	g.observed(
		"Sections 3 and 4 on the reference bench, on Zone(1) > Sector(2) > Cell(3):\n"
		"  adapter.get_full_path(cell)      -> 'Riverside — Alpha Sector — Northern Zone'\n"
		"  adapter.level_labels()           -> [{'key':'GUIDE-1','name':'Zone','order':1,'is_lowest':0},\n"
		"                                       {'key':'GUIDE-2','name':'Sector','order':2, …},\n"
		"                                       {'key':'GUIDE-3','name':'Cell','order':3, …}]\n"
		"  scope.get_user_geo_scope(user_a) -> 2 nodes (its sector + the cell under it)\n"
		"  resolve_approvers(cell, role)    -> ['alpha_officer@guide.test']\n"
		"  list / read / guard              -> all three agree, no errors"
	)
	g.expected(
		"Every service works unchanged on level names that do not exist in Kenya. Nothing needed a “County”, and no code path was skipped for its absence."
	)
	g.para(
		"This is the strongest evidence in the document, because it does not depend on a grep pattern being"
		" well chosen. If a hidden assumption existed, a three-level hierarchy named Zone / Sector / Cell"
		" would have hit it."
	)
	g.tickbox()

	g.check(
		"1.9",
		"The geo boundary holds — only the adapter touches the tables",
		"That level and node identity cannot leak into other modules through a stray query.",
	)
	g.code(
		"grep -rn 'tabGeo Node\\|tabGeo Level' --include='*.py' onerc_core/ \\\n"
		"  | grep -v '/tests/' | grep -v 'geo/services/adapter.py' \\\n"
		"  | grep -v 'doctype/geo_node/' | grep -v 'doctype/geo_level/'"
	)
	g.observed("access/services/scope.py:174   (a comment, explaining that this module holds no such query)")
	g.expected(
		"One hit, and it is a comment. Every other module reaches geography through the adapter, which is"
		" what keeps the ordering rule and the level vocabulary in one file."
	)
	g.tickbox()

	g.check(
		"1.10",
		"Comparing against configuration is not the same as hardcoding",
		"That you can recognise the correct pattern, so a future reviewer does not “fix” it.",
	)
	g.code("sed -n '106,109p' onerc_core/access/services/approvers.py")
	g.observed(
		"def is_at_level(candidate: str) -> bool:\n"
		'        return adapter.get_level(candidate)["key"] == geo_level\n'
		"\n"
		"match = adapter.resolve_upward(geo_node, is_at_level)"
	)
	g.expected(
		bullets=[
			"This compares a node's level against `geo_level`, a value passed in by the caller from configuration.",
			"That is the pattern the system is built on. The defect would be `== 'County'` — a literal.",
			"When you review a hit from 1.1 or 1.4, this is the distinction to apply.",
		]
	)
	g.tickbox()

	g.check(
		"1.11",
		"The phone rule is configuration, and there is no regex in the code",
		"One of the named hard rules: no hardcoded phone pattern.",
	)
	g.code("grep -rnE 're\\.(compile|fullmatch|match|sub)' --include='*.py' onerc_core/ | grep -v tests")
	g.observed(
		"society/services/config.py:194     re.fullmatch(policy['pattern'], value)   <- the configured pattern\n"
		"national_society_settings.py:130   re.compile(self.phone_number_pattern)    <- validating the config\n"
		"national_society_settings.py:158   re.sub(r'[\\s-]+', '_', …)                <- key normalisation\n"
		"article.py:36,62                   re.sub(…)                                <- CMS slug and strip-tags"
	)
	g.expected(
		"No literal phone pattern anywhere. The only phone regex in the system is the one an administrator"
		" typed into National Society Settings. Check 5.6 proves it is actually enforced."
	)
	g.tickbox()

	g.check(
		"1.12",
		"NEW — even the role that scopes a doctype can be configuration",
		"The rule taken one step further than the previous edition tested it.",
	)
	g.para(
		"A registration used to name a Frappe role literally, in the source of whatever app owned the"
		" doctype. That is a society-specific word in an app's code — the same class of problem this whole"
		" section exists to find, one level up. A registration may now name a National Society Settings"
		" field whose **value** is the role instead."
	)
	g.code(
		"sed -n '30,67p' onerc_core/access/services/registry.py\n"
		"grep -rn 'role_from_setting' --include='*.py' onerc_core/ | grep -v tests | head\n"
		"\n"
		"# and what an owning app actually writes:\n"
		"frappe.get_hooks('onerc_scopeable_doctypes')"
	)
	g.observed(
		'registry.py:81    ROLE_SETTING_KEY = "role_from_setting"\n'
		"registry.py:172   def resolve_role(registration) -> str | None:\n"
		"registry.py:233   def settings_backed_registrations() -> list[dict]:\n"
		"\n"
		"[{'doctype': 'VMMS Membership', 'geo_node_field': 'geo_node',\n"
		"  'role_from_setting': 'vmms_membership_scope_role'},\n"
		" {'doctype': 'VMMS Volunteer',  'geo_node_field': 'home_geo_node',\n"
		"  'role_from_setting': 'vmms_volunteer_scope_role'}]"
	)
	g.expected(
		bullets=[
			"Exactly one of `role` and `role_from_setting` may be given; both, or neither, is refused — check 4.18.",
			"**Settings keys only.** Not a callable and not a dotted path: either would put an"
			" arbitrary-code-execution surface inside the access layer, reachable from a hook that any"
			" installed app can write. A settings fieldname can only ever name a role.",
			"Core ships no such field. The **product** app that registers the doctype owns the field too,"
			" and adds it as a Custom Field — core only resolves whatever fieldname was registered. Confirm"
			" that on your bench: `frappe.get_all('Custom Field', filters={'dt': 'National Society Settings'})`.",
			"A literal `role` still behaves identically. This is an addition, not a migration.",
		]
	)
	g.tickbox()

	g.h2("What is NOT built or covered here")
	g.para(
		"Read this before signing the section off. Everything below is outside what the checks above can prove — it is not a list of defects, it is the boundary of the evidence."
	)
	g.bullet(
		"The scan reads Python only. Society-specific strings in `.js` files, in translations, or in doctype `options` lists are not covered — 1.2 covers JSON by grep, which is weaker."
	)
	g.bullet(
		"A semantic assumption expressed without a literal is invisible to both grep and the scanner. One"
		" exists and is benign: `geo_level.py` defines `TOP_LEVEL_ORDER = 1`, meaning “order 1 is the top of"
		" the hierarchy”. That is a structural convention, not a society-specific one, but it is an assumption."
	)
	g.bullet(
		"Nothing here checks other apps. vmmsx, or any product app, can hardcode whatever it likes; run the"
		" same scan against it separately. That matters more than it did: vmmsx now supplies two"
		" registrations and the settings fields behind them."
	)
	g.bullet(
		"The scanner matches against roles, levels and nodes that exist on the site you run it on. On an empty site it under-reports — see the note on 1.4."
	)
	g.bullet(
		"Copyright headers reading “Kenya Red Cross Society” remain on the older CMS files. Provenance, not logic, but worth a decision if the app is ever published as multi-society."
	)

	# ==================================================================
	g.h1("Section 2 — Identity")
	g.para(
		"Red Profile is one record per party, ever. It is deliberately thin: who someone is, the"
		" person-facts that stay true whatever anyone does with them, and a derived index of what they are"
		" to the society. The affiliation table is an index, never a source of truth, and checks 2.5 to 2.12"
		" are mostly about proving that it cannot be written into by hand. Checks 2.13 to 2.16 cover the"
		" identity documents, which are new and uncommitted."
	)

	g.check(
		"2.1",
		"A profile's docname is opaque",
		"That the primary key carries no mutable data — not the email, not the name.",
	)
	g.code(
		"profile = frappe.get_doc({\n"
		"    'doctype': 'Red Profile', 'first_name': 'Asha', 'middle_name': 'Njeri',\n"
		"    'last_name': 'Wanjiru', 'email': '  ASHA.Wanjiru@Example.TEST  ',\n"
		"}).insert()\n"
		"profile.name, profile.email, profile.full_name, profile.user"
	)
	g.observed("('RP-00120', 'asha.wanjiru@example.test', 'Asha Njeri Wanjiru', None)")
	g.expected(
		bullets=[
			"The docname is `RP-‹digits›`. It is not the email and not derived from any field.",
			"The email is trimmed and lowercased on save — so uniqueness means what it looks like.",
			"`full_name` is composed for display; `user` is `None`, because not everyone with a profile can sign in.",
		]
	)
	g.tickbox()

	g.check(
		"2.2",
		"Email is the identifier, and it is unique",
		"That two profiles cannot share an email, including by letter case.",
	)
	g.code(
		"frappe.get_doc({'doctype':'Red Profile','first_name':'Dup','last_name':'Licate',\n"
		"                'email':'ASHA.WANJIRU@example.test'}).insert()"
	)
	g.observed(
		"UniqueValidationError: ('Red Profile', 'RP-00121',\n  IntegrityError(1062, \"Duplicate entry 'asha.wanjiru@example.test' for key 'email'\"))"
	)
	g.expected(
		"A duplicate-entry error. The address is lowercased before the unique index sees it, so a different-case address is the same address."
	)
	g.tickbox()

	g.check(
		"2.3",
		"An affiliation type that is gated must name its key",
		"That a read gate cannot be configured with no way to open it.",
	)
	g.code(
		"frappe.get_doc({'doctype':'Affiliation Type','affiliation_type_key':'guide_gate_no_key',\n"
		"                'affiliation_type_name':'Gate Without Key','requires_gated_read':1}).insert()"
	)
	g.observed("MandatoryError: Gating Capability is required when Requires Gated Read is set.")
	g.expected("Refused. A gate with no key would fail closed forever and look like a data problem.")
	g.tickbox()

	g.check(
		"2.4",
		"Create the two affiliation types this section needs",
		"Setup for everything below — one ordinary type, one gated.",
	)
	g.code(
		"for key, label, gated, cap in (\n"
		"    ('guide_volunteer', 'Guide Volunteer', 0, None),\n"
		"    ('guide_beneficiary', 'Guide Beneficiary', 1, 'view_beneficiaries'),\n"
		"):\n"
		"    if not frappe.db.exists('Affiliation Type', key):\n"
		"        frappe.get_doc({'doctype':'Affiliation Type','affiliation_type_key':key,\n"
		"                        'affiliation_type_name':label,'requires_gated_read':gated,\n"
		"                        'gating_capability':cap}).insert()"
	)
	g.expected(
		"Both insert. Note the docname of an Affiliation Type is its key — unlike Red Profile,"
		" configuration doctypes here are keyed by a stable identifier on purpose."
	)
	g.tickbox()

	g.check(
		"2.5",
		"set_affiliation is the only way a row appears",
		"That a satellite writes the index through the service, and the row records what owns it.",
	)
	g.code(
		"satellite = frappe.get_doc({'doctype':'ToDo','description':'stand-in satellite'}).insert()\n"
		"from onerc_core.identity.services.affiliation import set_affiliation\n"
		"set_affiliation(profile.name, 'guide_volunteer', 'Active', 'ToDo', satellite.name)\n"
		"[(r.affiliation_type, r.status, r.reference_doctype, r.reference_name)\n"
		" for r in frappe.get_doc('Red Profile', profile.name).affiliations]"
	)
	g.observed("'dtt4sps6m9'\n[('guide_volunteer', 'Active', 'ToDo', 'dtt4sps6m9')]")
	g.expected(
		"One row, carrying the type, the status and a pointer back to the record that owns the truth. ToDo"
		" stands in for a satellite; the service only requires that the referenced record exists."
	)
	g.tickbox()

	g.check(
		"2.6",
		"Writing the same claim twice touches nothing",
		"Idempotence — a satellite that re-syncs on every save must not churn the profile.",
	)
	g.code(
		"before = frappe.db.get_value('Red Profile', profile.name, 'modified')\n"
		"set_affiliation(profile.name, 'guide_volunteer', 'Active', 'ToDo', satellite.name)\n"
		"before == frappe.db.get_value('Red Profile', profile.name, 'modified')"
	)
	g.observed("True")
	g.expected("`True` — no save, no version row, no `modified` bump.")
	g.tickbox()

	g.check(
		"2.7",
		"Status cannot be written directly",
		"The core rule of the derived index: a write that did not come through the service is not applied.",
	)
	g.code(
		"tamper = frappe.get_doc('Red Profile', profile.name)\n"
		"tamper.affiliations[0].status = 'Ended'\n"
		"tamper.phone = ''            # an unrelated, legitimate edit in the same save\n"
		"tamper.save()\n"
		"frappe.db.get_value('Red Profile Affiliation',\n"
		"    {'parent': profile.name, 'affiliation_type': 'guide_volunteer'}, 'status')"
	)
	g.observed("'Active'")
	g.expected(
		"Still Active. The persisted rows are put back and the rest of the save proceeds — the unrelated edit to `phone` is kept."
	)
	g.para(
		"Note the asymmetry, and decide whether you are content with it: on an UPDATE the tampered rows are"
		" silently restored, with no error raised. That is deliberate — a reader whose gated rows were"
		" stripped on load will post the document back without them, and must not thereby delete rows they"
		" were never allowed to see. The cost is that a genuine programming error is also silent here. On"
		" an INSERT it throws instead (2.8)."
	)
	g.tickbox()

	g.check(
		"2.8",
		"Inline affiliations on a new profile are refused loudly",
		"The other half of 2.7 — on insert there is nothing to restore, so a mistake is an error.",
	)
	g.code(
		"frappe.get_doc({'doctype':'Red Profile','first_name':'Inline','last_name':'Rows',\n"
		"                'email':'inline.rows@example.test',\n"
		"                'affiliations':[{'affiliation_type':'guide_volunteer','status':'Active',\n"
		"                                 'reference_doctype':'ToDo','reference_name':satellite.name}]\n"
		"               }).insert()"
	)
	g.observed(
		"ValidationError: Affiliations cannot be set directly. Insert the profile first, then let the\n"
		"satellite record write its own row through set_affiliation()."
	)
	g.expected("Refused with an explanation of what to do instead.")
	g.tickbox()

	g.check(
		"2.9",
		"The affiliations grid is read-only, and the identifications grid is not",
		"That the UI agrees with the server rule — and that the two child tables differ on purpose.",
	)
	g.code(
		"frappe.get_meta('Red Profile').get_field('affiliations').read_only\n"
		"frappe.get_meta('Red Profile').get_field('identifications').read_only"
	)
	g.observed("1\n0")
	g.expected(
		bullets=[
			"In the desk at `/app/red-profile`, the Affiliations grid renders but cannot be edited: no Add Row, and the rows do not open.",
			"The Identifications grid **is** editable, and that is correct: those rows are typed in by whoever"
			" edits the profile. There is no service and no gate on them — see 2.13.",
		]
	)
	g.tickbox()

	g.check(
		"2.10",
		"A gated affiliation is hidden from a reader without the capability",
		"The most security-sensitive behaviour in this module: that someone is a beneficiary is itself sensitive.",
	)
	g.code(
		"ben = frappe.get_doc({'doctype':'ToDo','description':'beneficiary satellite'}).insert()\n"
		"set_affiliation(profile.name, 'guide_beneficiary', 'Active', 'ToDo', ben.name)\n"
		"\n"
		"from onerc_core.identity.services import read_gate\n"
		"frappe.get_hooks('onerc_capability_resolver')\n"
		"[r['affiliation_type'] for r in read_gate.get_affiliations(profile.name)]\n"
		"[r.affiliation_type for r in frappe.get_doc('Red Profile', profile.name).affiliations]\n"
		"\n"
		"doc = frappe.get_doc('Red Profile', profile.name); doc.run_method('onload')\n"
		"[r.affiliation_type for r in doc.affiliations]\n"
		"read_gate.is_visible('guide_beneficiary'), read_gate.is_visible('guide_volunteer')\n"
		"read_gate.gated_capabilities()"
	)
	g.observed(
		"[]                                        # no capability resolver is installed anywhere\n"
		"['guide_volunteer']                       # the service read — gated row removed\n"
		"['guide_volunteer', 'guide_beneficiary']  # raw get_doc — trusted server-side, NOT gated\n"
		"['guide_volunteer']                       # after onload — the desk path, gated row removed\n"
		"(False, True)\n"
		"{'guide_beneficiary': 'view_beneficiaries'}"
	)
	g.expected(
		bullets=[
			"`get_affiliations()` and the desk's `onload` path both drop the beneficiary row.",
			"`frappe.get_doc()` does not — and must not be used on any path whose result reaches a user. That is the boundary the service exists to hold.",
			"With no capability resolver installed, the gate is closed to everyone including Administrator. That is fail-closed working, not a bug.",
		]
	)
	g.tickbox()

	g.check(
		"2.11",
		"… and it opens for a reader who does hold the capability",
		"The other side of the gate, which cannot otherwise be demonstrated on this bench.",
	)
	g.para(
		"Nothing on the bench implements `onerc_capability_resolver`, so the open case needs a stand-in."
		" This patches the resolver for the current console session only — it changes no file and does not"
		" survive the session."
	)
	g.code(
		"original = read_gate._resolver\n"
		"read_gate._resolver = lambda: (lambda user, capability: capability == 'view_beneficiaries')\n"
		"read_gate.is_visible('guide_beneficiary')\n"
		"[r['affiliation_type'] for r in read_gate.get_affiliations(profile.name)]\n"
		"read_gate._resolver = original          # put it back\n"
		"read_gate.is_visible('guide_beneficiary')"
	)
	g.observed("True\n['guide_volunteer', 'guide_beneficiary']\nFalse")
	g.expected(
		"With a resolver that grants the capability, the row appears; restore the resolver and it vanishes again. The gate is a gate, not a permanent hide."
	)
	g.tickbox()

	g.check(
		"2.12",
		"rebuild_affiliations leaves rows no provider owns",
		"That core can never wipe an index it has no way to rebuild — and, now, that it does discover real providers.",
	)
	g.code(
		"from onerc_core.identity.services.affiliation import rebuild_affiliations\n"
		"frappe.get_hooks('onerc_affiliation_providers')\n"
		"rebuild_affiliations(profile.name)"
	)
	g.observed(
		"['vmmsx.member.affiliations.provide', 'vmmsx.volunteer.affiliations.provide']\n"
		"\n"
		"{'providers': 2, 'owned_doctypes': ['VMMS Member', 'VMMS Volunteer'],\n"
		" 'claimed': 0, 'written': 0, 'removed': 0,\n"
		" 'unclaimed': ['guide_volunteer', 'guide_beneficiary'], 'changed': False}"
	)
	g.expected(
		bullets=[
			"`removed` is 0 and `changed` is `False` — nothing was touched.",
			"**Two providers are now discovered**, where the previous edition observed zero. They declare"
			" ownership of `VMMS Member` and `VMMS Volunteer`; both doctypes exist on this bench.",
			"Both of this guide's rows are still reported as `unclaimed`: no registered provider owns `ToDo`,"
			" so core leaves them alone rather than assuming the satellite is gone. That is the property"
			" worth confirming — a provider appearing does not put unrelated rows at risk.",
			"The removal path still has not run against a real satellite here, because neither provider"
			" claimed anything for this profile. Exercising it needs a real VMMS Volunteer record and belongs"
			" to vmmsx's own verification.",
		]
	)
	g.tickbox()

	g.h2("Identity documents — new, and uncommitted at the time of writing")
	g.para(
		"Red Profile used to hold `passport_number`, `id_number` and `id_document_type` flat on the person."
		" That shape could record one document and never said which of the three fields the type applied"
		" to; somebody holding both a national ID and a passport had to lose one. It is now a child table,"
		" `Red Profile Identification`, typed by a `Identification Type` vocabulary the society owns. If"
		" your working tree is clean, skip to section 3."
	)

	g.check(
		"2.13",
		"A profile carries its person-facts and its documents",
		"That the spine holds what stays true about a person, and that the documents are a list.",
	)
	g.code(
		"p = frappe.get_doc({'doctype':'Red Profile','first_name':'Asha','last_name':'Wanjiru',\n"
		"                    'email':'asha.docs@example.test','gender':'Female',\n"
		"                    'nationality':'Kenya','date_of_birth':'1994-03-17',\n"
		"                    'citizenship_status':'Citizen',\n"
		"                    'identifications':[\n"
		"                        {'id_type':'national_id','id_number':'  12345678  ','is_primary':1},\n"
		"                        {'id_type':'passport','id_number':'AK0912345'}]}).insert()\n"
		"\n"
		"(p.name, p.full_name, p.gender, p.nationality, str(p.date_of_birth), p.citizenship_status)\n"
		"[(r.id_type, r.id_number, bool(r.is_primary)) for r in p.identifications]"
	)
	g.observed(
		"('RP-00123', 'Asha Wanjiru', 'Female', 'Kenya', '1994-03-17', 'Citizen')\n"
		"[('national_id', '12345678', True), ('passport', 'AK0912345', False)]"
	)
	g.expected(
		bullets=[
			"Every one of the personal fields is optional and none is conditionally required. A profile is"
			" created at registration with a first name, a last name and an email; whichever affiliation"
			" process needs more asks for it then.",
			"`id_number` is trimmed on save — by the **parent**, not by the row's own controller. Frappe runs"
			" `validate` on the document being saved, not on its children, so a guard written on"
			" `RedProfileIdentification` would never fire. Confirm the trim happened.",
			"`gender`, `nationality` and `preferred_language` are Links to framework vocabularies, never"
			" Selects — a society can edit them.",
		]
	)
	g.tickbox()

	g.check(
		"2.14",
		"At most one document may be primary",
		"The one rule worth refusing: whoever asks which document to quote must get an answer, not a choice.",
	)
	g.code("p.append('identifications', {'id_type':'passport','id_number':'P7777','is_primary':1})\np.save()")
	g.observed("ValidationError: Only one identification may be marked Is Primary.")
	g.expected(
		"Refused, naming the field. No primary at all is fine — the rule is at-most-one, not exactly-one."
	)
	g.tickbox()

	g.check(
		"2.15",
		"Two documents of the same type are allowed",
		"That the table did not simply re-create the flat fields with extra steps.",
	)
	g.code(
		"frappe.get_doc({'doctype':'Red Profile','first_name':'Dual','last_name':'National',\n"
		"                'email':'dual.national@example.test',\n"
		"                'identifications':[{'id_type':'passport','id_number':'AA111'},\n"
		"                                   {'id_type':'passport','id_number':'BB222'}]}).insert()"
	)
	g.observed("[('passport', 'AA111'), ('passport', 'BB222')]")
	g.expected(
		"Both rows accepted. Dual nationality means two passports, and a register that could not hold both"
		" would be back where it started. This is deliberate, not an oversight in the validation."
	)
	g.tickbox()

	g.check(
		"2.16",
		"The document vocabulary is seeded, editable and readable by everyone",
		"That “which documents does this society recognise” is data, not a code change.",
	)
	g.code(
		"sorted(frappe.get_all('Identification Type', pluck='name'))\n"
		"frappe.get_all('Identification Type', filters={'is_active':1}, pluck='identification_type_name')\n"
		"[(p.role, p.read, p.write) for p in frappe.get_meta('Identification Type').permissions]\n"
		"\n"
		"frappe.get_doc({'doctype':'Identification Type','identification_type_key':'guide_card',\n"
		"                'identification_type_name':'  Guide Card  '}).insert().name"
	)
	g.observed(
		"['alien_id', 'driving_licence', 'national_id', 'passport']\n"
		"['Alien ID', 'Driving Licence', 'National ID', 'Passport']\n"
		"[('System Manager', 1, 1), ('All', 1, 0)]\n"
		"'guide_card'"
	)
	g.expected(
		bullets=[
			"Four types arrive seeded from `hooks.py` fixtures — not from a Select's `options`, which would"
			" have made the list a code change. The fixtures entry filters by key so a society's own"
			" additions are never exported back over the seeded set.",
			"A society may add its own and deactivate any of the four. An inactive type stays on records that already carry it.",
			"**Read is granted to All**, alongside full rights for System Manager. A user who could not read"
			" the vocabulary could not pick a document type on their own profile. This is the one doctype in"
			" the foundation that is not System-Manager-only; satisfy yourself that is what you want.",
			"The name is trimmed on save. That is the whole controller — a vocabulary this simple has nothing else to enforce.",
			"**Nothing in the app branches on a key.** Grep for `national_id` outside tests and fixtures: adding “Refugee Card” needs no code at all.",
		]
	)
	g.tickbox()

	g.h2("What is NOT built or covered here")
	g.para(
		"Read this before signing the section off. Everything below is outside what the checks above can prove — it is not a list of defects, it is the boundary of the evidence."
	)
	g.bullet(
		"No app anywhere implements `onerc_capability_resolver`. Everything gated is invisible to everyone until one does; 2.11 proves the mechanism, not a working deployment."
	)
	g.bullet(
		"Two affiliation providers are now registered, but neither claimed anything in this run, so the"
		" removal path in `rebuild_affiliations` still has not executed against a live satellite here."
	)
	g.bullet(
		"Identity resolution is email-only. There is no fuzzy matching, no merge, no de-duplication tooling, and phone is not unique. Two records for one human are prevented only by the email index."
	)
	g.bullet(
		"Nothing validates an identity document. `id_number` is free text: no checksum, no format rule per"
		" type, no uniqueness. Two profiles may carry the same national ID number and nothing complains."
	)
	g.bullet(
		"Red Profile permissions are System Manager only, and Red Profile is not registered as geo-scopeable — profiles are not scoped by `home_geo_node`."
	)
	g.bullet(
		"The sensitive set — blood group, medical notes, next of kin — is deliberately not on the spine. It is intended to arrive later as a separate, gated extension; nothing here tests that because nothing here implements it."
	)
	g.bullet(
		"The affiliation status vocabulary (Active / Inactive / Pending / Suspended / Ended) is a fixed Select on the child doctype. It is core's vocabulary, not a society's, and a society cannot extend it."
	)

	# ==================================================================
	g.h1("Section 3 — Geography")
	g.para(
		"Build a hierarchy whose level names exist in no Red Cross society you know, then run every adapter"
		" function against it. If the geography layer has an opinion about what a place is called, this"
		" section finds it. Checks 3.11 and 3.12 confirm the fix to finding 1 of the previous edition."
	)

	g.check(
		"3.1",
		"Create three levels with deliberately foreign names",
		"That level vocabulary is data. Zone / Sector / Cell — no county, no ward, nothing Kenyan.",
	)
	g.code(
		"zone = frappe.get_doc({'doctype':'Geo Level','geo_level_key':'GUIDE-1','geo_level_name':'Zone',\n"
		"                       'geo_level_order':1,'requires_parent':0,'is_active':1}).insert()\n"
		"sector = frappe.get_doc({'doctype':'Geo Level','geo_level_key':'GUIDE-2','geo_level_name':'Sector',\n"
		"                         'geo_level_order':2,'requires_parent':1,'is_active':1}).insert()\n"
		"cell = frappe.get_doc({'doctype':'Geo Level','geo_level_key':'GUIDE-3','geo_level_name':'Cell',\n"
		"                       'geo_level_order':3,'requires_parent':1,'is_active':1}).insert()"
	)
	g.observed("('GUIDE-1', 'GUIDE-2', 'GUIDE-3')      # the docnames are the keys")
	g.expected("Three levels, ordered 1–3. Deeper means a higher order number.")
	g.para(
		"You can leave `geo_level_order` out entirely: a new level is pre-filled with the rung below the deepest active one (check 3.13). The explicit numbers above are kept so the rest of this section has something predictable to talk about."
	)
	g.para(
		"Leave `is_lowest_level` at 0 for now. Flagging it no longer throws when another level already carries it — the marker moves — and check 3.9 is where that is exercised deliberately."
	)
	g.tickbox()

	g.check(
		"3.2",
		"Build the tree, and confirm node docnames are opaque",
		"That a node's key carries no name and no level.",
	)
	g.code(
		"def node(label, level, parent=None, group=False):\n"
		"    return frappe.get_doc({'doctype':'Geo Node','geo_node_name':label,'geo_level':level,\n"
		"                           'parent_geo_node':parent,'is_group':int(group)}).insert()\n"
		"\n"
		"north       = node('Northern Zone', zone.name, None, True)\n"
		"alpha       = node('Alpha Sector',  sector.name, north.name, True)\n"
		"beta        = node('Beta Sector',   sector.name, north.name, True)\n"
		"riverside_a = node('Riverside',     cell.name, alpha.name)\n"
		"riverside_b = node('Riverside',     cell.name, beta.name)\n"
		"north.name, alpha.name, riverside_a.name"
	)
	g.observed("('GEO-00001', 'GEO-00002', 'GEO-00004')")
	g.expected("`GEO-‹digits›`. Not ‘ward-riverside’, not ‘GUIDE-3-Riverside’.")
	g.tickbox()

	g.check(
		"3.3",
		"Two places with the same name coexist under different parents",
		"The case that opaque docnames were adopted for. Riverside exists in both sectors.",
	)
	g.code(
		"adapter.get_full_path(riverside_a.name)\nadapter.get_full_path(riverside_b.name)\nriverside_a.name, riverside_b.name"
	)
	g.observed(
		"'Riverside — Alpha Sector — Northern Zone'\n'Riverside — Beta Sector — Northern Zone'\n('GEO-00004', 'GEO-00005')"
	)
	g.expected("Both exist, with distinct keys and distinct paths.")
	g.tickbox()

	g.check(
		"3.4",
		"… but two siblings with the same name are refused",
		"That ambiguity is prevented exactly where it would be genuinely ambiguous.",
	)
	g.code("node('Riverside', cell.name, alpha.name)")
	g.observed(
		"ValidationError: A Geo Node named Riverside already exists under GEO-00002 (GEO-00004).\nSibling names must be unique."
	)
	g.expected(
		"Refused, case-insensitively and ignoring surrounding whitespace. The same name under a different parent stays legal."
	)
	g.tickbox()

	g.check(
		"3.5",
		"Every adapter function, on a hierarchy it has never seen",
		"The functional core of the geography layer.",
	)
	g.code(
		"from onerc_core.geo.services import adapter\n"
		"adapter.get_root_regions()\n"
		"adapter.get_children(north.name)\n"
		"adapter.get_descendants(north.name)\n"
		"adapter.get_level(alpha.name)\n"
		"adapter.level_labels()\n"
		"adapter.is_leaf(riverside_a.name), adapter.is_leaf(north.name)\n"
		"adapter.get_full_path(riverside_a.name)"
	)
	g.observed(
		"[{'name':'GEO-00001','geo_node_name':'Northern Zone', … 'lft':1,'rgt':10,'geo_level_order':1}]\n"
		"['Alpha Sector', 'Beta Sector']            # direct children only, alphabetical\n"
		"4 nodes                                    # whole subtree, any depth\n"
		"{'key':'GUIDE-2','name':'Sector','order':2,'is_lowest':0}\n"
		"[{'key':'GUIDE-1','name':'Zone','order':1,'is_lowest':0},\n"
		" {'key':'GUIDE-2','name':'Sector','order':2,'is_lowest':0},\n"
		" {'key':'GUIDE-3','name':'Cell','order':3,'is_lowest':0}]\n"
		"(True, False)\n"
		"'Riverside — Alpha Sector — Northern Zone'"
	)
	g.expected(
		bullets=[
			"`get_root_regions` returns parentless nodes — not ‘level order 1’ nodes. The distinction matters:"
			" level order is renumberable configuration, the parent link is structural.",
			"`level_labels` is what a UI renders as its hierarchy labels; it is entirely society data.",
			"`is_leaf` reads the nested-set bounds, not the `is_group` flag, so it cannot drift from reality.",
		]
	)
	g.tickbox()

	g.check(
		"3.6",
		"Ancestors come back nearest-first",
		"The contract every upward walk depends on — including approver routing.",
	)
	g.code("[(a.geo_node_name, a.geo_level_order) for a in adapter.get_ancestors(riverside_a.name)]")
	g.observed("[('Alpha Sector', 2), ('Northern Zone', 1)]")
	g.expected(
		"Immediate parent first, root last. **Ordering is `ORDER BY lft DESC` — tree position — not"
		" `geo_level_order`.** That changed in 62007b3; checks 3.11 and 3.12 are where it matters."
	)
	g.tickbox()

	g.check(
		"3.7", "Containment, in both directions", "`matches_scope`, which the enforcement layer relies on."
	)
	g.code(
		"adapter.matches_scope(riverside_a.name, north.name)\n"
		"adapter.matches_scope(riverside_a.name, beta.name)\n"
		"adapter.matches_scope(riverside_a.name, beta.name, allow_ancestor=False)\n"
		"adapter.resolve_upward(riverside_a.name, lambda n: adapter.get_level(n)['key'] == zone.name)"
	)
	g.observed("True\nFalse\nFalse\n'GEO-00001'")
	g.expected(
		bullets=[
			"A cell is within its zone's scope; it is not within a sibling sector's.",
			"`resolve_upward` is the generic “walk up until X” primitive; here it finds the nearest Zone-level ancestor. Approver routing is built on this.",
		]
	)
	g.tickbox()

	g.check(
		"3.8", "A level that requires a parent gets one", "Server-side enforcement of the level's own policy."
	)
	g.code("node('Orphan Sector', sector.name, None)")
	g.observed("MandatoryError: Parent Geo Node is required for a Geo Node at level GUIDE-2")
	g.expected(
		"Refused. The rule lives on Geo Level, per society, and is enforced on the server rather than by a form condition."
	)
	g.tickbox()

	g.check(
		"3.9",
		"The lowest marker moves rather than blocking",
		"That deepening a hierarchy is one edit, and that at-most-one-active-lowest still holds afterwards.",
	)
	g.code(
		"cell.is_lowest_level = 1; cell.save()          # GUIDE-3, order 3\n"
		"\n"
		"block = frappe.get_doc({'doctype':'Geo Level','geo_level_key':'GUIDE-4','geo_level_name':'Block',\n"
		"                        'geo_level_order':4,'is_lowest_level':1,'requires_parent':1}).insert()\n"
		"\n"
		"frappe.db.get_value('Geo Level', 'GUIDE-3', 'is_lowest_level')\n"
		"frappe.get_all('Geo Level', filters={'is_active':1,'is_lowest_level':1}, pluck='name')"
	)
	g.observed(
		"Lowest Level Moved: GUIDE-3 is no longer the lowest level. GUIDE-4 is.\n"
		"0\n"
		"['GUIDE-4']"
	)
	g.expected(
		"No refusal. GUIDE-4 takes the marker and GUIDE-3 loses it in the same save.",
		bullets=(
			"At-most-one-active-lowest is now the *result* of the move rather than a rule enforced by"
			" throwing. Exactly one active level carries the flag afterwards.",
			"Previously this threw, and adding a deeper tier meant finding and clearing the incumbent by"
			" hand before the new row would save at all.",
			"Inactive levels are exempt on both sides: a retired tier keeps its flag and neither claims"
			" the marker nor loses it. Set `is_active = 0` on one and re-run to see it left alone.",
		),
	)
	g.para(
		"Mark a level lowest while a deeper one exists and you get an additional warning — *Lowest Is Not"
		" The Deepest* — which does not block either. Order is guidance, and a society may genuinely have"
		" stopped registering records at its deepest tier without retiring the level."
	)
	g.tickbox()

	g.check(
		"3.10",
		"Renaming and relabelling a level",
		"That neither the key nor the display name is load-bearing anywhere.",
	)
	g.code(
		"frappe.rename_doc('Geo Level', 'GUIDE-2', 'GUIDE-2B', force=True)\n"
		"frappe.db.get_value('Geo Node', alpha.name, 'geo_level')\n"
		"\n"
		"lvl = frappe.get_doc('Geo Level', 'GUIDE-2B')\n"
		"lvl.geo_level_name = 'Département'; lvl.save()\n"
		"adapter.get_level(alpha.name)\n"
		"adapter.get_full_path(riverside_a.name)"
	)
	g.observed(
		"'GUIDE-2B'                                              # the node's link followed the rename\n"
		"{'key':'GUIDE-2B','name':'Département','order':2,'is_lowest':0}\n"
		"'Riverside — Alpha Sector — Northern Zone'              # paths use node names, unaffected"
	)
	g.expected(
		bullets=[
			"Renaming the key cascades to every Geo Node link (Frappe updates link fields on rename).",
			"Relabelling the display name changes what the adapter reports and nothing else — a society can rename ‘Sector’ to ‘Département’ with no consequence.",
		]
	)
	g.para(
		"Worth recording as a deliberate deviation from the opaque-docname rule: Geo Level, Affiliation Type"
		" and Identification Type are keyed by a data field, unlike Red Profile and Geo Node. For"
		" configuration vocabularies that is the point — the key is how config is referenced, and rename"
		" cascades, as just shown. Records *about* people and places get opaque IDs; the vocabularies they"
		" are filed under get keys."
	)
	g.tickbox()

	g.callout(
		"resolved",
		"RESOLVED — finding 1 of the previous edition is closed, in both halves",
		"Then: nothing stopped a hierarchy being nested out of level order, and `get_ancestors()` ordered by"
		" `geo_level_order` descending rather than by tree depth, so an out-of-order tree yielded an"
		" out-of-order answer and approver routing resolved to the wrong person. Now: Geo Node refuses a"
		" parent that is not at a strictly shallower level (3.11), **and** the adapter orders ancestry by"
		" `lft` descending (3.12). Both halves were fixed, deliberately — level order is configuration a"
		" society can renumber, and rows written before the rule existed are still on disk. If the two ever"
		" disagree, the tree is the truth.",
	)

	g.check(
		"3.11",
		"CONFIRMS A FIX — the malformed parent is refused at the point of entry",
		"That the tree can no longer be nested out of level order in the first place.",
	)
	g.code(
		"root_zone = node('Root Zone', zone.name, None,           True)\n"
		"mid_cell  = node('Mid Cell',  cell.name, root_zone.name, True)\n"
		"node('Inner Zone', zone.name, mid_cell.name, True)          # a Zone under a Cell"
	)
	g.observed(
		"ValidationError: GEO-00009 is at level GUIDE-3 (order 3), which is not above level GUIDE-1\n"
		"(order 1). A Geo Node's parent must sit at a shallower level than the node itself."
	)
	g.expected(
		bullets=[
			"Refused, naming both levels and both orders. Under the previous code this insert succeeded silently.",
			"Order 1 is the top of the hierarchy, so “shallower” means a **lower** order number.",
			"If either level is unreadable — a Link to a level that has gone, or a level saved with no order"
			" — the rule stands aside rather than throwing. Whatever wrote that is already broken, and a"
			" comparison against `None` would raise a `TypeError` instead of saying anything useful.",
		]
	)
	g.tickbox()

	g.check(
		"3.12",
		"CONFIRMS A FIX — a legacy inverted row still walks in tree order",
		"The half that matters most: rows written before the rule existed are still on disk, and the adapter must not trust the level ladder.",
	)
	g.para(
		"The validation in 3.11 stops new bad rows, so the only way to reproduce the old shape is to plant"
		" it — build the node at a level the rule accepts, then rewrite the level underneath it. That is"
		" what `geo/tests/fixtures.py` does, and what the automated test"
		" `TestAncestorOrderFollowsTheTree` runs against."
	)
	g.code(
		"# Root Zone(1) > Mid Cell(3) > Inner Zone(1) > Leaf Cell(3)\n"
		"root_zone  = node('Root Zone',  'GUIDE-1', None,            True)\n"
		"mid_cell   = node('Mid Cell',   'GUIDE-3', root_zone.name,  True)\n"
		"inner_zone = node('Inner Zone', 'GUIDE-4', mid_cell.name,   True)   # accepted: 4 under 3\n"
		"frappe.db.set_value('Geo Node', inner_zone.name, 'geo_level', 'GUIDE-1',\n"
		"                    update_modified=False)                          # now it is a Zone again\n"
		"leaf = node('Leaf Cell', 'GUIDE-3', inner_zone.name)\n"
		"\n"
		"[a.geo_node_name for a in adapter.get_ancestors(leaf.name)]\n"
		"adapter.get_full_path(leaf.name)\n"
		"resolve_approvers(leaf.name, role)     # holders at Inner Zone and at Mid Cell"
	)
	g.observed(
		"true parent chain, nearest first : ['Inner Zone', 'Mid Cell', 'Root Zone']\n"
		"adapter.get_ancestors(leaf)      : ['Inner Zone', 'Mid Cell', 'Root Zone']    <- CORRECT\n"
		"with their level orders          : [('Inner Zone', 1), ('Mid Cell', 3), ('Root Zone', 1)]\n"
		"adapter.get_full_path(leaf)      : 'Leaf Cell — Inner Zone — Mid Cell — Root Zone'\n"
		"resolve_approvers(leaf, role)    : ['inner@ord.test']                         <- the nearest holder"
	)
	g.expected(
		bullets=[
			"The ancestors come back in **tree** order even though the level orders read 1, 3, 1 — which is"
			" the whole point. Under the previous code this returned `['Mid Cell', 'Inner Zone', 'Root Zone']`.",
			"`resolve_approvers` picks the holder at Inner Zone, the leaf's actual parent. Under the previous"
			" code it walked past them to Mid Cell.",
			"If you want to see the old behaviour, put `ORDER BY lvl.geo_level_order DESC` back in"
			" `adapter.get_ancestors` — it breaks seven tests, and the control tests keep passing.",
		]
	)
	g.tickbox()

	g.check(
		"3.13",
		"A new level suggests its own order",
		"That the common single-society case never requires counting rows and typing a number.",
	)
	g.code(
		"from onerc_core.onerc_core.doctype.geo_level.geo_level import next_available_order\n"
		"next_available_order()\n"
		"\n"
		"nxt = frappe.get_doc({'doctype':'Geo Level','geo_level_key':'GUIDE-5',\n"
		"                      'geo_level_name':'Street'}).insert()   # no order given\n"
		"nxt.geo_level_order"
	)
	g.observed("5\n5")
	g.expected(
		"The blank order is filled with the rung below the deepest active level.",
		bullets=(
			"It is a **default, not a rule**: pass an explicit order and it is left exactly as given, which"
			" is what lets a society insert a tier between two existing ones.",
			"Zero counts as blank — the field's guidance starts at 1, so there is no rung 0 anybody meant.",
			"An inactive level frees its number: deactivate the deepest and the suggestion drops back.",
			"It is a `before_insert`, so re-saving an existing level never renumbers it.",
			"The desk form pre-fills the same value through `next_available_order`, so a new level arrives"
			" with the number already in the field.",
		),
	)
	g.tickbox()

	g.check(
		"3.14",
		"A reused order warns and does not block",
		"That a duplicated rung is reported without forbidding the multi-society case.",
	)
	g.code(
		"twin = frappe.get_doc({'doctype':'Geo Level','geo_level_key':'GUIDE-6',\n"
		"                       'geo_level_name':'Province','geo_level_order':1}).insert()\n"
		"twin.geo_level_order   # saved anyway"
	)
	g.observed(
		"Order Already In Use: GUIDE-1 is also at order 1. If they belong to different\n"
		"hierarchies that is expected and nothing is wrong...\n"
		"1"
	)
	g.expected(
		"A message, and a saved row.",
		bullets=(
			"**This must never become a throw.** Two societies on one site each number their own ladder"
			" from 1, and consuming apps build exactly that shape in their fixtures to prove the engine"
			" holds no opinion about a hierarchy. A site-wide unique order would forbid it outright.",
			"There is no unique index on `geo_level_order` and there is not meant to be one.",
			"When both levels already carry nodes under a common root, the message stops hedging and says"
			" *in the same hierarchy* — that is a fact about the tree, which is the only thing entitled"
			" to settle a structural question. Until nodes exist, neither reading can be established and"
			" the wording says so.",
		),
	)
	g.tickbox()

	g.check(
		"3.15",
		"The top of the ladder is derived, not stored",
		"That there is no third answer to where the hierarchy begins.",
	)
	g.code(
		"adapter.top_levels()\n"
		"adapter.is_top_level('GUIDE-1')\n"
		"adapter.hierarchy_overview()\n"
		"frappe.get_meta('Geo Level').get_field('is_highest_level')"
	)
	g.observed(
		"[{'key': 'GUIDE-1', 'name': 'Zone', 'order': 1, 'is_lowest': 0}, ...]\n"
		"True\n"
		"[{'key': 'GUIDE-1', ..., 'is_top': True, 'shares_order_with': ['GUIDE-6']}, ...]\n"
		"None"
	)
	g.expected(
		"The shallowest active level is reported as the top, and no field stores it.",
		bullets=(
			"`top_levels()` is **plural** on purpose: with two ladders on one site, more than one level"
			" legitimately sits on the shallowest rung, and returning a list says so instead of picking"
			" one and looking authoritative.",
			"`hierarchy_overview()` is what the Geo Level form draws, through `onload`. It marks the top,"
			" the lowest, which levels require a parent, and any shared rungs.",
			"Add a shallower level and re-run: what is reported as the top moves, with nothing to keep in"
			" step, because it was never stored.",
		),
	)
	g.para(
		"**Two notions of “top”, reconciled here rather than in code.** `get_root_regions()`"
		" answers *structurally* — a node with no parent — and that is what routing, scoping and"
		" ancestry are built on. `top_levels()` answers about *configuration*: what this society calls its"
		" shallowest rung. On a well-formed site they describe the same tier. If they ever disagree, **the"
		" tree is the truth and the ladder is the label that needs correcting** — which is why no"
		" `is_highest` flag exists to become a third opinion."
	)
	g.tickbox()

	g.check(
		"3.16",
		"Skipping a rung warns; contradicting the ladder still refuses",
		"That a valid tree is never rejected for tidiness, and a genuine contradiction still is.",
	)
	g.code(
		"# a Cell (order 3) filed straight under a Zone (order 1)\n"
		"skipped = frappe.get_doc({'doctype':'Geo Node','geo_node_name':'Orphan Cell',\n"
		"                          'geo_level':'GUIDE-3','parent_geo_node':alpha.name}).insert()\n"
		"\n"
		"# and the contradiction, for contrast\n"
		"frappe.get_doc({'doctype':'Geo Node','geo_node_name':'Upside Down',\n"
		"                'geo_level':'GUIDE-1','parent_geo_node':riverside_a.name}).insert()"
	)
	g.observed(
		"A Level Was Skipped: ... a rung has been skipped. That is allowed...\n"
		"(saved)\n"
		"\n"
		"ValidationError: ... A Geo Node's parent must sit at a shallower level than the node itself."
	)
	g.expected(
		"The skip warns and saves. The contradiction still throws.",
		bullets=(
			"They are different mistakes. A parent at the same or a deeper level is a contradiction with"
			" no reading under which it is what somebody meant.",
			"A parent two rungs up is merely unusual: a district with no sub-district, a city that is its"
			" own county, a national programme registering straight under the country. Refusing it would"
			" reject the real tree in favour of an idealised ladder.",
			"Strict adjacency is therefore **not** enforced, and is a candidate for a per-society setting"
			" if a society asks for one. See the boundary list below.",
		),
	)
	g.tickbox()

	g.check(
		"3.17",
		"The parent check says when it cannot run",
		"That a broken ladder cannot switch the guard off in silence.",
	)
	g.code(
		"# delete a level out from under nodes that still point at it\n"
		"frappe.db.sql(\"DELETE FROM `tabGeo Level` WHERE name = 'GUIDE-1'\")\n"
		"\n"
		"frappe.get_doc({'doctype':'Geo Node','geo_node_name':'After The Fall',\n"
		"                'geo_level':'GUIDE-2','parent_geo_node':alpha.name}).insert()\n"
		"\n"
		"frappe.get_all('Error Log', filters={'method':['like','%parent-level check skipped%']},\n"
		"               pluck='name')"
	)
	g.observed("(saved)\n['<an Error Log row>']")
	g.expected(
		"The node saves and an Error Log row records that the check stood down, naming the node and the"
		" unreadable level.",
		bullets=(
			"Logged rather than thrown: the tree is already written, and refusing would punish whoever"
			" touches a node next for a level somebody else removed.",
			"Previously this returned in silence, which is indistinguishable from a check that passed.",
			"The reachable cause is a level that has **gone**. `geo_level_order` is a mandatory Int, so"
			" its column is NOT NULL and a surviving row cannot carry a blank one.",
		),
	)
	g.tickbox()

	g.h2("What is NOT built or covered here")
	g.para(
		"Read this before signing the section off. Everything below is outside what the checks above can prove — it is not a list of defects, it is the boundary of the evidence."
	)
	g.bullet(
		"`geo_code` is free text and not unique: two nodes can carry the same official code with no complaint."
	)
	g.bullet(
		"There is no import tooling. A real hierarchy (thousands of nodes) has to be loaded by script; nothing in core does it, and nothing validates a bulk load."
	)
	g.bullet(
		"There is no archive, merge or move-with-history story for nodes. Frappe's nested set will re-parent a node, but nothing records that a place was renamed or absorbed."
	)
	g.bullet(
		"The parent-is-shallower rule fires on save. It does **not** re-check the tree when a Geo Level's"
		" `geo_level_order` is later renumbered, so a society that reorders its ladder can still end up with"
		" rows that would now be refused. The adapter tolerates that by design — 3.12 is exactly that case —"
		" but nothing reports it."
	)
	g.bullet(
		"Deactivating a Geo Level (`is_active = 0`) hides it from `level_labels` but does nothing to nodes already at that level; they keep working. Decide whether that is what you want."
	)
	g.bullet(
		"**Strict adjacency is not enforced.** A node may be filed more than one rung above its own level;"
		" 3.16 warns and saves. Whether a society wants that refused is a policy question, and the obvious"
		" next step is a per-society setting rather than a rule imposed on everybody. It is deliberately"
		" not built."
	)
	g.bullet(
		"**`geo_level_order` is not unique and must not become unique.** 3.14 is the reason. There is no"
		" index and no constraint; a collision is reported and allowed. Anything that needs a single"
		" ordered ladder should scope its own query, not tighten the schema."
	)
	g.bullet(
		"The duplicate-order warning can only say *which* reading applies once both levels carry nodes."
		" While a ladder is still being written down it reports that it cannot tell, which is honest but"
		" is not detection."
	)

	# ==================================================================
	g.h1("Section 4 — Access and scoping")
	g.para(
		"The security spine. Roles answer what a user may do; Geo Assignment answers where. Three"
		" enforcement layers read one scope service, and this section tests all three against the same"
		" arrangement — because a list view that filters correctly while the detail view leaks is not access"
		" control."
	)
	g.para(
		"**Order matters here.**  Do the DDL step (4.1) FIRST. Creating a DocType and a Custom Field commits the transaction, which would otherwise commit everything you built in sections 2 and 3."
	)

	g.check(
		"4.1",
		"Create the stand-in scopeable doctype, the role and the settings field",
		"Setup. Core must not name a product doctype, so the tests register one of their own; you will do the same.",
	)
	g.code(
		"if not frappe.db.exists('Role', 'Guide Volunteer Approver'):\n"
		"    frappe.get_doc({'doctype':'Role','role_name':'Guide Volunteer Approver','desk_access':1}).insert()\n"
		"\n"
		"frappe.get_doc({'doctype':'DocType','name':'Guide Scoped Record','module':'Onerc Core',\n"
		"    'custom':1,'autoname':'hash',\n"
		"    'fields':[{'fieldname':'title','fieldtype':'Data','label':'Title','reqd':1},\n"
		"              {'fieldname':'home_geo_node','fieldtype':'Link','options':'Geo Node','label':'Geo Node'}],\n"
		"    'permissions':[{'role':r,'read':1,'write':1,'create':1,'delete':1,'report':1}\n"
		"                   for r in ('System Manager','Guide Volunteer Approver')]}).insert()\n"
		"\n"
		"# the field an owning app would add for role_from_setting — needed by 4.16 and 4.17\n"
		"frappe.get_doc({'doctype':'Custom Field','dt':'National Society Settings',\n"
		"                'fieldname':'guide_scope_role','label':'Guide Scope Role',\n"
		"                'fieldtype':'Data','insert_after':'phone_number_example'}).insert()"
	)
	g.expected(
		"Both are created. Everything you did earlier in this console session is now committed — Appendix C's teardown will clean it up."
	)
	g.para(
		"Then build the same Zone / Sector / Cell tree as section 3: `Northern Zone` with `Alpha Sector` and `Beta Sector` beneath it, and a `Riverside` cell under each."
	)
	g.tickbox()

	g.check(
		"4.2",
		"Two users, two different places",
		"The arrangement the whole section turns on: same role, different nodes.",
	)
	g.code(
		"def user(handle):\n"
		"    email = f'{handle}@guide.test'\n"
		"    if frappe.db.exists('User', email): frappe.delete_doc('User', email, force=True)\n"
		"    frappe.get_doc({'doctype':'User','email':email,'first_name':handle,'send_welcome_email':0,\n"
		"                    'user_type':'System User','roles':[{'role':'Guide Volunteer Approver'}]}).insert()\n"
		"    frappe.clear_cache(user=email); return email\n"
		"\n"
		"user_a = user('alpha_officer')      # authority at Alpha Sector\n"
		"user_b = user('beta_officer')       # authority at Beta Sector\n"
		"user_c = user('unassigned_officer') # the role, and no authority anywhere\n"
		"\n"
		"for u, n in ((user_a, alpha), (user_b, beta)):\n"
		"    frappe.get_doc({'doctype':'Geo Assignment','user':u,'role':'Guide Volunteer Approver',\n"
		"                    'geo_node':n,'is_active':1}).insert()"
	)
	g.expected(
		"Three users hold the same Frappe role. Two have a Geo Assignment; one has none. That third user is the fail-closed case."
	)
	g.tickbox()

	g.check("4.3", "Records in every corner of the tree", "Including one with no geo node at all.")
	g.code(
		"records = {}\n"
		"for label, geo in (('alpha',alpha), ('riverside_a',riverside_a), ('beta',beta),\n"
		"                   ('riverside_b',riverside_b), ('north',north)):\n"
		"    records[label] = frappe.get_doc({'doctype':'Guide Scoped Record',\n"
		"                                     'title':f'guide {label}','home_geo_node':geo}).insert().name\n"
		"records['unplaced'] = frappe.get_doc({'doctype':'Guide Scoped Record',\n"
		"                                      'title':'guide unplaced'}).insert().name"
	)
	g.expected(
		"Six records. The unplaced one exists only to prove that an unplaced record is inside nobody's scope."
	)
	g.tickbox()

	g.check(
		"4.4",
		"Register the doctype as scopeable",
		"The inversion: core provides the engine, the owning app declares what is scoped.",
	)
	g.para(
		"For a console session, patch the registry directly. This affects only this process — nothing on disk changes:"
	)
	g.code(
		"from onerc_core.access.services import registry, scope, enforcement\n"
		"REG = {'Guide Scoped Record': {'doctype':'Guide Scoped Record',\n"
		"                               'geo_node_field':'home_geo_node',\n"
		"                               'role':'Guide Volunteer Approver'}}\n"
		"original_registrations = registry.registrations\n"
		"registry.registrations = lambda: REG\n"
		"registry.for_doctype('Guide Scoped Record')"
	)
	g.observed(
		"{'doctype': 'Guide Scoped Record', 'geo_node_field': 'home_geo_node', 'role': 'Guide Volunteer Approver'}"
	)
	g.expected(
		"The registration resolves. Note this uses a literal `role`; 4.16 repeats the whole arrangement with `role_from_setting` instead."
	)
	g.tickbox()

	g.check("4.5", "Scope is the node plus its subtree, and nothing else", "The definition of authority.")
	g.code(
		"s_a = scope.get_user_geo_scope(user_a, 'Guide Volunteer Approver')\n"
		"len(s_a), {alpha, riverside_a} <= s_a, beta in s_a\n"
		"scope.get_user_geo_scope(user_c, 'Guide Volunteer Approver')\n"
		"scope.get_user_geo_scope(user_a, 'Some Other Role')"
	)
	g.observed(
		"(2, True, False)      # Alpha Sector + the cell beneath it; Beta Sector excluded\n"
		"set()                 # no assignment -> nothing. Fail closed.\n"
		"set()                 # the role argument is load-bearing"
	)
	g.expected(
		bullets=[
			"`user_a` gets their node and its descendants — two nodes.",
			"`user_c` gets an empty set. Empty must be read as ‘sees nothing’, never as ‘unfiltered’.",
			"Asking with a different role returns nothing: ‘where may I approve volunteers’ and ‘where may I view members’ are different questions.",
		]
	)
	g.tickbox()

	g.check("4.6", "Layer 1 — the list query", "That a list view shows only what the user may see.")
	g.code(
		"enforcement.get_permission_query_conditions(user_a, 'Guide Scoped Record')\n"
		"enforcement.get_permission_query_conditions(user_c, 'Guide Scoped Record')\n"
		"\n"
		"for u in (user_a, user_b, user_c):\n"
		"    frappe.set_user(u)\n"
		"    listed[u] = set(frappe.get_list('Guide Scoped Record', pluck='name', limit_page_length=0))\n"
		"frappe.set_user('Administrator')"
	)
	g.observed(
		"\"`tabGuide Scoped Record`.`home_geo_node` IN ('GEO-00002', 'GEO-00004')\"\n"
		"'1=0'                                     # matches no row — not an empty string\n"
		"\n"
		"user_a sees alpha + riverside_a  -> True\n"
		"user_a sees beta                 -> False\n"
		"user_a sees the unplaced record  -> False\n"
		"user_b sees beta + riverside_b   -> True\n"
		"user_c sees                      -> set()"
	)
	g.expected(
		bullets=[
			"`user_a`'s condition is an `IN` over their two nodes; `user_c`'s is `1=0`.",
			"The unplaced record is invisible to everyone — an `IN` excludes NULL, and that is intended.",
			"`1=0` rather than `''` matters: an empty string would mean ‘no filter’, the exact inversion of an empty scope.",
		]
	)
	g.tickbox()

	g.check(
		"4.7",
		"Layer 2 — the document read",
		"The hole a list filter cannot close: a guessed docname or a bookmarked URL.",
	)
	g.code(
		"for label in ('alpha', 'riverside_a', 'beta'):\n"
		"    doc = frappe.get_doc('Guide Scoped Record', records[label])\n"
		"    print(label,\n"
		"          frappe.has_permission('Guide Scoped Record', doc=doc, user=user_a, ptype='read'),\n"
		"          frappe.has_permission('Guide Scoped Record', doc=doc, user=user_b, ptype='read'))"
	)
	g.observed("alpha        True   False\nriverside_a  True   False\nbeta         False  True")
	g.expected(
		"Each user can read their own subtree and not the other's. This is the check that makes the list filter access control rather than cosmetics."
	)
	g.tickbox()

	g.check(
		"4.8",
		"Layer 3 — the API guard",
		"For custom endpoints that assemble their own response and never touch the desk permission layer.",
	)
	g.code(
		"def guarded(u, name):\n"
		"    try:\n"
		"        enforcement.guard('Guide Scoped Record', name, user=u); return 'permitted'\n"
		"    except frappe.PermissionError:\n"
		"        return 'PermissionError'\n"
		"\n"
		"guarded(user_a, records['alpha'])\n"
		"guarded(user_a, records['beta'])\n"
		"guarded(user_c, records['alpha'])\n"
		"guarded(user_a, 'no-such-record')"
	)
	g.observed(
		"'permitted'\n'PermissionError'\n'PermissionError'\n'PermissionError'        # a record that does not exist is refused, not reported missing"
	)
	g.expected(
		bullets=[
			"The guard agrees with the other two layers on every record.",
			"A non-existent name raises `PermissionError` rather than `DoesNotExist` — deliberate, so a caller"
			" outside the scope cannot map the tree by watching which names answer differently. Verify you"
			" consider that the right trade-off.",
		]
	)
	g.tickbox()

	g.check("4.9", "The three layers never disagree", "The property worth more than any single check.")
	g.code(
		"for label, name in records.items():\n"
		"    doc = frappe.get_doc('Guide Scoped Record', name)\n"
		"    for u in (user_a, user_b, user_c):\n"
		"        in_list = name in listed[u]\n"
		"        can_read = frappe.has_permission('Guide Scoped Record', doc=doc, user=u, ptype='read')\n"
		"        ok = guarded(u, name) == 'permitted'\n"
		"        assert in_list == can_read == ok, (label, u, in_list, can_read, ok)\n"
		"print('all three layers agree on every record')"
	)
	g.observed("all three layers agree on every record")
	g.expected(
		"The assertion passes with no output but the final line. Any row where the list hides something the document read permits — or the reverse — is a defect."
	)
	g.tickbox()

	g.check(
		"4.10",
		"Approver routing walks up to the right person",
		"The routing question, which reads the same table as scope so the two cannot contradict each other.",
	)
	g.code(
		"from onerc_core.access.services.approvers import resolve_approvers, RULE_AT_LEVEL\n"
		"resolve_approvers(riverside_a, 'Guide Volunteer Approver')\n"
		"resolve_approvers(riverside_b, 'Guide Volunteer Approver')\n"
		"resolve_approvers(north, 'Guide Volunteer Approver')\n"
		"resolve_approvers(riverside_a, 'Guide Volunteer Approver', rule=RULE_AT_LEVEL, geo_level='GUIDE-1')"
	)
	g.observed(
		"['alpha_officer@guide.test']     # walked up from the cell to Alpha Sector\n"
		"['beta_officer@guide.test']      # same rule, different arrangement, different person\n"
		"[]                               # nobody holds the role at the zone or above it\n"
		"[]                               # at_level: nobody holds it AT zone level either"
	)
	g.expected(
		bullets=[
			"The walk stops at the first node upward with a holder — nearest wins.",
			"Authority does not flow downward: a holder at Alpha Sector does not answer for the zone above.",
			"An empty list is a legitimate answer. Core will not invent a fallback approver; what an unapprovable record means is the product's decision.",
		]
	)
	g.tickbox()

	g.check(
		"4.11",
		"A dead assignment grants nothing, and time travel works",
		"Liveness is defined once, in the Geo Assignment controller, and every reader uses it.",
	)
	g.code(
		"from frappe.utils import add_days, today\n"
		"frappe.get_doc({'doctype':'Geo Assignment','user':user_c,'role':'Guide Volunteer Approver',\n"
		"                'geo_node':north,'is_active':1,'valid_to':add_days(today(), -1)}).insert()\n"
		"\n"
		"resolve_approvers(north, 'Guide Volunteer Approver')\n"
		"resolve_approvers(north, 'Guide Volunteer Approver', on_date=add_days(today(), -30))\n"
		"scope.get_user_geo_scope(user_c, 'Guide Volunteer Approver')"
	)
	g.observed(
		"[]                                    # expired yesterday — grants nothing today\n"
		"['unassigned_officer@guide.test']     # … but it did, thirty days ago\n"
		"set()                                 # and it grants no read scope either"
	)
	g.expected(
		"The expired assignment is invisible today and visible on a date when it was live. Routing and scope agree."
	)
	g.tickbox()

	g.check(
		"4.12",
		"With nothing registered, the engine is completely inert",
		"The shipped state of core standing alone.",
	)
	g.code(
		"registry.registrations = original_registrations      # undo the patch from 4.4\n"
		"enforcement.get_permission_query_conditions(user_a, 'Guide Scoped Record')\n"
		"guarded(user_c, records['alpha'])"
	)
	g.observed("''            # no condition at all\n'permitted'   # no opinion — NOT 'deny'")
	g.expected(
		bullets=[
			"An **unregistered** doctype gets an empty condition and a permitted guard. `Guide Scoped Record`"
			" is unregistered again once the patch is undone, so this holds even on a bench where vmmsx has"
			" registered doctypes of its own.",
			"This is the correct behaviour, and it is the state core ships in: nothing is geo-scoped until an"
			" app declares it. Installing onerc_core alone scopes nothing.",
			"Do not confuse “no opinion” with “allow”. Those two are the same answer here only because a"
			" doctype nobody registered is not this layer's business.",
		]
	)
	g.tickbox()

	g.check(
		"4.13",
		"The unrestricted bypass is exactly what it claims",
		"That the escape hatch is one framework role and is not accidentally wider.",
	)
	g.code(
		"scope.has_unrestricted_scope('Administrator')\nscope.has_unrestricted_scope(user_a)\nscope.UNRESTRICTED_ROLES"
	)
	g.observed("True\nFalse\n('System Manager',)")
	g.expected(
		"Administrator and System Manager bypass; a society role holder does not. The bypass never consults an assignment at all."
	)
	g.tickbox()

	g.callout(
		"resolved",
		"RESOLVED — finding 2 of the previous edition is closed",
		"Then: `resolve_approvers()` and `get_user_geo_scope()` read Geo Assignment alone, so revoking"
		" somebody's role did **not** revoke their approval routing — they kept being resolved as the"
		" approver for their node until the assignment itself was deactivated. Now: what an assignment"
		" grants is defined once, as `GRANTS_AUTHORITY_SQL` in the Geo Assignment controller, and it is two"
		" halves — the row is live **and** the user still holds the Frappe role the row names, checked"
		" against `tabHas Role`. Either half of an off-boarding now fully revokes, everywhere, immediately."
		" Checks 4.14 and 4.15 reproduce it.",
	)

	g.check(
		"4.14",
		"CONFIRMS A FIX — removing the role revokes everywhere, at once",
		"That off-boarding by role removal alone is now sufficient.",
	)
	g.code(
		"from onerc_core.onerc_core.doctype.geo_assignment.geo_assignment import grants_authority, is_live\n"
		"ga = frappe.db.get_value('Geo Assignment',\n"
		"                         {'user':user_a,'role':'Guide Volunteer Approver','geo_node':alpha}, 'name')\n"
		"\n"
		"grants_authority(ga), is_live(ga)\n"
		"resolve_approvers(riverside_a, 'Guide Volunteer Approver')\n"
		"len(scope.get_user_geo_scope(user_a, 'Guide Volunteer Approver'))\n"
		"\n"
		"u = frappe.get_doc('User', user_a)                       # strip the role, leave the row alone\n"
		"u.set('roles', [r for r in u.roles if r.role != 'Guide Volunteer Approver'])\n"
		"u.save(); frappe.clear_cache(user=user_a)\n"
		"\n"
		"grants_authority(ga), is_live(ga)\n"
		"resolve_approvers(riverside_a, 'Guide Volunteer Approver')\n"
		"len(scope.get_user_geo_scope(user_a, 'Guide Volunteer Approver'))\n"
		"enforcement.get_permission_query_conditions(user_a, 'Guide Scoped Record')\n"
		"guarded(user_a, records['alpha'])"
	)
	g.observed(
		"before — grants_authority, is_live : (True, True)\n"
		"before — resolve_approvers         : ['alpha_officer@guide.test']\n"
		"before — scope size                : 2\n"
		"\n"
		"role still held                    : False\n"
		"\n"
		"after  — grants_authority, is_live : (False, True)      <- the row is still LIVE, and grants nothing\n"
		"after  — resolve_approvers         : []\n"
		"after  — scope size                : 0\n"
		"after  — list condition            : '1=0'\n"
		"after  — guard on their own record : PermissionError\n"
		"\n"
		"role restored — scope size         : 2"
	)
	g.expected(
		bullets=[
			"`(False, True)` is the whole fix in one line: the assignment row is untouched and still live,"
			" and it grants nothing. `is_live()` remains available on its own because “is this row still"
			" current” is a fair question — but `grants_authority()` is the one worth asking.",
			"All four readers agree instantly: routing, scope, the list filter and the guard. Nothing caches"
			" a scope and the role check reads `tabHas Role` directly, so there is no window.",
			"Restoring the role restores the scope. Nothing had to be re-created.",
			"**Either half revokes.** Deactivating the assignment while leaving the role also revokes — that is check 4.11.",
		]
	)
	g.tickbox()

	g.check(
		"4.15",
		"CONFIRMS A FIX — an assignment for a role never held grants nothing",
		"The previous edition's exact reproduction, run again against the fixed code.",
	)
	g.code(
		"roleless = 'roleless@guide.test'\n"
		"frappe.get_doc({'doctype':'User','email':roleless,'first_name':'Roleless',\n"
		"                'send_welcome_email':0,'user_type':'System User'}).insert()   # note: NO roles\n"
		"frappe.clear_cache(user=roleless)\n"
		"frappe.get_doc({'doctype':'Geo Assignment','user':roleless,\n"
		"                'role':'Guide Volunteer Approver','geo_node':alpha,'is_active':1}).insert()\n"
		"\n"
		"'Guide Volunteer Approver' in frappe.get_roles(roleless)\n"
		"resolve_approvers(riverside_a, 'Guide Volunteer Approver')\n"
		"len(scope.get_user_geo_scope(roleless, 'Guide Volunteer Approver'))"
	)
	g.observed(
		"False                            # they do not hold the role\n"
		"['alpha_officer@guide.test']     # … and are NOT routed. Only the genuine holder is.\n"
		"0                                # … and are granted no scope"
	)
	g.expected(
		bullets=[
			"Under the previous code this returned `['alpha_officer@guide.test', 'roleless@guide.test']` and a"
			" scope of 2. Compare against the 2 August edition's check 4.14 if you have it.",
			"The row still exists and is still live. It simply places an authority the user does not have.",
			"Administrator is branched around in the SQL, because `frappe.get_roles` treats Administrator as"
			" holding every role without a `Has Role` row to prove it. Without that branch the SQL and the"
			" Python form of the rule would disagree about exactly one user.",
		]
	)
	g.tickbox()

	g.h2("The role that scopes a doctype, taken from configuration")
	g.para(
		"Everything above used a literal role in the registration. These three checks repeat the same"
		" arrangement with `role_from_setting`, which is what both of vmmsx's real registrations use."
	)

	g.check(
		"4.16",
		"NEW — the same three layers, with the role read from settings",
		"That a settings-backed registration behaves identically to a literal one.",
	)
	g.code(
		"REG['Guide Scoped Record'] = {'doctype':'Guide Scoped Record',\n"
		"                              'geo_node_field':'home_geo_node',\n"
		"                              'role_from_setting':'guide_scope_role'}\n"
		"registry.registrations = lambda: REG\n"
		"frappe.db.set_single_value('National Society Settings', 'guide_scope_role',\n"
		"                           'Guide Volunteer Approver')\n"
		"frappe.clear_document_cache('National Society Settings', 'National Society Settings')\n"
		"\n"
		"registry.resolve_role(registry.for_doctype('Guide Scoped Record'))\n"
		"enforcement.get_permission_query_conditions(user_b, 'Guide Scoped Record')\n"
		"guarded(user_b, records['beta']), guarded(user_b, records['alpha'])"
	)
	g.observed(
		"'Guide Volunteer Approver'\n"
		"\"`tabGuide Scoped Record`.`home_geo_node` IN ('GEO-00003', 'GEO-00005')\"\n"
		"('permitted', 'PermissionError')"
	)
	g.expected(
		bullets=[
			"Identical behaviour to 4.6 and 4.8, with the role coming from a settings field instead of an app's source.",
			"`resolve_role()` reads through `config.settings()` — the same cached single every other"
			" society-configuration reader uses — so this adds no database round trip to the enforcement hot path.",
			"A literal `role` is returned as-is and is **not** checked for existence. That is deliberate: it is"
			" exactly the previous behaviour, and the config-time check in 5.7 already covers the settings case.",
		]
	)
	g.tickbox()

	g.check(
		"4.17",
		"NEW — an unresolvable role fails closed and leaves a signal",
		"The trap this whole shape exists to close: a denial that looks like an empty scope.",
	)
	g.code(
		"from onerc_core.access.services.registry import UNRESOLVED_ROLE_LOG_TITLE\n"
		"before = frappe.db.count('Error Log', {'method': UNRESOLVED_ROLE_LOG_TITLE})\n"
		"\n"
		"frappe.db.set_single_value('National Society Settings', 'guide_scope_role', '')   # unset\n"
		"frappe.clear_document_cache('National Society Settings', 'National Society Settings')\n"
		"registry.resolve_role(registry.for_doctype('Guide Scoped Record'))\n"
		"enforcement.get_permission_query_conditions(user_b, 'Guide Scoped Record')\n"
		"guarded(user_b, records['beta'])\n"
		"\n"
		"frappe.db.set_single_value('National Society Settings', 'guide_scope_role', 'No Such Role')\n"
		"frappe.clear_document_cache('National Society Settings', 'National Society Settings')\n"
		"registry.resolve_role(registry.for_doctype('Guide Scoped Record'))\n"
		"enforcement.get_permission_query_conditions(user_b, 'Guide Scoped Record')\n"
		"frappe.db.count('Error Log', {'method': UNRESOLVED_ROLE_LOG_TITLE}) - before\n"
		"\n"
		"enforcement.guard('Guide Scoped Record', records['beta'], user=user_b)"
	)
	g.observed(
		"None            # unset\n"
		"'1=0'\n"
		"'PermissionError'\n"
		"\n"
		"None            # names a role that does not exist\n"
		"'1=0'\n"
		"6               # six new Error Log rows across those calls\n"
		"\n"
		"PermissionError: You are not permitted to act on Guide Scoped Record fsooqmdild. The role that\n"
		"scopes Guide Scoped Record is not configured, so nobody's area can be established — ask an\n"
		"administrator to set it in National Society Settings."
	)
	g.expected(
		bullets=[
			"Both failure modes — unset, and naming a role that does not exist — return `None`, deny, and log.",
			"**`1=0`, not `''`.** Failing closed is the only safe answer: granting on “we could not tell” is how a scope layer becomes decorative.",
			"It logs on **every** occurrence rather than deduplicating. A misconfigured access boundary is an"
			" outage; the noise is the alarm. That is why the reference bench shows 717 of them in check 0.5.",
			"The refusal message names the problem rather than a role that does not exist, so the person who"
			" hits it can act on it. Compare with 4.8's message, which names the configured role.",
			"The distinction that matters: **a role that resolves and legitimately has no assignments returns"
			" an empty scope with no error, and that is normal.** Only an unresolvable role logs. Those two"
			" cases used to be indistinguishable.",
		]
	)
	g.tickbox()

	g.check(
		"4.18",
		"NEW — a malformed registration is refused, naming what is wrong",
		"That an app cannot half-declare a security boundary.",
	)
	g.code(
		"from onerc_core.access.services import registry\n"
		"registry._validated({'doctype':'X','geo_node_field':'g','role':'R','role_from_setting':'s'})\n"
		"registry._validated({'doctype':'X','geo_node_field':'g'})\n"
		"registry._validated({'doctype':'X','role':'R'})\n"
		"registry._validated('Guide Scoped Record')\n"
		"registry.geo_node_field('Guide Scoped Record')      # registered on a field it does not have"
	)
	g.observed(
		"ValidationError:  … gives both role and role_from_setting. Exactly one names the role: a literal\n"
		"                  role, or the settings field holding it.\n"
		"MandatoryError:   … names no role. Give either role (a Frappe role name) or role_from_setting\n"
		"                  (the National Society Settings field holding one).\n"
		"MandatoryError:   … is missing geo_node_field. Every entry needs doctype, geo_node_field, role.\n"
		"ValidationError:  … entry must be a dict with keys doctype, geo_node_field, role. Got str.\n"
		"ValidationError:  Guide Scoped Record is registered as scopeable on field no_such_field, which\n"
		"                  Guide Scoped Record does not have. Fix the onerc_scopeable_doctypes entry in\n"
		"                  the app that declared it."
	)
	g.expected(
		bullets=[
			"Both role keys is **refused**, not resolved by precedence. A registration with two answers to one"
			" question would make the security boundary depend on which key the reader looked at first.",
			"A field the doctype does not have throws rather than degrading. Silently skipping the filter"
			" would leak every record of that doctype to every user; silently denying would look like a data"
			" problem instead of the wiring mistake it is.",
			"Also try registering one doctype twice, from two apps: that throws too, because picking one would"
			" make a security boundary depend on app install order.",
		]
	)
	g.tickbox()

	g.h2("What is NOT built or covered here")
	g.para(
		"Read this before signing the section off. Everything below is outside what the checks above can prove — it is not a list of defects, it is the boundary of the evidence."
	)
	g.bullet(
		"Every check in this section used a stand-in doctype registered by hand. The two **real**"
		" registrations on this bench — VMMS Volunteer and VMMS Membership — were only inspected, not"
		" exercised, because neither has any records and both have an unconfigured role. Verifying them"
		" end to end belongs to vmmsx's own pass."
	)
	g.bullet(
		"The enforcement layer does not distinguish read from write: `has_permission` applies the same geo"
		" test to every permission type. Somebody who can read a record in their scope can, as far as this"
		" layer is concerned, write it too; only role permissions separate the two."
	)
	g.bullet(
		"There is no administrative UI for scope beyond the standard Geo Assignment form — no ‘who can see what’ report, no way to preview a user's scope from the desk."
	)
	g.bullet(
		"No audit trail of scope decisions. A denial is a `PermissionError`; nothing records that it happened. The Error Log entries in 4.17 record misconfiguration, not denials."
	)
	g.bullet(
		"Row-level sharing (Frappe's docshare) is not considered by the geo layer. A shared document may be reachable outside a user's geo scope through the framework's own sharing."
	)
	g.bullet(
		"The three Geo Assignment test classes that cover `grants_authority` cannot run on this bench —"
		" check 0.3. Checks 4.14 and 4.15 are the manual substitute, and they are the only evidence here"
		" that the rule holds."
	)

	# ==================================================================
	g.h1("Section 5 — Society settings")
	g.para(
		"Everything a National Society answers differently should live in one record and be readable in one"
		" call. This section changes three of those answers and watches `get_ui_config()` follow — then"
		" checks the config-time half of the access layer's fail-loud rule."
	)

	g.check(
		"5.1",
		"Read the configuration before changing anything",
		"The shape of the payload, and what an unconfigured site returns.",
	)
	g.code(
		"from onerc_core.society.services import config as society\n"
		"cfg = society.get_ui_config()\n"
		"sorted(cfg)\n"
		"cfg['theme'], cfg['terminology'], cfg['features']\n"
		"cfg['locale']\n"
		"cfg['society']"
	)
	g.observed(
		"['features', 'locale', 'social_media', 'society', 'terminology', 'theme', 'validation']\n"
		"({}, {}, {})        # nothing configured yet\n"
		"{'primary_language':'en', 'secondary_languages':[], 'currency':None,\n"
		" 'time_zone':'Asia/Kolkata', 'date_format':'dd-mm-yyyy', 'time_format':'HH:mm:ss',\n"
		" 'first_day_of_week':'Sunday', 'number_format':'#,###.##', 'float_precision':'2'}\n"
		"{'name':None, 'short_name':None, 'country':'Kenya', 'website':None, 'telephone':None,\n"
		" 'physical_address':None, 'logo':None, 'logo_dark':None, 'favicon':None}"
	)
	g.expected(
		bullets=[
			"Seven keys, one call.",
			"`theme` is `{}` rather than a dict of `None`s — unset tokens are omitted so a UI can spread this over its own defaults without blanking them.",
			"The locale values that are populated came from **System Settings**, not from this record. That"
			" fallback is the contract: this doctype never becomes a second source of truth for site formatting.",
			"`time_zone` here reads `Asia/Kolkata` — Frappe's own default, never changed on this bench. Confirm"
			" with `frappe.get_cached_doc('System Settings').time_zone`. It matters for check 5.4.",
		]
	)
	g.tickbox()

	g.check(
		"5.1b",
		"CONFIRMS A FIX — branding is optional, so configuration is not blocked",
		"That a fresh site can be configured before anybody has found a logo to upload.",
	)
	g.code(
		"meta = frappe.get_meta('National Society Settings')\n"
		"[f.fieldname for f in meta.fields if f.reqd]\n"
		"meta.get_field('logo').reqd, meta.get_field('logo').description"
	)
	g.observed(
		"['organization_name', 'organization_short_name', 'country', 'primary_language']\n"
		"(0, 'Optional. Blank means the society has not uploaded one yet.')"
	)
	g.expected(
		bullets=[
			"`logo` is no longer mandatory. Under the previous code it was an `Attach Image` with `reqd: 1`,"
			" so nobody could set a currency, a phone rule or a terminology term until somebody had uploaded"
			" a picture — finding 3 of the previous edition.",
			"Four fields remain mandatory, and all four are answers only the society can give. Nothing else became mandatory in exchange.",
			"The automated test for this, `TestBrandingIsOptional`, is one of the five that cannot run on this bench — check 0.3. This check is its substitute.",
		]
	)
	g.tickbox()

	g.check(
		"5.2",
		"Change a term, a colour and the currency",
		"The core claim: a society's vocabulary and identity are data.",
	)
	g.code(
		"s = frappe.get_doc('National Society Settings')\n"
		"s.organization_name = s.organization_name or 'Guide National Society'\n"
		"s.organization_short_name = s.organization_short_name or 'GNS'\n"
		"s.primary_language = s.primary_language or 'en'\n"
		"s.append('terminology', {'term_key':'Volunteer ', 'singular':'Kujitolea', 'plural':''})\n"
		"s.append('feature_toggles', {'feature_key':'Self Service', 'is_enabled':1})\n"
		"s.primary_color = '#C8102E'\n"
		"s.currency = 'KES'        # or any currency on your site\n"
		"s.save()\n"
		"\n"
		"society.term('volunteer'), society.term('volunteer', plural=True)\n"
		"society.term('a_word_nobody_configured')\n"
		"society.is_feature_enabled('self_service')\n"
		"society.is_feature_enabled('a_feature_nobody_configured', True)\n"
		"society.get_ui_config()['theme']['primary_color']\n"
		"society.get_ui_config()['locale']['currency']"
	)
	g.observed(
		"('Kujitolea', 'Kujitoleas')          # note the key was normalised: 'Volunteer ' -> volunteer\n"
		"'a_word_nobody_configured'           # falls back to the key, never renders empty\n"
		"True\n"
		"True                                 # absent means absent — the caller's default is honoured\n"
		"'#C8102E'\n"
		"'KES'"
	)
	g.expected(
		bullets=[
			"The term key is lower-snake-cased on save, so ‘Self Service’ and ‘self_service’ cannot become two rows that shadow each other.",
			"The plural is generated when not given — crude for non-English words (‘Kujitoleas’), which is why"
			" the plural column exists. Set it explicitly for any language where the +s rule does not hold.",
			"An unconfigured feature returns the caller's default, because core does not define features and cannot have an opinion about one it never named.",
		]
	)
	g.tickbox()

	g.check(
		"5.2b",
		"A repeated key is refused, naming the row it collides with",
		"That a normalisation rule cannot silently swallow a duplicate.",
	)
	g.code(
		"s = frappe.get_doc('National Society Settings')\ns.append('terminology', {'term_key':'volunteer', 'singular':'Again'})\ns.save()"
	)
	g.observed("ValidationError: Terminology row 2 repeats the key volunteer, already used in row 1.")
	g.expected("Refused, with both row numbers. The same rule applies to feature toggles.")
	g.tickbox()

	g.check("5.3", "The same values in the desk", "That the form and the service agree.")
	g.code("/app/national-society-settings")
	g.expected(
		"Look at the Society, Theme, Locale, Terminology, Features and Validation tabs. The term you added"
		" appears in the Terminology grid with the normalised key; the colour appears in the Theme tab; the"
		" currency in Locale. Change one from the form and re-run `get_ui_config()` to confirm the service"
		" sees it."
	)
	g.tickbox()

	g.check(
		"5.4",
		"CONFIRMS A FIX — a bad time zone is refused, with a site-relevant example",
		"That validation is society-neutral rather than a maintained list, and that the worked example is no longer Kenyan.",
	)
	g.code("s = frappe.get_doc('National Society Settings'); s.time_zone = 'Middle/Earth'; s.save()")
	g.observed(
		"ValidationError: Middle/Earth is not an IANA time zone name. Expected something like Asia/Kolkata."
	)
	g.expected(
		bullets=[
			"Refused. The check is membership of Python's `zoneinfo` database — no hardcoded list to rot.",
			"**The example is your site's own System Settings zone**, not `Africa/Nairobi`. On this bench that"
			" is `Asia/Kolkata`; on yours it will be whatever the site was created with. If System Settings has"
			" nothing to offer it falls back to the shape `Region/City` — a shape rather than a place, which is"
			" what the message is really demonstrating.",
		]
	)
	g.tickbox()

	g.check(
		"5.5",
		"An invalid phone pattern is refused at configuration time",
		"So a broken regex fails once, in front of an administrator, not on every profile save.",
	)
	g.code(
		"s = frappe.get_doc('National Society Settings'); s.phone_number_pattern = '^+254(unclosed'; s.save()"
	)
	g.observed(
		"ValidationError: ^+254(unclosed is not a valid regular expression: nothing to repeat at position 1"
	)
	g.expected("Refused with the regex error included.")
	g.tickbox()

	g.check(
		"5.6",
		"The configured phone rule is enforced — and absent means unchecked",
		"The whole ‘no hardcoded phone regex’ rule, end to end.",
	)
	g.code(
		"s = frappe.get_doc('National Society Settings')\n"
		"s.phone_number_pattern = r'^\\+2547\\d{8}$'; s.phone_number_example = '+254712345678'; s.save()\n"
		"\n"
		"frappe.get_doc({'doctype':'Red Profile','first_name':'Bad','last_name':'Phone',\n"
		"                'email':'bad.phone@example.test','phone':'0712 345 678'}).insert()\n"
		"\n"
		"frappe.get_doc({'doctype':'Red Profile','first_name':'Good','last_name':'Phone',\n"
		"                'email':'good.phone@example.test','phone':'+254712345678'}).insert()\n"
		"\n"
		"s.phone_number_pattern = ''; s.save()\n"
		"frappe.get_doc({'doctype':'Red Profile','first_name':'NoRule','last_name':'Phone',\n"
		"                'email':'norule.phone@example.test','phone':'0712 345 678'}).insert()"
	)
	g.observed(
		"ValidationError: Phone 0712 345 678 is not valid for this society. Expected something like\n"
		"                 +254712345678.\n"
		"RP-00121  (+254712345678 accepted)\n"
		"RP-00122  ('0712 345 678' accepted — no pattern configured, so no check at all)"
	)
	g.expected(
		bullets=[
			"A number that does not match the society's pattern is refused, with the society's own example in the message.",
			"Clear the pattern and the same number is accepted — a society that has not declared a numbering plan does not get one invented for it.",
			"Set a different pattern (say a Gambian one) and confirm the previously-valid Kenyan number is now refused. That is the configurability claim in one gesture.",
		]
	)
	g.tickbox()

	g.check(
		"5.7",
		"NEW — a scope role that names nothing is refused while the administrator is looking at it",
		"The config-time half of the access layer's fail-loud rule.",
	)
	g.para(
		"Check 4.17 showed what happens at enforcement time when a scope role cannot be resolved: deny, and"
		" log. This is the other half — stopping the bad value being saved at all. Use the"
		" `guide_scope_role` Custom Field created in 4.1, or one of vmmsx's if it is installed."
	)
	g.code(
		"s = frappe.get_doc('National Society Settings')\n"
		"s.vmms_volunteer_scope_role = 'No Such Role At All'\n"
		"s.save()\n"
		"\n"
		"# then a real one, and then blank:\n"
		"s.vmms_volunteer_scope_role = 'Guide Scope Role'; s.save()\n"
		"registry.resolve_role(registry.registrations()['VMMS Volunteer'])\n"
		"s.vmms_volunteer_scope_role = ''; s.save()\n"
		"registry.resolve_role(registry.registrations()['VMMS Volunteer'])"
	)
	g.observed(
		"LinkValidationError: Could not find Volunteer Scope Role: No Such Role At All\n"
		"\n"
		"'Guide Scope Role'      # saved, and resolves\n"
		"''                      # blank saves fine\n"
		"None                    # … and resolves to nothing, which is the fail-closed case"
	)
	g.expected(
		bullets=[
			"A non-empty value naming no Frappe role is refused. A name matching nothing would deny everybody the doctype it scopes.",
			"**An empty value saves fine.** A society that has not chosen the role yet has not made a mistake;"
			" enforcement fails closed and logs until they do. That asymmetry is deliberate — do not"
			" “fix” it into a mandatory field.",
			"The message names the field's label and the doctype the role decides access to, so it says what is at stake rather than just what is invalid.",
		]
	)
	g.callout(
		"observation",
		"OBSERVATION — On this bench the guard is doubled, and core's own half never fires",
		"vmmsx declared its settings fields as `Link → Role`, so **Frappe's own link validation** rejects an"
		" unknown role before `NationalSocietySettings.validate_scope_roles()` is ever reached — which is why"
		" the observed error above is a `LinkValidationError` rather than core's own message. That is a"
		" better outcome, not a worse one, and nothing needs changing. But it means core's check is unproven"
		" on this bench. It is what protects a registration whose settings field is a plain `Data` field, and"
		" the automated tests in `test_scope_role_config.py` cover that case. If you want to see core's own"
		" message, point a registration at the `Data` Custom Field from check 4.1 and save a nonsense value.",
	)
	g.tickbox()

	g.h2("What is NOT built or covered here")
	g.para(
		"Read this before signing the section off. Everything below is outside what the checks above can prove — it is not a list of defects, it is the boundary of the evidence."
	)
	g.bullet(
		"`get_ui_config()` is whitelisted but authenticated — there is no guest-safe branding subset, so a public portal cannot read the logo and colours without a session."
	)
	g.bullet(
		"Terminology keys are free-form. Nothing declares which terms a product will ask for, so a typo in a key is silently a term nobody reads; `term()` returns the key and the screen looks almost right."
	)
	g.bullet(
		"The currency is stored and returned but nothing in core consumes it — no formatting helper, no conversion. It is a promise to product apps, not a working feature yet."
	)
	g.bullet(
		"Feature toggles are similarly inert in core: `is_feature_enabled()` is available, and nothing in core calls it."
	)
	g.bullet(
		"Two of the settings doctype's own test classes cannot run on this bench — check 0.3. The 32 society tests that do run live in `society/tests/test_config.py` and exercise the service, not the form."
	)
	g.bullet(
		"There is no second-society fixture anywhere. Nobody has yet stood up two sites with different settings and compared behaviour — the strongest possible version of this section, and it is not done."
	)

	# ==================================================================
	g.h1("Section 6 — Findings, and what this document does not cover")

	g.h2("The three findings of the previous edition")
	g.para(
		"All three were reproduced on the reference bench on 2 August, fixed in code, and re-verified by the checks named below on 4 August."
	)
	g.table(
		["#", "Finding", "Fixed in", "Re-verified by"],
		[
			(
				"1",
				"A Geo Node could be nested under a node at a deeper level; `get_ancestors()` then returned"
				" ancestors in the wrong order and `resolve_approvers()` routed to the wrong person.",
				"62007b3 — `ORDER BY lft DESC` in the adapter, and a parent-is-shallower rule on Geo Node.",
				"Checks 3.11 and 3.12. **Closed.**",
			),
			(
				"2",
				"Geo Assignment granted routing and scope without checking that the user still held the Frappe role named on it.",
				"62007b3 — `GRANTS_AUTHORITY_SQL`, read by every caller.",
				"Checks 4.14 and 4.15. **Closed.**",
			),
			(
				"3",
				"National Society Settings could not be saved without a logo, blocking all other configuration on a fresh site.",
				"62007b3 — the logo is optional and carries a description saying so.",
				"Check 5.1b. **Closed.**",
			),
		],
	)
	g.para(
		"Both cosmetic observations are closed too: the unknown-time-zone message now uses the site's own"
		" zone (check 5.4), and the data-keyed docnames on Geo Level, Affiliation Type and Identification"
		" Type are recorded as a deliberate rule about configuration vocabularies rather than a deviation"
		" (check 3.10)."
	)

	g.h2("Findings from this run")
	g.para(
		"Two things on this bench behave differently from what the documented intent implies. Neither is a defect in onerc_core's code."
	)
	g.table(
		["#", "Finding", "Where", "Severity"],
		[
			(
				"1",
				"Two doctypes are registered as geo-scoped with `role_from_setting`, and **neither settings"
				" value is set**. Every user without the System Manager bypass is denied VMMS Volunteer and"
				" VMMS Membership entirely, and 717 Error Log entries have accumulated saying so.",
				"Check 0.5",
				"High, operationally — but it is **configuration, not code**. The layer is behaving exactly as"
				" designed: fail closed, and log loudly enough to be found. Set the two roles in National"
				" Society Settings and both the denials and the logging stop.",
			),
			(
				"2",
				"Five test classes error in `setUpClass` before any of their tests run, because Frappe's test"
				" record generation reaches an ERPNext Fiscal Year that collides with a real one. They cover"
				" the optional-logo change, time-zone validation, and all three Geo Assignment classes —"
				" including `TestGrantsAuthority`, the automated half of the previous edition's finding 2.",
				"Check 0.3",
				"Medium. The code is fine and the behaviour was verified by hand in checks 4.14, 4.15 and 5.1b."
				" The risk is that a future regression in `grants_authority` would not be caught by CI. Give"
				" those classes `IGNORE_TEST_RECORD_DEPENDENCIES`, as the Red Profile tests already do.",
			),
		],
	)

	g.h2("The headline answer")
	g.callout(
		"resolved",
		"Configurability: no defects found.",
		"No controller, service or doctype in onerc_core assumes a level named “County” or a role named"
		" “County Coordinator”. Zero society role names, zero geo level names and zero geo node names reach"
		" executable code; the only role literals in logic are the framework primitives System Manager,"
		" Administrator and Guest. A society with no counties loses nothing — proven by running identity,"
		" geography, scoping and approver routing end to end on a Zone / Sector / Cell hierarchy. What"
		" society words remain are in docstrings, field help text, test fixtures and copyright headers."
		" Since the last edition the claim has gone one step further: **which role scopes a doctype is now"
		" configuration too**, so an app no longer has to name a society's role in its own source.",
	)

	g.h2("What this document does not cover at all")
	g.bullet(
		"The CMS half of onerc_core — Article, FAQ, Feedback, Stakeholder, Region, SMS Campaign,"
		" Localisation. Those doctypes predate this work, have test files containing no tests, and are"
		" explicitly out of scope for the identity/geo/access foundation."
	)
	g.bullet(
		"Performance and scale. Every check here runs on a hierarchy of eleven nodes. Nothing has been"
		" measured against a real country's geography, and `get_user_geo_scope()` materialises a set of"
		" every node in a user's subtree on every call."
	)
	g.bullet("Concurrency. No check exercises two users acting on one record at the same moment.")
	g.bullet(
		"Migration and upgrade. Nothing here tests what happens to existing data when a level is deleted, a node is re-parented, or an affiliation type is deactivated."
	)
	g.bullet(
		"The vmmsx approval engine, which consumes all of this — and now also the two registrations and two"
		" affiliation providers it contributes. Verifying vmmsx is a separate exercise, and checks 0.4, 0.5"
		" and 2.12 only inspect what it declares."
	)
	g.bullet(
		"Any second national society. The strongest test of this system is two live sites with different"
		" hierarchies, terminology and roles. Until that exists, section 1 is an argument from code and"
		" sections 3–4 an argument from a synthetic hierarchy — strong, but not the real thing."
	)

	g.h2("Sign-off")
	g.table(
		["Section", "Checks", "Result", "Notes"],
		[
			("0 — Preflight", "5", "", ""),
			("1 — Configurability", "12", "", ""),
			("2 — Identity", "16", "", ""),
			("3 — Geography", "12", "", ""),
			("4 — Access & scoping", "18", "", ""),
			("5 — Society settings", "9", "", ""),
			("", "", "", ""),
			("Verified by", "", "Date", ""),
			("Commit tested", "", "Site", ""),
		],
	)

	# ==================================================================
	g.h1("Appendix A — The hardcoding scanner")
	g.para(
		"Save as `/tmp/scan_hardcoding.py` and run in the console with"
		" `exec(open('/tmp/scan_hardcoding.py').read(), globals())`. Used by check 1.4. It parses every"
		" non-test Python file in onerc_core and reports string constants — excluding docstrings — that"
		" match a live Role, Geo Level or Geo Node name on the site you run it against."
	)
	g.code(
		"import ast, os, frappe\n"
		"\n"
		"APP_PATH = frappe.get_app_path('onerc_core')\n"
		"SKIP = {'tests', '__pycache__', 'node_modules'}\n"
		"FRAMEWORK_ROLES = {'System Manager', 'Administrator', 'All', 'Guest', 'Desk User', 'Report Manager'}\n"
		"SOCIETY_WORDS = {'county','counties','coordinator','ward','kenya','kenyan','province',\n"
		"                 'district','sub-county','subcounty','chapter','branch'}\n"
		"\n"
		"def source_files():\n"
		"    for root, dirs, files in os.walk(APP_PATH):\n"
		"        dirs[:] = [d for d in dirs if d not in SKIP]\n"
		"        for name in files:\n"
		"            if name.endswith('.py') and not name.startswith('test_'):\n"
		"                yield os.path.join(root, name)\n"
		"\n"
		"def docstring_nodes(tree):\n"
		"    out = []\n"
		"    for n in ast.walk(tree):\n"
		"        if isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):\n"
		"            if n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):\n"
		"                out.append(n.body[0].value)\n"
		"    return out\n"
		"\n"
		"roles  = set(frappe.get_all('Role', pluck='name'))\n"
		"levels = set(frappe.get_all('Geo Level', pluck='geo_level_name')) | set(frappe.get_all('Geo Level', pluck='name'))\n"
		"nodes  = set(frappe.get_all('Geo Node', pluck='geo_node_name'))\n"
		"print(f'matching against {len(roles)} roles, {len(levels)} levels, {len(nodes)} nodes')\n"
		"\n"
		"role_hits, level_hits, node_hits, word_hits = [], [], [], []\n"
		"for path in sorted(source_files()):\n"
		"    rel = os.path.relpath(path, APP_PATH)\n"
		"    tree = ast.parse(open(path, encoding='utf-8').read(), filename=rel)\n"
		"    docs = docstring_nodes(tree)\n"
		"    for n in ast.walk(tree):\n"
		"        if not isinstance(n, ast.Constant) or not isinstance(n.value, str):  continue\n"
		"        if any(n is d for d in docs):                                        continue\n"
		"        v = n.value\n"
		"        if   v in roles:            role_hits.append((rel, n.lineno, v))\n"
		"        elif v in levels and v:     level_hits.append((rel, n.lineno, v))\n"
		"        elif v in nodes and v:      node_hits.append((rel, n.lineno, v))\n"
		"        elif any(w in v.lower() for w in SOCIETY_WORDS):  word_hits.append((rel, n.lineno, v))\n"
		"\n"
		"for title, hits in (('A. live ROLE names', role_hits), ('B. live GEO LEVEL names', level_hits),\n"
		"                    ('C. live GEO NODE names', node_hits), ('D. other society words', word_hits)):\n"
		"    print(f'\\n{title}: {len(hits)} hit(s)')\n"
		"    for rel, line, v in hits:  print(f'  {rel}:{line}  {v!r}')\n"
		"\n"
		"print('\\nVERDICT')\n"
		"print('society role names in logic :', [h for h in role_hits if h[2] not in FRAMEWORK_ROLES] or 'none')\n"
		"print('geo level names in logic    :', [h[2] for h in level_hits] or 'none')\n"
		"print('geo node names in logic     :', [h[2] for h in node_hits] or 'none')"
	)

	# ==================================================================
	g.h1("Appendix B — Confirming the ancestor-ordering fix")
	g.para(
		"Used by checks 3.11 and 3.12. Assumes the Zone / Cell / Block levels from section 3 exist"
		" (`GUIDE-1` order 1, `GUIDE-3` order 3, `GUIDE-4` order 4). The first half proves the malformed"
		" tree can no longer be built; the second plants one anyway, the way the automated fixtures do, and"
		" proves the adapter walks it in tree order regardless."
	)
	g.code(
		"import frappe\n"
		"from onerc_core.geo.services import adapter\n"
		"from onerc_core.access.services.approvers import resolve_approvers\n"
		"\n"
		"def node(label, level, parent, group=True):\n"
		"    return frappe.get_doc({'doctype':'Geo Node','geo_node_name':label,'geo_level':level,\n"
		"                           'parent_geo_node':parent,'is_group':int(group)}).insert()\n"
		"\n"
		"root_zone = node('Root Zone', 'GUIDE-1', None)\n"
		"mid_cell  = node('Mid Cell',  'GUIDE-3', root_zone.name)\n"
		"\n"
		"# 1. the shape is now refused at the point of entry\n"
		"try:\n"
		"    node('Inner Zone', 'GUIDE-1', mid_cell.name)     # a Zone under a Cell\n"
		"    print('NOT REFUSED — the parent-is-shallower rule is missing')\n"
		"except frappe.ValidationError as exc:\n"
		"    print('refused as expected:', frappe.utils.strip_html(str(exc))[:110])\n"
		"\n"
		"# 2. plant it the way a pre-rule row would exist on disk, and walk it\n"
		"inner_zone = node('Inner Zone', 'GUIDE-4', mid_cell.name)          # accepted: order 4 under 3\n"
		"frappe.db.set_value('Geo Node', inner_zone.name, 'geo_level', 'GUIDE-1', update_modified=False)\n"
		"leaf = node('Leaf Cell', 'GUIDE-3', inner_zone.name, group=False)\n"
		"\n"
		"print('true chain :', ['Inner Zone', 'Mid Cell', 'Root Zone'])\n"
		"print('adapter    :', [a.geo_node_name for a in adapter.get_ancestors(leaf.name)])\n"
		"print('orders     :', [a.geo_level_order for a in adapter.get_ancestors(leaf.name)])\n"
		"print('full path  :', adapter.get_full_path(leaf.name))\n"
		"\n"
		"role = 'Ordering Test Approver'\n"
		"if not frappe.db.exists('Role', role):\n"
		"    frappe.get_doc({'doctype':'Role','role_name':role,'desk_access':1}).insert()\n"
		"for handle, at in (('inner', inner_zone.name), ('mid', mid_cell.name)):\n"
		"    email = f'{handle}@ord.test'\n"
		"    if frappe.db.exists('User', email): frappe.delete_doc('User', email, force=True)\n"
		"    frappe.get_doc({'doctype':'User','email':email,'first_name':handle,'send_welcome_email':0,\n"
		"                    'user_type':'System User','roles':[{'role':role}]}).insert()\n"
		"    frappe.clear_cache(user=email)\n"
		"    frappe.get_doc({'doctype':'Geo Assignment','user':email,'role':role,\n"
		"                    'geo_node':at,'is_active':1}).insert()\n"
		"\n"
		"print('routed to  :', resolve_approvers(leaf.name, role))\n"
		"print('expected   :', ['inner@ord.test'])\n"
		"frappe.db.rollback()"
	)
	g.observed(
		"refused as expected: GEO-00009 is at level GUIDE-3 (order 3), which is not above level GUIDE-1…\n"
		"true chain : ['Inner Zone', 'Mid Cell', 'Root Zone']\n"
		"adapter    : ['Inner Zone', 'Mid Cell', 'Root Zone']\n"
		"orders     : [1, 3, 1]\n"
		"full path  : Leaf Cell — Inner Zone — Mid Cell — Root Zone\n"
		"routed to  : ['inner@ord.test']\n"
		"expected   : ['inner@ord.test']"
	)

	# ==================================================================
	g.h1("Appendix C — Teardown")
	g.para(
		"Quitting the console discards uncommitted work, so in most cases you need nothing. Run this only"
		" if you committed, or after check 4.1's DDL committed the earlier sections for you. Every name"
		" below is a fixture name from this guide. Running it at the end of the reference pass left the"
		" site with no Geo Level, Geo Node, Geo Assignment or Red Profile rows at all."
	)
	g.code(
		"import frappe\n"
		"\n"
		"# 1. the stand-in doctype and its records (DDL — commits)\n"
		"if frappe.db.exists('DocType', 'Guide Scoped Record'):\n"
		"    for name in frappe.get_all('Guide Scoped Record', pluck='name'):\n"
		"        frappe.delete_doc('Guide Scoped Record', name, force=True)\n"
		"    frappe.delete_doc('DocType', 'Guide Scoped Record', force=True)\n"
		"\n"
		"# 2. users and their assignments\n"
		"for email in frappe.get_all('User', filters={'email': ('like', '%@guide.test')}, pluck='name'):\n"
		"    for ga in frappe.get_all('Geo Assignment', filters={'user': email}, pluck='name'):\n"
		"        frappe.delete_doc('Geo Assignment', ga, force=True)\n"
		"    frappe.delete_doc('User', email, force=True)\n"
		"for email in frappe.get_all('User', filters={'email': ('like', '%@ord.test')}, pluck='name'):\n"
		"    for ga in frappe.get_all('Geo Assignment', filters={'user': email}, pluck='name'):\n"
		"        frappe.delete_doc('Geo Assignment', ga, force=True)\n"
		"    frappe.delete_doc('User', email, force=True)\n"
		"\n"
		"# 3. profiles, their stand-in satellites, and the vocabularies\n"
		"for rp in frappe.get_all('Red Profile', filters={'email': ('like', '%@example.test')}, pluck='name'):\n"
		"    frappe.delete_doc('Red Profile', rp, force=True)\n"
		"for td in frappe.get_all('ToDo', filters={'description': ('like', '%satellite%')}, pluck='name'):\n"
		"    frappe.delete_doc('ToDo', td, force=True)\n"
		"for key in ('guide_volunteer', 'guide_beneficiary'):\n"
		"    if frappe.db.exists('Affiliation Type', key):\n"
		"        frappe.delete_doc('Affiliation Type', key, force=True)\n"
		"if frappe.db.exists('Identification Type', 'guide_card'):\n"
		"    frappe.delete_doc('Identification Type', 'guide_card', force=True)\n"
		"\n"
		"# 4. geography, deepest first — nested set refuses to delete a node with children\n"
		"levels = [l for l in frappe.get_all('Geo Level', pluck='name') if l.startswith('GUIDE-')]\n"
		"for n in frappe.get_all('Geo Node', filters={'geo_level': ('in', levels)},\n"
		"                        order_by='lft desc', pluck='name'):\n"
		"    frappe.delete_doc('Geo Node', n, force=True)\n"
		"for l in levels:\n"
		"    frappe.delete_doc('Geo Level', l, force=True)\n"
		"\n"
		"# 5. roles, and the settings field from check 4.1\n"
		"for role in ('Guide Volunteer Approver', 'Guide Scope Role', 'Ordering Test Approver'):\n"
		"    if frappe.db.exists('Role', role):\n"
		"        frappe.delete_doc('Role', role, force=True)\n"
		"cf = frappe.db.get_value('Custom Field',\n"
		"                         {'dt': 'National Society Settings', 'fieldname': 'guide_scope_role'}, 'name')\n"
		"if cf:\n"
		"    frappe.delete_doc('Custom Field', cf, force=True)\n"
		"frappe.db.set_single_value('National Society Settings', 'guide_scope_role', None)\n"
		"\n"
		"frappe.db.commit()\n"
		"\n"
		"# 6. National Society Settings is a Single — revert the terminology, colour and currency\n"
		"#    by hand in the desk, or restore the values you noted in 5.1 before you changed them."
	)

	path = g.save()
	print(f"wrote {path}  ({g.checks} checks)")
	return g


if __name__ == "__main__":
	build()
