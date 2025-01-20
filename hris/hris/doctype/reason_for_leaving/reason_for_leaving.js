// Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Reason for Leaving', {
	// refresh: function(frm) {

	// }
});

frappe.ui.form.on('Payment Detail', {
    from:function(frm,cdt,cdn){
        check_redundant_option(frm,cdt,cdn)
    },
    to:function(frm,cdt,cdn){
        check_redundant_option(frm,cdt,cdn)
    },
    pay_percentage:function(frm,cdt,cdn){
        check_redundant_option(frm,cdt,cdn)
    }
});


var check_redundant_option = function(frm,cdt,cdn){
    let years_from_values = []
    let years_to_value = []
    var items = cur_frm.doc.payment_detail || []
    for(var i=0; i < items.length; i++){
        if (items[i].pay_percentage < 0 || items[i].pay_percentage > 100){
            frappe.model.set_value(cdt, cdn, "pay_percentage", '')
            frm.refresh_field(items[i].pay_percentage);
            frappe.throw(__("Value must be more than Zero and less than 100"))
        }

        if(years_from_values.indexOf(items[i].years_from) !== -1){
            frappe.model.set_value(cdt, cdn, "years_from", '')
            frm.refresh_field(items[i].years_from);
            frappe.throw(__("Value already exists!"))
        }
        else{
            years_from_values.push(items[i].years_from)
        }

        if(years_to_value.indexOf(items[i].years_to) !== -1){
            frappe.model.set_value(cdt, cdn, "years_to", '')
            frm.refresh_field(items[i].years_to);
            frappe.throw(__("Value already exists!"))
        }
        else{
            years_to_value.push(items[i].years_to)
        }


    }
}

