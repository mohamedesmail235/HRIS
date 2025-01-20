// Copyright (c) 2018, Alfahhad and contributors
// For license information, please see license.txt

frappe.ui.form.on('Permission', {
	// clear cache for from_time_ and to_time_ while creating new permission...
	refresh: function (frm) {
		if (frm.is_new()) {
			let currentDate = new Date();
			frm.set_value("from_time_", `${currentDate.getHours()}:${currentDate.getMinutes()}:${currentDate.getMinutes()}`);
			frm.set_value("to_time_", `${currentDate.getHours()}:${currentDate.getMinutes()}:${currentDate.getMinutes()}`);
		}
	},
});

/*
for_date: function(frm) {
		frm.trigger("get_permission_balance");
	},
	employee: function(frm) {
		frm.trigger("get_permission_balance");
	},
	from_time: function(frm) {
		frm.trigger("get_permission_balance");
	},

	to_time: function(frm) {
		frm.trigger("get_permission_balance");
	},
	get_permission_balance: function(frm) {
		if(frm.doc.employee && frm.doc.for_date && frm.doc.from_time && frm.doc.to_time) {
			return frappe.call({
				method: "ptco_hr.attendances.doctype.permission.permission.get_permission_balance",
				args: {
					employee : frm.doc.employee,
					for_date : frm.doc.for_date
				},
				callback: function(r) {
					is_viewable= Object.keys(r.message)[0] != "Number Of Permissions Per Month";
					if (is_viewable == false){
							cur_frm.set_value("from_time","");
							cur_frm.set_value("to_time","");
							cur_frm.toggle_display("from_time", is_viewable);
							cur_frm.toggle_display("to_time", is_viewable);
					}

					if (!r.exc && r.message) {
						frm.set_value('permission_balance', Object.values(r.message)[0]);
					}
					else {
						frm.set_value('permission_balance', "0");
					}
					cur_frm.toggle_reqd("from_time", is_viewable);
					cur_frm.toggle_reqd("to_time", is_viewable);
				}
			});
		}
	}

*/