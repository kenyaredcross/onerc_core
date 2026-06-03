// Copyright (c) 2026, Kelvin Njenga and contributors
// For license information, please see license.txt

frappe.ui.form.on("OneRC Storage Backend", {
	refresh(frm) {
		if (!frm.doc.__islocal) {
			frm.add_custom_button(__("Test Connection"), () => {
				frappe.show_alert({ message: __("Testing connection…"), indicator: "blue" });
				frm.call("test_connection").then((r) => {
					if (r.message) {
						const result = r.message;
						frappe.msgprint({
							title: result.success ? __("Connection Successful") : __("Connection Failed"),
							message: result.message,
							indicator: result.success ? "green" : "red",
						});
					}
				});
			});
		}
	},
});
