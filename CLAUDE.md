# CLAUDE.md — onerc_core

This app is the **shared identity + geo foundation** for OneRC products. Other apps (vmmsx, and future OneRC apps) depend on it. Treat it as a stable, reusable base — not a place for product-specific logic.

Work happens on the `feature/vmms-integration` branch. **Never commit to `main`.**

---

## What this app owns

- **Identity:** Red Profile, Red Profile Affiliation, Affiliation Type.
- **Geo:** Geo Level, Geo Node (nested set), and the geo adapter service.
- **Society config:** National Society Settings (single).

It also currently contains CMS/stakeholder tooling (Article, FAQ, Feedback, Stakeholder). Leave that alone unless a task names it. The identity + geo foundation is being **added** to this app; the CMS content already there is not ours to change.

---

## Vocabulary — do not conflate

- **Affiliation** = what a person *is* to the society: volunteer, member, vendor, beneficiary, donor, staff.
- **Capability** = what a user is *allowed to do*: approve, view metrics, deploy. (Capabilities are not built in this app.)

These are different concepts. Never use one word for the other. (Earlier drafts used "capacity" for affiliation — that word is retired; use **affiliation**.)

---

## Hard rules

- **Opaque docnames.** Red Profile is `RP-.#####`, never the email. Geo Node is an opaque ID, never `{level}-{name}`. Mutable data never goes in a primary key.
- **No app outside `onerc_core` imports Geo Node or Geo Level directly.** Everything geo goes through the adapter service.
- **`home_geo_node`, never `region`.** There is already an unrelated `Region` doctype; the name `region` is taken and confusing.
- **No denormalised `geo_level_order` on Geo Node.** Join to Geo Level for order; never sort or branch on a copied value.
- **No `ignore_permissions=True` by default.** Justify any exception inline.
- **No hardcoded country, currency, phone regex, or role name.** All of it is config or comes from National Society Settings.
- **Business logic in services, not in a single lifecycle hook** (not `before_submit`-only). Services must be idempotent.

---

## Red Profile — the identity spine

One record per party, ever. Thin: it holds *who* someone is and a list of their affiliations. It holds **no** domain data — a volunteer's skills, a member's fee, all live in satellite doctypes in other apps that link back here.

- Docname `RP-.#####`.
- `email` is the current unique identifier (required, unique, lowercased). It is a *field*, not the docname, so improving identity resolution later is a config change, not a migration.
- `user` is **nullable** — not everyone with a profile can log in (beneficiaries, imports, staff-entered records).
- `full_name` is composed, read-only; satellites in other apps fetch it for display only, never for logic.

## Affiliations — Design 2: a derived, satellite-maintained index

The `affiliations` child table is a **denormalised index, never the source of truth.**

- The **satellite owns the truth.** A Volunteer satellite (in vmmsx) existing and being Active is what makes someone an active volunteer. The affiliation row is a summary the satellite writes.
- **Satellites write rows only through `set_affiliation()`** (see services below), never by touching the child table directly. The row `status` is read-only.
- **No business logic reads the row.** Deployability, approval eligibility, etc. read the satellite. If code branches on an affiliation row's status, that is a bug — the row is allowed to be stale.
- **The list is reconstructable.** Deleting every affiliation row and rebuilding from live satellites must lose nothing. If it would lose information, the row has wrongly become a source of truth.

## Read gating

An Affiliation Type may set `requires_gated_read`. When a Red Profile is read, affiliation rows of a gated type are hidden from readers who lack the gating capability. The *existence* of such an affiliation (e.g. beneficiary) is itself sensitive. Enforce this in a service on every read path, not in the UI.

### The gate's boundary — read this before writing any affiliation query

Gated affiliations are protected **on document reads**: `read_gate.get_affiliations(profile)` for code, and `RedProfile.onload()` for the desk and any API returning a whole document.

**Never `frappe.get_all("Red Profile Affiliation", ...)` in a user-facing path.** It bypasses the gate by design — it is a direct child-table query and the gate lives above it. The same is true of `frappe.get_doc("Red Profile", ...)`, which returns every row because it is trusted server-side access. That is precisely why the service exists: anything whose result reaches a user goes through `get_affiliations()`.

A quick query is how a gated affiliation leaks. If you need affiliation data for a user-facing screen, report, or API, call the service.

---

## Services onerc_core must expose

- **Geo adapter** — `get_root_regions`, `get_children`, `get_ancestors` (nearest-first, ordered by `geo_level_order` via join), `get_descendants`, `get_level`, `level_labels`, `is_leaf`, `get_full_path`, `resolve_upward(node, predicate)`, `matches_scope(node, target, allow_ancestor)`. Uses NestedSet `lft`/`rgt`, never recursion.
- **`set_affiliation(profile, affiliation_type, status, reference_doctype, reference_name, start_date=None, end_date=None)`** — the single controlled entry point satellites use to write/update their index row. Enforces the read-only-status and one-row-per-type rules.
- **`rebuild_affiliations(profile)`** — regenerates a profile's affiliation list from its live satellites. The safety net for Design 2.
- **Read-gate service** — `get_affiliations(profile, user=None)` filters gated affiliation rows on read. Applied to the desk read path by `RedProfile.onload()`. Direct child-table queries bypass it — see the boundary note above.
- **`get_ui_config()`** — the whole of National Society Settings a product UI needs, in one call: branding, theme tokens, locale, terminology, feature toggles, validation policy.

---

## Decisions already taken — do not re-litigate

- Identity + geo foundation lives here in `onerc_core`, unprefixed, so future OneRC sites share it.
- `onerc_vmms` (the legacy app) is **not** used. Do not import from it or install it on the same site — it defines colliding Geo Level / Geo Node doctypes.
- Affiliations are Design 2 (derived index), not a source of truth.
- **There is no `clear_affiliation()`.** A satellite that is deleted calls `rebuild_affiliations(profile)` from its `on_trash`. One removal path, not two.
- Satellite apps register themselves with core, never the reverse: `onerc_affiliation_providers` for affiliation rebuilds, `onerc_capability_resolver` for the read gate. Core imports no satellite app. Both hooks are documented at the end of `hooks.py`.
- The word is **affiliation**, not capacity.
- Do **not** add a `required_apps` dependency on `onerc_knowledge_hub` / `localisation_hub` yet — note the undeclared Link deps, leave them dormant.
