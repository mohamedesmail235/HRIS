# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
import frappe
from frappe import _
from frappe.utils.data import date_diff, add_days, cint, add_months, flt, getdate
from hris.utils.utils import get_dates_diff, apply_leave_allocation_policy
from erpnext.setup.doctype.employee.employee import Employee


class CustomEmployee(Employee):
    def autoname(self):
        id = frappe.db.sql("""
			select cast(`name` as UNSIGNED) +1 id
				from tabEmployee
				order by `name` desc
				limit 1
			""", as_dict=True)
        if id:
            self.name = str(id[0]["id"])
            self.employee_number = str(id[0]["id"])

    def after_insert(self):
        leave_days_no = self.update_yearly_vacation()
        self.db_set("yearly_vacation", leave_days_no)
        apply_leave_allocation_policy(self.name)

    @frappe.whitelist()
    def update_yearly_vacation(self):
        leave_days_no = 0
        data = frappe.get_list("Leave Category", filters={'parent': self.employee_leave_category}, fields=[
                               'years_from', 'years_to', 'leave_days_no'], order_by="idx desc")
        if data:
            service_details = self.get_years_of_service()
            if len(data) > 1:
                for item in data:
                    if flt(item["years_to"]) >= cint(service_details["years"]) >= flt(item["years_from"]):
                        self.yearly_vacation = flt(item["leave_days_no"])
                        leave_days_no = flt(item["leave_days_no"])
            else:
                self.yearly_vacation = flt(data[0]["leave_days_no"])
                leave_days_no = flt(data[0]["leave_days_no"])

            if not flt(self.yearly_vacation) > 0:
                frappe.throw(_("يرجي مراجعة فئات أجازات الموظفين"))

        return leave_days_no

    def get_years_of_service(self):
        date_of_joining = frappe.db.get_value(
            "Employee", self.employee, "date_of_joining")
        if (not date_of_joining):
            frappe.throw("Please set date of joining")
        deducted_days = frappe.db.get_value("Deduct Days from Service Period",
                                            {"name": self.employee, "type": "Service Period"}, "number_of_days") or 0

        service_details = get_dates_diff(
            add_days(date_of_joining, deducted_days), add_days(getdate(), 1))
        # frappe.msgprint("service_details==================="+str(service_details))
        return service_details
