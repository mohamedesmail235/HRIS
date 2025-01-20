// Copyright (c) 2022, MiM and contributors
// For license information, please see license.txt

frappe.ui.form.on('Employee Penalties', {
	setup: function(frm) {
		frm.set_query("employee", function() {
			return {
				filters: {
					"status": "Active"
				}
			};
		});
	}
});
