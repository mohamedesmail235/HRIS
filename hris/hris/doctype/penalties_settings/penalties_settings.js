// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Penalties Settings', {
	refresh: function(frm) {

	},
	onload:function (frm) {
		 frm.set_query("deduct_value_of","penalties_data",  function() {
			return {
				query: "hris.hris.doctype.penalties_settings.penalties_settings.get_salary_components"
			};
		});

	}
});

frappe.ui.form.on("Penalties Settings", "validate", function(frm) {
    if (frm.doc.to_date < frm.doc.from_date) {
        frappe.msgprint(__("to date must be far than from date"));
        frappe.validated = false;
    }
});