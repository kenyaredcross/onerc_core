// Copyright (c) 2026, Kelvin Njenga and contributors
// For license information, please see license.txt

// Two jobs, both of them entry experience rather than rules. Every rule this
// form appears to have lives on the server: `geo_level.py` fills a blank order,
// warns about a reused one, and moves the lowest marker whatever client asked
// for the save. Nothing here is load-bearing.
//
//   1. A new level arrives with its order already filled in, so nobody counts
//      rows and types a number. The server does the same for an API call or an
//      import; this is only so the desk shows it before saving.
//   2. The ladder is drawn, with the top rung marked. The top is *derived* from
//      the lowest active order and handed over by `onload` — there is no
//      is_highest field, deliberately, because a stored flag would be a third
//      answer to where the hierarchy begins.

frappe.ui.form.on("Geo Level", {
	onload(frm) {
		suggest_order(frm);
	},

	refresh(frm) {
		render_hierarchy(frm);
	},
});

function suggest_order(frm) {
	// Only ever fills a blank, and only on a new level. An order somebody typed,
	// or one an existing row already carries, is never touched.
	if (!frm.is_new() || frm.doc.geo_level_order) {
		return;
	}

	frappe.call({
		method: "onerc_core.onerc_core.doctype.geo_level.geo_level.next_available_order",
		callback(response) {
			// Re-checked on the way back: the field may have been typed into
			// while the request was in flight.
			if (response.message && !frm.doc.geo_level_order) {
				frm.set_value("geo_level_order", response.message);
			}
		},
	});
}

function render_hierarchy(frm) {
	const field = frm.get_field("hierarchy_html");

	if (!field || !field.$wrapper) {
		return;
	}

	const ladder = (frm.doc.__onload && frm.doc.__onload.hierarchy) || [];

	if (!ladder.length) {
		field.$wrapper.html(
			`<div class="text-muted">${__("No active levels yet. This one is the first rung.")}</div>`
		);
		return;
	}

	const rows = ladder
		.map((level) => {
			const marks = [];

			if (level.is_top) marks.push(__("top"));
			if (level.is_lowest) marks.push(__("lowest"));
			if (level.requires_parent) marks.push(__("needs a parent"));
			if (level.shares_order_with.length) {
				marks.push(
					__("shares this order with {0}", [
						frappe.utils.escape_html(level.shares_order_with.join(", ")),
					])
				);
			}

			const here = level.key === frm.doc.name;
			const label = frappe.utils.escape_html(level.name || level.key);
			const note = marks.length
				? `<span class="text-muted small"> &mdash; ${marks.join(", ")}</span>`
				: "";

			return `<div style="padding:2px 0">
				<span class="text-muted" style="display:inline-block;width:2.5rem">${level.order}</span>
				<span${here ? ' style="font-weight:600"' : ""}>${label}</span>${note}
			</div>`;
		})
		.join("");

	field.$wrapper.html(`<div>${rows}</div>`);
}
