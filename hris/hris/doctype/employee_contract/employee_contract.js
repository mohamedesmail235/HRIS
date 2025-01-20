// Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
{% include "erpnext/public/js/controllers/accounts.js" %}

cur_frm.cscript.onload = function(doc, dt, dn){
	var e_tbl = doc.earnings || [];
	var d_tbl = doc.deductions || [];
	if (e_tbl.length == 0 && d_tbl.length == 0)
		return function(r, rt) { refresh_many(['earnings', 'deductions']);};
}

frappe.ui.form.on('Employee contract', {
  social_status:function(frm){
        if(frm.doc.social_status=='Single'){
            frm.set_value('family_members_count',0)
            frm.refresh_field("family_members_count")
        }
   },
  employee: function(frm) {

    var emp = frm.doc.employee ;
    if(emp){
    frappe.call({
          method:'frappe.client.get' ,
          args:{
            'doctype' : 'Employee'  ,
            'name' : emp   ,

          },
            callback: function(r){

              frm.set_value("employee_full_name", r.message.employee_name)
            }


      })
    } else{
    frm.set_value("employee_full_name", " ")
    }

	},
  onload: function(frm){

    var emp = frm.doc.employee ;
    if(emp){
    var employee = frappe.get_doc('Employee',emp)
    // frm.set_value("employee_full_name", employee.employee_name)
    if (employee.citizen_or_resident == "Citizen") {
        frm.set_value("contract_type", "عقد عمل سعودى")
    }else{
      frm.set_value("contract_type" ,"عقد عمل أجنبي")
      // employee_nationality
      frm.set_value("employee_nationality" , employee.nationality )
    }}

    frm.set_query("salary_component", "earnings", function() {
			return {
				filters: {
					type: "earning"
				}
			}
		});
		frm.set_query("salary_component", "deductions", function() {
			return {
				filters: {
					type: "deduction"
				}
			}
		});
		frm.set_query("employee", "employees", function(doc) {
			return {
				query: "erpnext.controllers.queries.employee_query",
				filters: {
					company: doc.company
				}
			}
		});

  },
  refresh: function(frm) {
    frm.trigger("toggle_fields");
    frm.fields_dict['earnings'].grid.set_column_disp("default_amount", false);
    frm.fields_dict['deductions'].grid.set_column_disp("default_amount", false);
  },
  data_7: function(frm) {
    var duration = frm.doc.data_7 ;
    frappe.call({
      method:'hris.hris.doctype.employee_contract.employee_contract.v_integer' ,
      args :{
        'number':duration ,
      },
        callback: function(r){
          if(r.message==='0'){
            frappe.msgprint(__("Duration must be numbers"))
          }
        }
    })



    var employee = frm.doc.employee
      if(frm.doc.contract_start_date && employee)  {
      var start = frm.doc.contract_start_date

        frappe.call({
            method:'hrms.hrms.doctype.employee_contract.employee_contract.get_contract_end_date',
            args: {
              'duration'  : duration ,
              'start_date': start,
              'employee' :  employee
            } ,
            callback: function(r){
              frm.set_value("contratc_end_date" ,r.message)
            }


        })
                            }
            },
  contract_start_date: function(frm) {
    var duration = frm.doc.data_7 ;
    var start = frm.doc.contract_start_date
    var employee = frm.doc.employee
    if(frm.doc.data_7 && employee)
    {    frappe.call({// refresh: function(frm) {

	// }
          method:'hrms.hrms.doctype.employee_contract.employee_contract.get_contract_end_date',
          args: {
            'duration'  : duration ,
            'start_date': start ,
            'employee' :  employee
          } ,
          callback: function(r){
            frm.set_value("contratc_end_date" ,r.message)
          }


      })}

  } ,
family_members_count:function(frm){
	var numbers = frm.doc.family_members_count ;
	frappe.call({
		method:'hris.hris.doctype.employee_contract.employee_contract.v_integer' ,
		args :{
			'number':numbers ,
		},
			callback: function(r){
				if(r.message==='0'){
					frappe.msgprint(__("Input must be numbers"))
				}
			}
	})

},
    employee_leave_category: function (frm) {
        if (frm.doc.employee_leave_category) {
            frappe.call({
                method: 'update_yearly_vacation',
                doc: frm.doc,
                callback: function(r) {
                    if (r.message){
                        frm.set_value('yearly_vacation',r.message)
                        refresh_field('yearly_vacation')
                    }
                }
            })
        }
        else {
            frm.set_value('yearly_vacation',0)
            refresh_field('yearly_vacation')
        }
    }

})


frappe.ui.form.on('Salary Detail', {
  amount: function(frm, cdt, cdn){

    var row = locals[cdt][cdn];
    var data = frm.doc.earnings ;
    var data_d = frm.doc.deductions ;
    var i ;
    var total_earning = 0 ;
    var total_deduction = 0 ;
    frm.set_value("total_earnings" ,0) ;
    frm.set_value("total_deductions" ,0);

    if (data && data.length > 0){
    for (i =0 ; i < data.length ; i++){
			if(data[i].amount < 0){
					frappe.msgprint(__("You can not add negative numbers !"))
			}else{
      total_earning += data[i].amount ;}
    }
          }
    if (data_d && data_d.length > 0) {
    for (i =0 ; i < data_d.length ; i++){
			if(data_d[i].amount < 0){
					frappe.msgprint(__("You can not add negative numbers !"))
			}else{
      total_deduction += data_d[i].amount ;}
    }
      }
    frm.set_value("total_earnings" ,total_earning)
    frm.set_value("total_deductions" ,  total_deduction)
  },

  salary_component: function(frm, cdt, cdn) {
		var child = locals[cdt][cdn];
		if(child.salary_component){
			frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "Salary Component",
					name: child.salary_component
				},
				callback: function(data) {
					if(data.message){
						var result = data.message;
						frappe.model.set_value(cdt, cdn, 'condition', result.condition);
						frappe.model.set_value(cdt, cdn, 'amount_based_on_formula', result.amount_based_on_formula);
						if(result.amount_based_on_formula == 1){
							frappe.model.set_value(cdt, cdn, 'formula', result.formula);
						}
						else{
							frappe.model.set_value(cdt, cdn, 'amount', result.amount);
						}
						frappe.model.set_value(cdt, cdn, 'statistical_component', result.statistical_component);
						frappe.model.set_value(cdt, cdn, 'depends_on_payment_days', result.depends_on_payment_days);
						frappe.model.set_value(cdt, cdn, 'do_not_include_in_total', result.do_not_include_in_total);
						frappe.model.set_value(cdt, cdn, 'variable_based_on_taxable_salary', result.variable_based_on_taxable_salary);
						frappe.model.set_value(cdt, cdn, 'is_tax_applicable', result.is_tax_applicable);
						frappe.model.set_value(cdt, cdn, 'is_flexible_benefit', result.is_flexible_benefit);
						refresh_field("earnings");
						refresh_field("deductions");
					}
				}
			});
		}
	},




})
