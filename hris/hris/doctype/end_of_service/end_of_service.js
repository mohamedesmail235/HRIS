// Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('End of Service', {
    refresh: function (frm) {
        frm.toggle_reqd("contract_type", frm.doc.form_type === 'End of Service' ? 1 : 0);
        frm.toggle_reqd("reason_for_leaving", frm.doc.form_type === 'End of Service' ? 1 : 0);
        frm.toggle_reqd("leave_application", frm.doc.form_type === 'Adjustment' ? 1 : 0);
    },
    setup: function (frm) {
        frm.set_query("salary_component", "earnings", function () {
            return {
                filters: {
                    type: "earning"
                }
            }
        });

        frm.set_query("salary_component", "deductions", function () {
            return {
                filters: {
                    type: "deduction"
                }
            }
        });

        frm.set_query("reason_for_leaving", function () {
            return {
                filters: {
                    "contract_type": frm.doc.contract_type
                }
            };
        });

        frm.set_query("employee", function () {
            return {
                filters: {
                    "status": 'Active'
                }
            };
        });

        // frm.set_query("contract", function () {
        //     return {
        //         filters: {
        //             "employee": frm.doc.employee
        //         }
        //     };
        // });

        frm.set_query("leave_application", function () {
            return {
                filters: {
                    "employee": frm.doc.employee,
                    "docstatus": 1
                }
            };
        });

    },
    // before_save : function (frm) {
    //     frm.clear_table("earnings","deductions")
    //     frm.refresh_fields("earning","deduction")
    // },
    form_type: function (frm) {
        // cur_frm.set_df_property('reason_for_leaving', 'reqd', frm.doc.form_type=='End of Service' ? 1:0);
        frm.toggle_reqd("contract_type", frm.doc.form_type === 'End of Service' ? 1 : 0);
        frm.toggle_reqd("reason_for_leaving", frm.doc.form_type === 'End of Service' ? 1 : 0);
        frm.toggle_reqd("leave_application", frm.doc.form_type === 'Adjustment' ? 1 : 0);
        if (frm.doc.form_type === 'End of Service') {
            frm.set_value("ignore_loan", 0);
        }


        frm.trigger("years_of_service")
    },
    contract_type: function (frm) {
        if (!frm.doc.contract_type) {
            frm.set_value("reason_for_leaving", "");
        }
    },
    employee: function (frm) {
        frm.trigger("years_of_service")
        frm.trigger("get_contract")
    },
    relieving_date: function (frm) {
        frm.trigger("years_of_service")
    },
    get_contract: function (frm) {
        if (frm.doc.employee) {
            frappe.call({
                method: "get_employee_contract",
                doc: frm.doc,
                args: {
                    "employee": frm.doc.employee
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("contract", r.message)
                        frm.refresh_field("contract")
                    }
                }
            });
        }
    },
    years_of_service: function (frm) {
        if (frm.doc.employee && frm.doc.relieving_date && frm.doc.form_type) {
            frappe.call({
                method: "get_years_of_service",
                doc: frm.doc,
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("years", r.message["years"])
                        frm.set_value("months", r.message["months"])
                        frm.set_value("days", r.message["days"])

                        frm.set_value("adj_years", r.message["adj_years"])
                        frm.set_value("adj_months", r.message["adj_months"])
                        frm.set_value("adj_days", r.message["adj_days"])
                    }
                }
            });
            // frm.trigger("calculate_total_leaves_allocated");
        }
        else {
            frm.set_value("years", 0)
            frm.set_value("months", 0)
            frm.set_value("days", 0)

            frm.set_value("adj_years", 0)
            frm.set_value("adj_months", 0)
            frm.set_value("adj_days", 0)
            frm.set_value("current_leave_balance", 0);
        }

    },
    calculate_total_leaves_allocated: function (frm) {
        return frappe.call({
            method: "hrms.hr.doctype.leave_allocation.leave_allocation.get_carry_forwarded_leaves",
            args: {
                "employee": frm.doc.employee,
                "date": frm.doc.relieving_date,
                "leave_type": '',
                "till_now": true
            },
            callback: function (r) {
                if (!r.exc && r.message) {
                    // if (parseFloat(r.message) > 0) {
                    //     frm.set_value('current_leave_balance', r.message);
                    // }
                    // else {
                    //     frm.set_value('current_leave_balance', 0);
                    // }
                    // check for Leave Balance Adjustment
                    // getLeaveBalanceAdjustmentDays(frm, (LeaveBalanceAdjustmentDays) => {
                    //     frm.set_value('current_leave_balance', frm.doc.current_leave_balance + LeaveBalanceAdjustmentDays);
                    // });
                    refresh_field("current_leave_balance");
                }
            }
        });
    },
    // validate:function (frm) {
    //     if(!frm.is_new()) {
    //         // frappe.ui.toolbar.clear_cache()
    //     }

    // }
});

const getLeaveBalanceAdjustmentDays = function (frm, callbackMethodArg) {
    frappe.call({
        method: "hrms.hrms.doctype.end_of_service.end_of_service.get_Leave_balance_adjustment_days",
        args: {
            employee: frm.doc.employee,
            last_working_date: frm.doc.relieving_date
        },
        callback: function (r) {
            if (r.message) {
                callbackMethodArg(r.message);
            }
        },
        error: (r) => {
            frappe.msgprint(`Error: Check your inputs, ${r}`);
        }
    });
}

cur_frm.cscript.get_earnings = function () {
    cur_frm.doc.earnings = [];
    cur_frm.doc.deductions = [];
    cur_frm.doc.loans = [];
    cur_frm.call("calculate_net_pay");
}
