# -*- coding: utf-8 -*-
# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import erpnext
import datetime
from datetime import datetime
from frappe.model.document import Document
from hrms.hr.utils import get_holiday_dates_for_employee, validate_active_employee
from hris.utils.utils import get_dates_diff, get_month_days
from frappe.utils import add_days, add_months, cint, cstr, flt, getdate, rounded, date_diff, get_last_day, formatdate, add_years
from frappe.utils.data import get_first_day, get_last_day
from frappe import _
from hrms.hr.utils import get_leave_period
# from erpnext.payroll.doctype.additional_salary.additional_salary import get_additional_salaries
from hrms.hr.doctype.leave_application.leave_application \
    import get_leave_allocation_records, get_leave_balance_on, get_approved_leaves_for_period
from hris.utils.utils import get_month_days, get_last_day
from hris.overrides.leave_application import get_allocation_expiry_for_cf_leaves, get_leaves_for_period, \
    get_remaining_leaves
import traceback
from hris.utils.utils import get_dates_diff_in_month, get_additional_salaries

from hrms.payroll.doctype.salary_slip.salary_slip import get_salary_component_data


class EndofService(Document):

    def __init__(self, *args, **kwargs):
        super(EndofService, self).__init__(*args, **kwargs)
        self.whitelisted_globals = {
            "int": int,
            "float": float,
            "long": int,
            "round": round,
            "date": datetime.date,
            "getdate": getdate
        }

    def validate(self):
        self.total_base_earnigns = 0
        date_of_joining = self.get_last_join_date()
        self.last_joining_day = date_of_joining
        if date_diff(self.relieving_date, date_of_joining) < 0:
            frappe.throw(
                _("Last Working Day must be after Joining Date {0}".format(date_of_joining)))
        self.total_base_earnigns = self.get_component_totals(
            "earning", statical_component=True)  # flt(self.earning_amount)

    def before_save(self):
        self.calculate_net_pay()

    def on_submit(self):
        frappe.db.set_value("Employee", self.employee, "status", "Left")
        frappe.db.set_value("Employee", self.employee,
                            "relieving_date", self.relieving_date)
        frappe.db.set_value("Employee", self.employee,
                            "reason_for_leaving", self.reason_for_leaving)

    def on_cancel(self):
        frappe.db.set_value("Employee", self.employee, "status", "Active")
        frappe.db.set_value("Employee", self.employee, "relieving_date", None)
        frappe.db.set_value("Employee", self.employee,
                            "reason_for_leaving", None)

    @frappe.whitelist()
    def get_years_of_service(self):
        date_of_joining = frappe.db.get_value(
            "Employee", self.employee, "date_of_joining")
        if (not date_of_joining):
            frappe.throw("Please set date of joining")
        deducted_days = frappe.db.get_value("Deduct Days from Service Period",
                                            {"name": self.employee, "type": "Service Period"}, "number_of_days") or 0
        unpaid_leaves_days = 0
        unpaid_leaves = frappe.db.sql("""
                select sum(total_leave_days) total_leave_days 
                    from `tabLeave Application`
                        where leave_type='Unpaid Leave'
                                and employee='{employee}'
                                and docstatus=1;
            """.format(employee=self.employee), as_dict=True)
        if unpaid_leaves:
            unpaid_leaves_days = flt(unpaid_leaves[0]["total_leave_days"])
        deducted_days += unpaid_leaves_days
        if flt(deducted_days) > 20:
            deducted_days -= 20
        else:
            deducted_days = 0

        self.deduct_days_from_service_period = deducted_days
        self.leave_without_pay = deducted_days
        service_details = get_dates_diff(
            add_days(date_of_joining, deducted_days), add_days(self.relieving_date, 1))

        date_of_joining = self.get_last_join_date()
        adj_service_details = get_dates_diff(
            add_days(date_of_joining, deducted_days), add_days(self.relieving_date, 1))
        service_details["adj_years"] = (adj_service_details["years"] if cint(
            adj_service_details["years"]) > 0 else 0)
        service_details["adj_months"] = (
            adj_service_details["months"] if cint(adj_service_details["months"]) > 0 else 0)
        service_details["adj_days"] = (adj_service_details["days"] if cint(
            adj_service_details["days"]) > 0 else 0)

        return service_details

    def get_lwp_unpaid_leaves(self):  # MiM Unpaid Leave
        pass

    def add_additional_salary_components(self):
        # end_date = str(getdate(self.relieving_date).year)+"-"+ str(getdate(self.relieving_date).month)+"-"+ str(get_month_days(self.relieving_date))
        # start_date = str(getdate(str(self.relieving_date)).year)+"-"+ str(getdate(str(self.relieving_date)).month)+"-"+str(get_first_day(self.relieving_date))--
        self.over_time_hours = 0
        month_working_days = getdate(self.relieving_date).day
        month_working_days = month_working_days - cint(self.advance_leave_days)
        days_in_month = cint(get_month_days(self.start_date))

        additional_components = get_additional_salaries(
            self.employee, self.start_date, get_last_day(add_months(self.end_date, 1)), "earnings")

        hrms_settings = frappe.db.get_singles_dict("HRMS Settings")
        start_date = add_months(self.start_date, -1)
        start_date = getdate(str(getdate(start_date).year)+"-"+str(
            getdate(start_date).month)+"-" + str(hrms_settings.deductions_start_day))

        # get _all deduction and future one
        additional_salaries_deductions = get_additional_salaries(
            self.employee, start_date, self.end_date, "deductions")

        if not additional_salaries_deductions in additional_components:
            additional_components += additional_salaries_deductions

        # get _all deduction and future one
        future_deductions = get_additional_salaries(self.employee, add_days(
            self.end_date, 1), add_years(self.relieving_date, 3), "deductions")
        if not future_deductions in additional_components:
            additional_components += future_deductions

        if additional_components:
            for additional_component in additional_components:
                amount = additional_component.amount
                key = "earning" if additional_component.type == "Earning" else "deduction"
                overwrite = additional_component.overwrite

                include_in_indemnity = frappe.db.get_value("Salary Component", {
                                                           "name": additional_component.component, "type": "Earning"}, "include_in_indemnity")
                if additional_component.type == "Earning":
                    if include_in_indemnity:
                        self.include_in_indemnity_amount += amount
                        self.update_component_row(self.get_salary_component_data(
                            additional_component.component), amount, key, overwrite=0)

                saved = False
                add_to_5_and_15_batch = frappe.db.get_value(
                    "Salary Component", additional_component.component, "add_to_5_and_15_batch") or 0
                add_to_5_and_15_batch = 1 if add_to_5_and_15_batch == 1 else 0
                if additional_component.type == "Earning" and add_to_5_and_15_batch == 1:
                    saved = self.check_is_saved_addtional_salary(
                        additional_component.component, additional_component.amount)
                elif additional_component.type == "Earning" and add_to_5_and_15_batch == 0:
                    saved = self.check_saved_slip(
                        get_first_day(self.relieving_date),
                        get_last_day(self.relieving_date),
                        payroll_frequency="Monthly",
                        component=additional_component.component,
                        amount=additional_component.amount
                    )
                elif additional_component.type == "Deduction":
                    saved = self.check_saved_slip(
                        self.start_date,
                        self.end_date,
                        payroll_frequency="Monthly",
                        component=additional_component.component,
                        amount=additional_component.amount
                    )

                if additional_component.statistical_component in (0, None) and additional_component.type == "Earning" and frappe.db.get_value("Salary Component", additional_component.component, "include_in_deduction") and add_to_5_and_15_batch == 0:
                    self.absent_amount += (self.absent_days /
                                           cint(get_month_days(self.start_date))) * flt(amount)

                if frappe.db.get_value("Salary Component", {"name": additional_component.component, "type": "Earning"}, "include_in_leave_encashment_") == 1:
                    self.for_leave_encashment += amount

                if saved:
                    continue

                if additional_component.component == "Over Time Allowance":
                    if additional_component.from_over_time:
                        self.over_time_hours += cint(frappe.db.get_value(
                            "Employee Hours Details", additional_component.from_over_time, "over_time_in_working_hours"))

                is_recurring = frappe.db.get_value(
                    "Additional Salary", additional_component.name, "is_recurring")

                if additional_component.type == "Earning":
                    if is_recurring:
                        amount = (flt(amount) / days_in_month) * (
                            month_working_days if month_working_days <= days_in_month else days_in_month)

                overwrite = additional_component.overwrite
                key = "earnings" if additional_component.type == "Earning" else "deductions"
                if (additional_component.type == "Deduction" and is_recurring == 1):
                    amount = self.calculate_is_recurring_deduction(
                        additional_component.name, self.start_date)
                elif (additional_component.type == "Deduction" and getdate(self.relieving_date) >= getdate(additional_component.payroll_date)):
                    amount = additional_component.amount

                self.update_component_row(self.get_salary_component_data(
                    additional_component.component), amount, key, overwrite=0, adsal=additional_component)  # .get("from_traffic_violation")

    def calculate_is_recurring_deduction(self, additional_name, from_date):
        data = frappe.db.get_values(
            "Additional Salary",
            additional_name,
            fieldname=["amount", "from_date", "to_date"],
            as_dict=True,
        )[0]
        amount = flt(data["amount"])
        months = get_dates_diff_in_month(str(from_date), str(data["to_date"]))
        amount += flt(months) * flt(data["amount"])
        # print('\n'*3,getdate(self.relieving_date).month,getdate(data["to_date"]).month,'\n'*5)
        # if getdate(self.relieving_date).month != getdate(data["to_date"]).month:
        #     months = get_dates_diff_in_month(
        #         str(self.start_date), str(data["to_date"]))
        #     amount += flt(months) * flt(data["amount"])
        return amount

    def check_is_saved_addtional_salary(self, component="", amount=0):
        hrms_settinngs = frappe.db.get_singles_dict("HRMS Settings")

        first_half_month_start_day = hrms_settinngs.first_half_month_start_day
        first_half_month_end_day = hrms_settinngs.first_half_month_end_day

        day_15_start_date = getdate(
            str(getdate(self.relieving_date).year) + "-" + str(getdate(self.relieving_date).month) + "-" + str(
                first_half_month_start_day))
        day_15_end_date = getdate(
            str(getdate(self.relieving_date).year) + "-" + str(getdate(self.relieving_date).month) + "-" + str(
                first_half_month_end_day))

        second_half_month_start_day = hrms_settinngs.second_half_month_start_day
        second_half_month_end_day = hrms_settinngs.second_half_month_end_day

        year = getdate(self.relieving_date).year
        next_year = getdate(self.relieving_date).year
        month = getdate(self.relieving_date).month
        next_month = getdate(self.relieving_date).month

        if getdate(self.relieving_date).day >= 13:
            next_month = getdate(self.relieving_date).month + 1
            if getdate(self.relieving_date).month == 12:
                next_year += 1
                next_month = 1
        else:
            month = getdate(self.relieving_date).month - 1
            if getdate(self.relieving_date).month == 1:
                year -= 1
                month = 12

        day_5_start_date = getdate(
            str(year) + "-" + str(month) + "-" + str(second_half_month_start_day))
        day_5_end_date = getdate(
            str(next_year) + "-" + str(next_month) + "-" + str(second_half_month_end_day))

        # or getdate(self.relieving_date).month
        if getdate(self.relieving_date).day > 15 or getdate(self.relieving_date).month == getdate(day_5_start_date).month:
            day_5_start_date = get_first_day(self.relieving_date)

        start_date = day_5_start_date  # get_first_day(self.relieving_date)
        end_date = get_last_day(self.relieving_date)
        return self.check_saved_slip(day_5_start_date, end_date, "", component, amount)

        # if day_15_end_date >= getdate(self.relieving_date) >= day_15_start_date:
        #     return self.check_saved_slip(day_15_start_date, day_15_end_date, "")
        # elif day_5_end_date >= getdate(self.relieving_date) >= day_5_start_date:
        #     return self.check_saved_slip(day_5_start_date, day_5_end_date, "")

    def check_saved_slip(self, start_date, end_date, payroll_frequency, component="", amount=0):
        amount = round(amount, 2)

        condition = ""
        if payroll_frequency == "Monthly":
            condition = " and S.payroll_frequency = 'Monthly' "
        else:
            condition = " and S.payroll_frequency != 'Monthly' "

        # if flt(amount) > 0:
        #     condition += " and D.amount = '{amount}' ".format(
        #         amount=round(amount, 2))

        if component and amount:
            condition += f" and D.salary_component = '{component}' and D.amount = {amount}"

        sql_strng = """
			select S.gross_pay
                from `tabSalary Slip` S
                    inner JOIN
                    `tabSalary Detail` D
                        on S.`name`= D.parent
					where S.employee = '{employee}'
							and (S.start_date BETWEEN '{start_date}' and '{end_date}' or S.end_date BETWEEN '{start_date}' and '{end_date}')
							{condition}
			
		    """.format(condition=condition, employee=self.employee, start_date=start_date, end_date=end_date, amount=amount)

        saved = frappe.db.sql("""
			select S.gross_pay
                from `tabSalary Slip` S
                    inner JOIN
                    `tabSalary Detail` D
                        on S.`name`= D.parent
					where S.employee = '{employee}'
							and (S.start_date BETWEEN '{start_date}' and '{end_date}' or S.end_date BETWEEN '{start_date}' and '{end_date}')
							{condition}
			
		    """.format(condition=condition, employee=self.employee, start_date=start_date, end_date=end_date, amount=amount), as_dict=True, debug=True)

        if saved:
            return True
        else:
            return False

    def get_salary_component_data(self, component):
        return frappe.get_value(
            "Salary Component",
            component,
            [
                "name as salary_component",
                "depends_on_payment_days",
                "salary_component_abbr as abbr",
                "do_not_include_in_total",
                "is_tax_applicable",
                "is_flexible_benefit",
                "variable_based_on_taxable_salary",
            ],
            as_dict=1,
        )

    def get_tickets_details(self):
        tickets_details = frappe.db.get_list("Airplane Tickets Request",
                                             filters={
                                                 "employee": self.employee, "contract": self.contract},
                                             fields=["employee_share", "company_share"])
        if tickets_details:
            for item in tickets_details:
                amount = item.employee_share
                self.company_share = item.company_share
                item.salary_component = "Tickets Employee Share"
                item.abbr = "TES"
                self.update_component_row(frappe._dict(
                    item), amount, "deductions", overwrite="overwrite")

    def calculate_component_amounts(self):
        self.include_in_indemnity_amount = 0.0
        data = self.get_employee_data_for_eval()

        month_days = get_month_days(self.relieving_date)

        from calendar import monthrange
        # monthrange(getdate(self.relieving_date).year, getdate(self.relieving_date).month)[1]
        days_in_month = cint(get_month_days(self.relieving_date))
        month_working_days = getdate(self.relieving_date).day
        month_working_days = month_working_days - cint(self.advance_leave_days)
        get_last_day(self.relieving_date)
        if cint(month_working_days) >= cint(days_in_month):
            month_working_days = days_in_month
        elif cint(month_working_days) == cint(days_in_month):
            month_working_days = 30
        elif cint(month_working_days) == get_last_day(self.relieving_date).day:
            month_working_days = 30

        # frappe.msgprint("========="+str(get_last_day(self.relieving_date).day))
        # frappe.msgprint(str(month_working_days))

        date_of_joining = self.get_last_join_date()
        if getdate(date_of_joining).month == getdate(self.relieving_date).month and getdate(date_of_joining).year == getdate(self.relieving_date).year:
            month_working_days = date_diff(
                self.relieving_date, date_of_joining) + 1
            # frappe.msgprint("month_working_days========" + str(month_working_days))

        # frappe.msgprint(str(date_of_joining))
        # frappe.msgprint("month_working_days========"+str(month_working_days))
        # base_eos_sal = frappe.db.get_value("Salary Slip", filters={"employee": self.employee,"start_date":self.start_date}, fieldname =["gross_pay"])#  "docstatus": "1",
        base_eos_sal = frappe.db.sql("""
			select gross_pay
				from `tabSalary Slip`
					where employee = %s
							and month(start_date) = %s
							and year(start_date) = %s
							and payroll_frequency = 'Monthly'
		""", (self.employee, getdate(self.relieving_date).month, getdate(self.relieving_date).year), as_dict=True)
        if base_eos_sal:
            base_eos_sal = base_eos_sal[0]["gross_pay"]
        # base_eos_sal = self.check_saved_slip(self.relieving_date,self.relieving_date,payroll_frequency="Monthly")

        # self.earnings = []
        # self.deductions = []
        self.for_leave_encashment = 0.0
        self.late_minutes_amount = 0
        # if not base_eos_sal:
        self.add_additional_salary_components()
        self.get_tickets_details()
        for key in ('earnings', 'deductions'):
            for struct_row in self._salary_structure_doc.get(key):
                include_in_indemnity = frappe.db.get_value("Salary Component", struct_row.salary_component,
                                                           "include_in_indemnity")
                if key == "earnings":
                    amount = self.eval_condition_and_formula(struct_row, data)

                    if struct_row.salary_component == "Transportation" and amount < 300:
                        amount = 300

                    if struct_row.salary_component == "Housing" and amount < 750 and not struct_row.statistical_component:
                        amount = 750
                    if struct_row.statistical_component == 0 and frappe.db.get_value("Salary Component", struct_row.salary_component, "include_in_deduction"):
                        self.absent_amount += (self.absent_days / cint(
                            get_month_days(self.start_date))) * flt(amount)
                        self.late_minutes_amount += self.late_minutes_perc * \
                            flt(amount)

                    if include_in_indemnity:
                        self.include_in_indemnity_amount += amount

                    if key == "earnings" and frappe.db.get_value("Salary Component", struct_row.salary_component,
                                                                 "include_in_leave_encashment_") == 1:
                        self.for_leave_encashment += amount
                    if amount:  # and not base_eos_sal:  # struct_row.statistical_component == 0 and
                        self.update_component_row(
                            struct_row, amount, "earning")
                    # frappe.msgprint(str(struct_row.salary_component) + "======" + str(amount) + "======" + str(days_in_month) + "======>" + str(month_working_days))
                    amount = (flt(amount) / days_in_month) * month_working_days

                    if amount and struct_row.statistical_component == 0 and not base_eos_sal:
                        self.update_component_row(struct_row, amount, key)

                elif key == "deductions":
                    amount = self.eval_condition_and_formula(struct_row, data)

                    amount = (flt(amount) / days_in_month) * month_working_days

                    # self.absent_amount += (self.absent_days /
                    #                        cint(get_month_days(self.start_date))) * flt(amount)

                    if amount and struct_row.statistical_component == 0 and not base_eos_sal:
                        self.update_component_row(struct_row, amount, key)

        closing, paid_leave = 0.0, 0.0
        filters = frappe._dict()
        start_date = get_first_day(self.relieving_date)

        if date_diff(self.relieving_date, self.joining_date) < 1:
            frappe.throw(_("relieving date should be after joining date"))
        self.total_leave_encashed = 0
        # frappe.msgprint("for_leave_encashment===" + str(for_leave_encashment))
        if self.for_leave_encashment > 0:
            deducted_days = frappe.db.get_value("Deduct Days from Service Period", {
                "name": self.employee, "type": "Leave En-Cash"}, "number_of_days") or 0
            # leave_category_details =
            calculate_leave_encasement = (
                frappe.db.get_single_value("HRMS Settings", "calculate_leave_encasement") or "Day Rate")
            if calculate_leave_encasement == "Day Rate":
                day_rate = str(flt(self.for_leave_encashment) /
                               month_days)  # month_working_days
                # frappe.msgprint(str(for_leave_encashment)+"====day_rate===="+str(day_rate)+"====month_working_days===="+str(month_days))

                if self.current_leave_balance > self.leave_balance:
                    self.current_leave_balance = self.leave_balance
                elif flt(self.current_leave_balance) < 0:
                    self.current_leave_balance = 0

                self.total_leave_encashed = round(
                    flt(day_rate) * round(flt(self.current_leave_balance), 2), 2)
            else:
                if self.contract:
                    last_join_date = self.get_last_join_date()

                    contract_duration_days = (
                        cint(self.contract_duration) * 30) + flt(deducted_days)
                    # if cint(date_diff(self.relieving_date,last_join_date)) < contract_duration_days :
                    # 	self.total_leave_encashed = flt((flt(for_leave_encashment)/11) * (cint(self.years) + cint(self.months) + (flt(self.days) /30)))
                    # else:

                    service_duration_days = contract_duration_days - \
                        (cint(self.yearly_vacation) *
                         (flt(self.contract_duration) / 12))

                    service_duration_months = flt(service_duration_days / 30)

                    total_sevice_months = (
                        cint(self.adj_years) * 12) + cint(self.adj_months) + (
                        flt(self.adj_days) / 30)

                    # frappe.msgprint(str(self.adj_years))
                    # frappe.msgprint(str(self.adj_months))
                    # frappe.msgprint(str(self.adj_days))
                    # frappe.msgprint("total_sevice_months==="+str(total_sevice_months))

                    leaves = frappe.db.get_all("Leave Application",
                                               filters={"docstatus": 1, "employee": self.employee,
                                                        "leave_type": "Casual Leave",
                                                        # "not_affect_the_leave_en_cash":0,
                                                        "from_date": ["between",
                                                                      [self.last_joining_day, self.relieving_date]], \
                                                        "to_date": ["between",
                                                                    [self.last_joining_day, self.relieving_date]]},
                                               fields=["*"])
                    total_leave_days_tacken = 0
                    deducted_leaves = 0
                    if leaves and self.form_type == "End of Service":
                        for item in leaves:
                            total_leave_days_tacken += flt(
                                item["total_leave_days"])

                        # frappe.msgprint("total_leave_days===" + str(total_leave_days_tacken))

                        # leave_rate_per_month = (cint(self.yearly_vacation)/30) / flt(self.contract_duration)
                        leave_rate_per_month = (flt(self.yearly_vacation) / 12)
                        total_leave_days_tacken = flt(
                            total_leave_days_tacken) / flt(leave_rate_per_month)
                        total_leave_days = flt(
                            total_sevice_months) * flt(leave_rate_per_month)
                        total_sevice_months -= total_leave_days_tacken
                        # frappe.msgprint("leave_rate_per_month===" + str(((cint(total_leave_days) * (flt(self.contract_duration) / 12)) / 30)))
                        # deducted_leaves = flt(total_leave_days) * leave_rate_per_month
                        # frappe.msgprint("leave_rate_per_month===" + str(leave_rate_per_month))
                        # if deducted_leaves > 0:
                        #     total_sevice_months-= deducted_leaves

                    # frappe.msgprint("total_sevice_months===" + str(total_sevice_months))
                    # frappe.msgprint("self.yearly_vacation===" + str(self.yearly_vacation))
                    # frappe.msgprint("service_duration_months===" + str(service_duration_months))

                    self.total_leave_encashed = round((flt(self.for_leave_encashment) / service_duration_months) * (
                        (cint(self.yearly_vacation) * (
                            flt(self.contract_duration) / 12)) / 30) * total_sevice_months, 2)
            # frappe.msgprint("self.total_leave_encashed===" + str(self.total_leave_encashed))
            if self.total_leave_encashed < 0:
                self.total_leave_encashed = 0

    def add_late_minutes_deductions(self):
        late_minutes, late_minutes_percetage = 0, 0

        hrms_settings = frappe.db.get_singles_dict("HRMS Settings")
        start_date = add_months(self.start_datestart_date, -1)
        start_date = getdate(str(getdate(start_date).year)+"-"+str(
            getdate(start_date).month)+"-" + str(hrms_settings.deductions_start_day))
        end_date = add_days(self.start_date, cint(
            hrms_settings.deductions_end_day)-1)

        minutes = frappe.db.sql("""
                select sum(late_minutes) late_minutes
                    from `tabLate Minutes`
                        where employee = '{employee}'
                            and day_date between '{start_date}' and '{end_date}'
                                and docstatus = 1
                """.format(employee=self.employee, start_date=start_date, end_date=end_date), as_dict=True)
        if minutes:
            late_minutes = minutes[0]["late_minutes"]

            monthly_working_hours = frappe.db.get_single_value(
                'HRMS Settings', 'monthly_working_hours')
            if monthly_working_hours == 0:
                msg = _("Please Add Monthly Working Hours in HRMS Settings")
                self.update_payroll_entry(msg)
                frappe.throw(msg)

            late_minutes_percetage = flt(
                late_minutes) / (flt(monthly_working_hours)*60)

        return late_minutes_percetage

    def get_last_join_date(self):
        last_join_date = ""
        last_join = frappe.db.sql("""
			select joining_date
				from `tabBack From Leave`
				where employee = %s
					and docstatus = 1
					-- and leave_type ='Casual Leave'
				order by from_date desc 
				limit 1
		""", (self.employee), as_dict=True)

        if last_join:
            last_join_date = last_join[0]["joining_date"]
        else:
            if not self.joining_date:
                frappe.throw(_("Please Check Joning Date"))
            last_join_date = self.joining_date

        return last_join_date

    @frappe.whitelist()
    def calculate_net_pay(self):
        self.deductions = self.earnings = []
        self.balance_loan_amount = 0
        self.absent_amount = 0
        self.absent_days = 0
        self.advance_leave_days = 0
        self.start_date = str(get_first_day(self.relieving_date))
        self.end_date = get_last_day(self.relieving_date)

        self.advance_leave_days = self.get_advance_days()

        self.total_indemnity = 0
        payroll_based_on = frappe.db.get_value(
            "Payroll Settings", None, "payroll_based_on")
        holidays = self.get_holidays_for_employee(
            self.start_date, self.end_date)

        if not payroll_based_on:
            msg = _("Please set Payroll based on in Payroll settings")
            frappe.throw(msg)

        if payroll_based_on == "Leave":
            hrms_settings = frappe.db.get_singles_dict("HRMS Settings")
            start_date = add_months(self.start_date, -1)
            start_date = getdate(str(getdate(start_date).year) + "-" + str(
                getdate(start_date).month) + "-" + str(hrms_settings.deductions_start_day))

            actual_lwp = self.calculate_lwp_ppl_and_absent_days_based_on_attendance(
                holidays, self.start_date, self.end_date)[0] or 0

            absence_cutoff_end_date = self.get_cutoff_end_date_for_last_submitted_salary_slip_with_absent()

            if absence_cutoff_end_date:
                absent = self.calculate_lwp_ppl_and_absent_days_based_on_attendance(
                    holidays, absence_cutoff_end_date, self.end_date)[1] or 0
            else:
                # get cutoff end date for the relieving_date  (relieving_date-1 / 15)
                # (relieving_date-1 / 15) to the reliving date
                # relieving_date_cutoff_start_date = self.get_cutoff_end_date_for_relieving_date()
                absent = self.calculate_lwp_ppl_and_absent_days_based_on_attendance(
                    holidays, start_date, self.end_date)[1] or 0

            self.absent_days = absent

            # self.late_minutes_perc = self.add_late_minutes_deductions(self.start_date, self.end_date)

            cutoff_end_date = self.get_cutoff_end_date_for_last_submitted_salary_slip_with_late_minutes()
            if cutoff_end_date:
                self.late_minutes_perc = self.add_late_minutes_deductions(
                    cutoff_end_date, self.relieving_date)
            else:
                # get cutoff end date for the relieving_date  (relieving_date-1 / 15)
                # (relieving_date-1 / 15) to the reliving date
                relieving_date_cutoff_start_date = self.get_cutoff_end_date_for_relieving_date()
                self.late_minutes_perc = self.add_late_minutes_deductions(
                    relieving_date_cutoff_start_date, self.relieving_date)

        # self.absent_amount += (self.absent_days / cint(get_month_days(self.start_date))) * flt(default_amount)

        self.get_leave_balance()
        self.check_futural_credit()
        self.calculate_component_amounts()

        if self.absent_amount > 0:
            self.update_component_row(get_salary_component_data(
                "Absence"), self.absent_amount, 'deductions')

        if self.late_minutes_amount > 0:
            self.update_component_row(get_salary_component_data(
                "Late Minutes"), self.late_minutes_amount, 'deductions')

        self.calculate_penalty()

        self.earning_amount = self.get_component_totals("earning")
        self.deduction_sum = self.get_component_totals("deduction")

        self.gross_pay = self.get_component_totals("earnings")
        self.total_deduction = self.get_component_totals("deductions")

        # if self.ignore_loan:
        #     self.set('loans', [])
        # else:
        #     self.set_loan_repayment()

        # - (flt(self.total_deduction))
        self.net_sum = flt(self.earning_amount)
        self.total_base_earnigns = self.get_component_totals(
            "earning", statical_component=True)  # flt(self.earning_amount)
        # + flt(self.total_loan_repayment)
        self.net_pay = flt(self.gross_pay) - (flt(self.total_deduction))
        # self.net_pay = rounded(self.net_pay)
        if self.form_type == 'End of Service':
            is_paid = frappe.db.get_value("Reason for Leaving", filters={"name": self.reason_for_leaving},
                                          fieldname=["paid"])
            if is_paid:
                idemnity_amount = self.calculate_idemnity_amount()
                # - flt(self.total_principal_amount - self.total_loan_repayment)
                self.total_indemnity = flt(idemnity_amount)
            else:
                self.total_indemnity = 0.0
        # frappe.msgprint("net_pay=============>" + str(self.net_pay))
        self.total_net_pay = ((self.total_indemnity if self.form_type == 'End of Service' else 0) +
                              self.net_pay + self.total_leave_encashed) - self.balance_loan_amount

    def get_advance_days(self):
        advance_leave_days = 0
        advance_days = frappe.db.get_all("Advance Leave", filters={"employee": self.employee, "end_date": [
                                         "between", (self.start_date, self.end_date)]}, fields="*")
        if advance_days:
            advance_leave_days = date_diff(
                advance_days[0]["end_date"], self.start_date)+1
        return advance_leave_days

    def get_cutoff_end_date_for_last_submitted_salary_slip_with_absent(self):
        cutoff_end_date = None
        try:
            ss_start_date = frappe.db.sql(f"""select s.start_date as start_date  
                    from `tabSalary Slip` s inner join `tabSalary Detail` d on d.parent = s.`name`
                    where s.docstatus=1 and s.employee={self.employee} and d.parentfield = 'deductions' and d.salary_component="Absence" and d.amount > 0
                    order by s.start_date desc limit 1;""",
                                          as_dict=1,
                                          debug=True
                                          )
            if ss_start_date:
                cutoff_end_date = datetime(
                    ss_start_date[0].start_date.year, ss_start_date[0].start_date.month, 16)
            else:
                ss_start_date = frappe.db.get_value("Salary Slip", {
                    "payroll_frequency": "Monthly",
                    "docstatus": 1,
                    "employee": self.employee
                },
                    "start_date", order_by="start_date desc")
                if ss_start_date:
                    cutoff_end_date = datetime(
                        ss_start_date.year, ss_start_date.month, 16)
            return cutoff_end_date.date()
        except Exception as ex:
            frappe.log_error(frappe.get_traceback(
            ), "get_cutoff_end_date_for_last_submitted_salary_slip_with_absent:end_of_service")
            return cutoff_end_date

    def get_cutoff_end_date_for_last_submitted_salary_slip_with_late_minutes(self):
        cutoff_end_date = None
        try:
            ss_posting_date = frappe.db.sql(f"""select s.posting_date 
                    from `tabSalary Slip` s inner join `tabSalary Detail` d on d.parent = s.`name`
                    where s.docstatus=1 and s.employee={self.employee} and d.parentfield = 'deductions' and d.salary_component="Late Minutes" and d.amount > 0
                    order by s.creation desc limit 1;""",
                                            as_dict=1
                                            )
            if ss_posting_date:
                cutoff_end_date = datetime(
                    ss_posting_date[0].posting_date.year, ss_posting_date[0].posting_date.month, 15
                )
            return cutoff_end_date
        except Exception as ex:
            frappe.log_error(frappe.get_traceback(
            ), "get_cutoff_end_date_for_last_submitted_salary_slip_with_late_minutes:end_of_service")
            return cutoff_end_date

    def get_cutoff_end_date_for_relieving_date(self):
        if getdate(self.relieving_date).month == 1:
            relieving_date_cutoff_start_date = datetime(
                getdate(self.relieving_date).year - 1, 12, 15)
        else:
            relieving_date_cutoff_start_date = datetime(
                getdate(self.relieving_date).year, getdate(self.relieving_date).month - 1, 15)
        return relieving_date_cutoff_start_date

    def add_late_minutes_deductions(self, start_date, end_date):
        late_minutes, late_minutes_percetage = 0, 0

        minutes = frappe.db.sql("""
                select sum(late_minutes) late_minutes
                    from `tabLate Minutes`
                        where employee = '{employee}'
                            and day_date between '{start_date}' and '{end_date}'
                                and docstatus = 1
                """.format(employee=self.employee, start_date=start_date, end_date=end_date), as_dict=True)
        if minutes:
            late_minutes = minutes[0]["late_minutes"]
            self.late_time_minutes = late_minutes
            monthly_working_hours = frappe.db.get_single_value(
                'HRMS Settings', 'monthly_working_hours')
            if monthly_working_hours == 0:
                msg = _("Please Add Monthly Working Hours in HRMS Settings")
                frappe.throw(msg)

            late_minutes_percetage = flt(
                late_minutes) / (flt(monthly_working_hours)*60)

        return late_minutes_percetage

    def get_holidays_for_employee(self, start_date, end_date):
        return get_holiday_dates_for_employee(self.employee, start_date, end_date)

    def get_leave_balance(self):
        leave_types = []
        leaves_taken, opening, closing = 0.0, 0.0, 0.0
        date_of_joining = frappe.db.get_value(
            "Employee", self.employee, "date_of_joining")
        if getdate(date_of_joining) > getdate(self.start_date):
            allocation_records_based_on_to_date = get_leave_allocation_records(
                self.employee, date_of_joining)
        else:
            allocation_records_based_on_to_date = get_leave_allocation_records(
                self.employee, self.start_date)

        # frappe.msgprint(str(allocation_records_based_on_to_date))
        # allocation_records_based_on_from_date = get_leave_allocation_records(self.end_date)
        leave_period = get_leave_period(self.start_date, self.end_date,
                                        frappe.db.get_value("Employee", self.employee, "company"))

        if leave_period:
            leave_period = leave_period[0]
            leave_types = frappe.db.get_all(
                "Leave Type", filters={"is_lwp": 0, "is_carry_forward": 1}, fields=["name"])

            total_period_leave_balance = self.get_total_leave_balance()
            # frappe.msgprint(str(total_period_leave_balance))
            for leave_type in leave_types:
                # leaves taken
                leaves_taken += get_approved_leaves_for_period(
                    self.employee, leave_type.name, leave_period.from_date, leave_period.to_date)

                # opening balance
                # opening += get_leave_balance_on(self.employee, leave_type.name, leave_period.from_date,allocation_records_based_on_to_date.get(self.employee, frappe._dict()))
                opening += allocation_records_based_on_to_date[leave_type['name']
                                                               ]["total_leaves_allocated"]
                # closing balance
                closing += get_leave_balance_on(self.employee, leave_type.name, leave_period.to_date,
                                                allocation_records_based_on_to_date.get(self.employee, frappe._dict()))
            balance_adjustment_days = get_Leave_balance_adjustment_days(
                self.employee, self.relieving_date) or 0

            self.leave_balance = flt(opening)
            # + flt(balance_adjustment_days)

            self.current_leave_balance = (
                flt(opening) - flt(leaves_taken)) + flt(balance_adjustment_days)

    def check_futural_credit(self):
        leave_type = "Annual Leave"
        consider_all_leaves_in_the_allocation_period = True

        allocation_records = get_leave_allocation_records(
            self.employee, getdate(), leave_type)
        allocation = allocation_records.get(leave_type, frappe._dict())

        end_date = allocation.to_date if cint(
            consider_all_leaves_in_the_allocation_period) else getdate()
        cf_expiry = get_allocation_expiry_for_cf_leaves(
            self.employee, leave_type, self.relieving_date, getdate())

        leaves_taken = get_leaves_for_period(
            self.employee, leave_type, allocation.from_date, end_date) or 0

        remaining_leaves = get_remaining_leaves(
            allocation, leaves_taken, getdate(), cf_expiry)

        leave_balance_to_the_to_date = remaining_leaves

        balance_adjustment_days = get_Leave_balance_adjustment_days(
            self.employee, self.relieving_date) or 0

        from hris.utils.utils import calculate_annual_leave_balance
        # if getdate(self.from_date) > getdate():

        # self.leave_balance = allocation["total_leaves_allocated"]

        self.leave_balance += flt(balance_adjustment_days)

        leave_balance_to_the_to_date = calculate_annual_leave_balance(
            self.employee, self.relieving_date) or 0
        leave_balance_to_the_to_date += leaves_taken

        self.leave_balance_to_the_to_date = leave_balance_to_the_to_date

        self.current_leave_balance = leave_balance_to_the_to_date + flt(  # remaining_leaves['leave_balance']
            balance_adjustment_days)

        # self.current_leave_balance = leave_balance_to_the_to_date
        # + flt(balance_adjustment_days)

        # leave_balance_to_the_to_date += flt(balance_adjustment_days)

        return leave_balance_to_the_to_date

    def get_total_leave_balance(self):
        leave_balance_per_for_encash = 0
        if 5 > self.years > 0:
            leave_balance_per_for_encash = 21
            leave_balance_per_for_encash = 21 * \
                (cint(self.adj_years) + flt(self.adj_months / 12) +
                 ((flt(self.adj_days) / 30) / 12))
        elif self.years >= 5:
            leave_balance_per_for_encash = 30 * (
                cint(self.adj_years) + flt(self.adj_months / 12) + ((flt(self.adj_days) / 30) / 12))

        return leave_balance_per_for_encash

    def calculate_idemnity_amount(self):
        month_days = get_month_days(self.relieving_date)
        idemnity_amount, days_months_value = 0.0, 0.0
        conditions = frappe.get_list("Payment Detail",
                                     filters={
                                         "parent": self.reason_for_leaving, "parentfield": "payment_detail"},
                                     fields=["years_from", "years_to", "pay_percentage"], order_by="idx desc")
        total_years = self.years
        date_of_joining = frappe.db.get_value(
            "Employee", self.employee, "date_of_joining")
        service_days = date_diff(self.relieving_date, add_days(
            date_of_joining, self.deduct_days_from_service_period)) + 1
        totla_idemnity_amount = 0
        # frappe.msgprint("idemnity_amount=============>" + str(self.include_in_indemnity_amount))
        if 5 > self.years >= 0:
            # idemnity_amount = flt(flt(self.include_in_indemnity_amount) / 730) * cint(service_days)
            idemnity_amount = flt(
                self.include_in_indemnity_amount) * cint(self.years)
            idemnity_amount += (flt(self.include_in_indemnity_amount) /
                                12) * cint(self.months)
            idemnity_amount += ((flt(self.include_in_indemnity_amount) /
                                 12) / 30) * cint(self.days)
        # frappe.msgprint("idemnity_amount=============>"+str(self.include_in_indemnity_amount))
        elif self.years >= 5:
            idemnity_amount = (
                flt(self.include_in_indemnity_amount) * cint(self.years)) / 2

            idemnity_amount += (flt(self.include_in_indemnity_amount) /
                                12) * cint(self.months)
            idemnity_amount += ((flt(self.include_in_indemnity_amount) /
                                12) / 30) * cint(self.days)

            # idemnity_amount = flt(
            #     flt(self.include_in_indemnity_amount) / 24) * 60
            # idemnity_amount += ((flt(self.include_in_indemnity_amount) / 12)) * (
            #     ((cint(self.years) - 5) * 12) + cint(self.months) + (flt(self.days) / 30))

        elif self.months > 0:
            idemnity_amount = (flt(flt(self.include_in_indemnity_amount) / 24)
                               * (cint(self.months) + (flt(self.days) / 30)))

        for item in conditions:
            if flt(item["years_to"]) > total_years >= flt(item["years_from"]):
                totla_idemnity_amount += flt(idemnity_amount) * \
                    (flt(item["pay_percentage"]) / 100)

        return rounded(totla_idemnity_amount, 2)

    def get_component_totals(self, component_type, statical_component=False):
        total = 0.0
        for d in self.get(component_type):
            # if not d.do_not_include_in_total:
            if statical_component:
                if d.statistical_component == 0:
                    d.amount = flt(d.amount, d.precision("amount"))
                    total += d.amount
            else:
                d.amount = flt(d.amount, d.precision("amount"))
                total += d.amount
        return total

    def get_employee_data_for_eval(self):
        '''Returns data for evaluating formula'''
        data = frappe._dict()
        salary_structure = frappe.get_list("Salary Structure Assignment", {"employee": self.employee, "docstatus": 1},
                                           "salary_structure", order_by="from_date desc", limit_start=0,
                                           limit_page_length=1)
        if salary_structure:
            salary_structure = salary_structure[0]["salary_structure"]
            self._salary_structure_doc = frappe.get_doc(
                'Salary Structure', salary_structure)
            sal_assig = frappe.db.get_value("Salary Structure Assignment", {
                "employee": self.employee, "docstatus": 1, "salary_structure": salary_structure},
                order_by="from_date desc")
            assign_data = frappe.get_doc(
                "Salary Structure Assignment", sal_assig).as_dict()
            data.update(assign_data)
        else:
            frappe.throw(_("Please make New Salary Structure Assignment"))

        data.update(frappe.get_doc("Employee", self.employee).as_dict())
        data.update(self.as_dict())

        # set values for components
        salary_components = frappe.get_all(
            "Salary Component", fields=["salary_component_abbr"])
        for sc in salary_components:
            data.setdefault(sc.salary_component_abbr, 0)

        return data

    def eval_condition_and_formula(self, d, data):
        try:
            condition = d.condition.strip() if d.condition else None
            if condition:
                if not frappe.safe_eval(condition, self.whitelisted_globals, data):
                    return None
            amount = d.amount
            if d.amount_based_on_formula:
                formula = d.formula.strip() if d.formula else None
                if formula:
                    amount = flt(frappe.safe_eval(
                        formula, self.whitelisted_globals, data), d.precision("amount"))
            if amount:
                data[d.abbr] = amount

            return amount

        except NameError as err:
            frappe.throw(_("Name error: {0}".format(err)))
        except SyntaxError as err:
            frappe.throw(
                _("Syntax error in formula or condition: {0}".format(err)))
        except Exception as e:
            frappe.throw(_("Error in formula or condition: {0}".format(e)))
            raise

    def update_component_row(self, struct_row, amount, key, overwrite=1, **kwargs):
        component_row = None
        adsal_from_traffic_violations = kwargs.get("adsal", None) if kwargs.get(
            "adsal", None) and kwargs.get("adsal", None).get("from_traffic_violation") else ''
        for d in self.get(key):
            if d.salary_component == struct_row.salary_component:
                '''check if deduction trrafic according to Traffic Violations from additional salary'''
                if adsal_from_traffic_violations and d.get("from_traffic_violation", "") == adsal_from_traffic_violations.get("name", None):
                    component_row = None
                    break
                elif not adsal_from_traffic_violations:
                    component_row = d

        if not component_row:
            if amount:
                self.append(key, {
                    'amount': amount,
                    'default_amount': amount if not struct_row.get("is_additional_component") else 0,
                    'depends_on_payment_days': struct_row.depends_on_payment_days,
                    'salary_component': struct_row.salary_component,
                    'abbr': struct_row.abbr,
                    'do_not_include_in_total': struct_row.do_not_include_in_total,
                    'is_tax_applicable': struct_row.is_tax_applicable,
                    'is_flexible_benefit': struct_row.is_flexible_benefit,
                    'statistical_component': struct_row.statistical_component,
                    'variable_based_on_taxable_salary': struct_row.variable_based_on_taxable_salary,
                    'deduct_full_tax_on_selected_payroll_date': struct_row.deduct_full_tax_on_selected_payroll_date,
                    'additional_amount': amount if struct_row.get("is_additional_component") else 0,
                    **({'from_traffic_violation': adsal_from_traffic_violations.get("name", "")} if adsal_from_traffic_violations else {})
                })
        else:
            if struct_row.get("is_additional_component"):
                if overwrite:
                    component_row.additional_amount = amount - \
                        component_row.get("default_amount", 0)
                else:
                    component_row.additional_amount = amount

                if not overwrite and component_row.default_amount:
                    amount += component_row.default_amount
            else:
                if key == "deductions":
                    '''to sum all future deduction issue_109'''
                    amount += component_row.default_amount
                else:
                    amount += component_row.default_amount

                    component_row.default_amount = amount
                    component_row.statistical_component = struct_row.statistical_component

            component_row.amount = amount
            component_row.deduct_full_tax_on_selected_payroll_date = struct_row.deduct_full_tax_on_selected_payroll_date

    def set_loan_repayment(self):
        self.set('loans', [])
        self.total_loan_repayment = 0
        self.total_interest_amount = 0
        self.total_principal_amount = 0
        self.balance_loan_amount = 0
        for loan in self.get_loan_details():
            self.append('loans', {
                'loan': loan.name,
                'total_payment': loan.total_payment,
                'interest_amount': loan.interest_amount,
                'principal_amount': loan.principal_amount,
                'loan_account': loan.loan_account,
                'interest_income_account': loan.interest_income_account
            })

            self.balance_loan_amount = flt(loan.balance_loan_amount)
            self.total_loan_repayment += flt(loan.total_payment) - flt(
                loan.balance_loan_amount)  # + loan.principal_amount
            self.total_interest_amount += loan.interest_amount
            self.total_principal_amount += loan.total_payment

    def get_loan_details(self):
        return frappe.db.sql("""select 
					rps.principal_amount, 
					rps.interest_amount, 
					l.name,
					l.total_payment, 
					l.loan_account, 
					l.interest_income_account,
					rps.balance_loan_amount
			from
				`tabRepayment Schedule` as rps, `tabLoan` as l
			where
				l.name = rps.parent and rps.payment_date between %s and %s and
				l.repay_from_salary = 1 and l.docstatus = 1 and l.applicant = %s
				and rps.parenttype ='Loan' """,
                             (self.start_date, self.end_date, self.employee), as_dict=True, debug=False) or []

    @frappe.whitelist()
    def get_employee_contract(self, employee):
        contract = frappe.db.sql("""
			select `name` contract
				from `tabEmployee contract`
					where employee = %s
							and docstatus = 1
							order by contratc_end_date desc 
							limit 1
		""", (employee), as_dict=True)
        if contract:
            return contract[0]["contract"]

    def is_rounding_total_disabled(self):
        return cint(frappe.db.get_single_value("Payroll Settings", "disable_rounded_total"))

    def get_data_for_eval(self):
        """Returns data for evaluating formula"""
        data = frappe._dict()
        employee = frappe.get_doc("Employee", self.employee).as_dict()

        start_date = getdate(get_first_day(self.relieving_date))
        date_to_validate = (
            employee.date_of_joining if employee.date_of_joining > start_date else start_date
        )
        self.month_to_date = 0
        self.rounded_total = 0
        self.year_to_date = 0
        self.base_rounded_total = 0
        self.currency = erpnext.get_default_currency()
        self.company = employee.company
        salary_structure_assignment = frappe.get_value(
            "Salary Structure Assignment",
            {
                "employee": self.employee,
                # "salary_structure": self.salary_structure,
                "from_date": ("<=", date_to_validate),
                "docstatus": 1,
            },
            "*",
            order_by="from_date desc",
            as_dict=True,
        )
        print("salary_structure_assignment =======" +
              str(salary_structure_assignment)+"====="+str(self.employee))
        # print("salary_structure_assignment================================"+str(self.salary_structure))
        if not salary_structure_assignment:
            msg = _(
                "Please assign a Salary Structure for Employee {0} " "applicable from or before {1} first"
            ).format(
                frappe.bold(self.employee),
                frappe.bold(formatdate(date_to_validate)),
            )
            frappe.throw(msg)

        data["start_date"] = start_date
        data["end_date"] = get_last_day(start_date)
        data.update(salary_structure_assignment)
        data.update(employee)
        # data.update(self.as_dict())

        # set values for components
        salary_components = frappe.get_all(
            "Salary Component", fields=["salary_component_abbr"])
        for sc in salary_components:
            data.setdefault(sc.salary_component_abbr, 0)

        # shallow copy of data to store default amounts (without payment days) for tax calculation
        default_data = data.copy()

        for key in ("earnings", "deductions"):
            for d in self.get(key):
                default_data[d.abbr] = d.default_amount or 0
                data[d.abbr] = d.amount or 0

        data["B"] = salary_structure_assignment['base']
        return data, default_data

    def calculate_lwp_ppl_and_absent_days_based_on_attendance(self, holidays, startdate, enddate):
        lwp = 0
        absent = 0

        daily_wages_fraction_for_half_day = (
            flt(frappe.db.get_value("Payroll Settings", None,
                "daily_wages_fraction_for_half_day")) or 0.5
        )

        leave_types = frappe.get_all(
            "Leave Type",
            or_filters=[["is_ppl", "=", 1], ["is_lwp", "=", 1]],
            fields=["name", "is_lwp", "is_ppl",
                    "fraction_of_daily_salary_per_leave", "include_holiday"],
        )

        leave_type_map = {}
        for leave_type in leave_types:
            leave_type_map[leave_type.name] = leave_type

        attendances = frappe.db.sql(
            """
            SELECT attendance_date, status, leave_type
            FROM `tabAttendance`
            WHERE
                status in ("Absent", "Half Day", "On leave")
                AND employee = %s
                AND docstatus = 1
                AND attendance_date between %s and %s
        """,
            values=(self.employee, startdate, enddate),
            as_dict=1,
            debug=False)

        for d in attendances:
            if (
                d.status in ("Half Day", "On Leave")
                and d.leave_type
                and d.leave_type not in leave_type_map.keys()
            ):
                continue

            if formatdate(d.attendance_date, "yyyy-mm-dd") in holidays:
                if d.status == "Absent" or (
                    d.leave_type
                    and d.leave_type in leave_type_map.keys()
                    and not leave_type_map[d.leave_type]["include_holiday"]
                ):
                    continue

            if d.leave_type:
                fraction_of_daily_salary_per_leave = leave_type_map[d.leave_type][
                    "fraction_of_daily_salary_per_leave"
                ]

            if d.status == "Half Day":
                equivalent_lwp = 1 - daily_wages_fraction_for_half_day

                if d.leave_type in leave_type_map.keys() and leave_type_map[d.leave_type]["is_ppl"]:
                    equivalent_lwp *= (
                        fraction_of_daily_salary_per_leave if fraction_of_daily_salary_per_leave else 1
                    )
                lwp += equivalent_lwp
            elif d.status == "On Leave" and d.leave_type and d.leave_type in leave_type_map.keys():
                equivalent_lwp = 1
                if leave_type_map[d.leave_type]["is_ppl"]:
                    equivalent_lwp *= (
                        fraction_of_daily_salary_per_leave if fraction_of_daily_salary_per_leave else 1
                    )
                lwp += equivalent_lwp
            elif d.status == "Absent":
                absent += 1
        return lwp, absent

    def calculate_penalty(doc):
        from collections import Counter
        from hris.utils.utils import calc_penalty_amount
        penalty_list, month_penalty_list = [], []
        mounth_penalty, penalty_amount, calc_using_pre, amount = 0, 0, False, 0
        data = doc.get_data_for_eval()
        data = data[0]
        if "penalties_data" in data:
            CountItems = 0

            penalties_data = sorted(
                data['penalties_data'], key=lambda d: d['apply_date'])

            hrms_settings = frappe.db.get_singles_dict("HRMS Settings")

            start_date = add_months(getdate(data['start_date']), -1)
            start_date = getdate(str(getdate(start_date).year)+"-"+str(
                getdate(start_date).month)+"-" + str(hrms_settings.deductions_start_day))
            # end_date = add_days(getdate(data['start_date']), cint(hrms_settings.deductions_end_day)-1)
            end_date = get_last_day(doc.relieving_date)

            penalities_amounts = {}
            for penalty in penalties_data:
                if data['end_date']:
                    if not data['start_date']:
                        data['start_date'] = data['end_date'].replace(
                            data['end_date'].split('-')[-1], '1')

                    rule_start_date = frappe.db.get_value("Penalties Settings", {"penalty_type": penalty.penalty_type},
                                                          "from_date")
                    rule_end_date = frappe.db.get_value("Penalties Settings", {"penalty_type": penalty.penalty_type},
                                                        "to_date")
                    if getdate(rule_start_date) <= penalty.apply_date <= getdate(rule_end_date):
                        if penalty.apply_date < getdate(data['end_date']):
                            penalty_list.append(
                                {"penaltytype": penalty.penalty_type, "apply_date": penalty.apply_date})

                        CountItems = Counter(d['penaltytype']
                                             for d in penalty_list)
                        penalty_amount = calc_penalty_amount(
                            doc, penalty["penalty_type"], penalty["apply_date"], CountItems, data)

                        if getdate(start_date) <= penalty.apply_date <= getdate(end_date):
                            if penalty.penalty_type not in penalities_amounts:
                                penalities_amounts[penalty.penalty_type] = penalty_amount
                            else:
                                penalities_amounts[penalty.penalty_type] += penalty_amount

            for key, val in penalities_amounts.items():
                component = frappe.db.get_value(
                    "Salary Component", {"name": key, "is_penalties_component": 1}, "name")
                if not component:
                    frappe.throw(_("Please Check Penalty Component.."))
                doc.update_component_row(
                    get_salary_component_data(component),
                    val,
                    "deductions"
                )


@frappe.whitelist()
def get_Leave_balance_adjustment_days(employee, last_working_date, leave_type=None):
    try:
        total_adjustment_balance_days = 0
        if leave_type:
            leave_adjustment_balance_days = frappe.db.get_all("Leave Balance Adjustment",
                                                              {
                                                                  "docstatus": 1,
                                                                  "employee_code": employee,
                                                                  "leave_type": leave_type,
                                                                  "adjustment_transaction_date": ['<=', last_working_date],
                                                              },
                                                              "leave_adjustment_days"
                                                              )
        else:
            leave_adjustment_balance_days = frappe.db.get_all("Leave Balance Adjustment",
                                                              {
                                                                  "docstatus": 1,
                                                                  "employee_code": employee,
                                                                  "adjustment_transaction_date": ['<=', last_working_date],
                                                              },
                                                              "leave_adjustment_days"
                                                              )
        if leave_adjustment_balance_days:
            for labd in leave_adjustment_balance_days:
                total_adjustment_balance_days += labd.leave_adjustment_days

        return total_adjustment_balance_days
    except Exception as ex:
        frappe.log_error(
            "get_Leave_balance_adjustment_days:EndofService", f"{traceback.format_exc()}")
        return False



def test_rounding(itemised_tax, precision=2):
    for taxes in itemised_tax:
        for row in taxes.values():
            if isinstance(row, dict) and isinstance(row["tax_amount"], float):
                value = row["tax_amount"]
                rounded_value = flt(value, precision)
            print(f"Rounding {value} to {rounded_value}")