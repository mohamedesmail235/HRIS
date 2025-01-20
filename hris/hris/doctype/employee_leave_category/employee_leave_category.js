// Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Employee Leave Category', {
    refresh: function (frm) {
        frm.set_query('leave', function () {
            return {
                "filters": {
                    "is_lwp": 0,
                    "is_carry_forward": 1
                }
            };
        })
    }
});
