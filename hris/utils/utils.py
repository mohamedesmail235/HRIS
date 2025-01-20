# -*- coding: utf-8 -*-
# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals, print_function
import base64
import hmac
from hashlib import sha256
import time
import uuid
import jwt
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from erpnext.setup.doctype.holiday_list.holiday_list import is_holiday
import frappe
import erpnext
from frappe import _
import frappe.sessions
from frappe.utils import getdate
import calendar
from collections import namedtuple
import json
from collections import Counter
import math
from typing import Dict, Optional, Tuple

from frappe.utils import getdate, nowdate, cint, add_days, today
from frappe.model.naming import make_autoname
from calendar import monthrange
from datetime import datetime, timedelta
from dateutil import relativedelta
from frappe.utils.data import get_first_day, date_diff, flt, get_last_day, add_months
from frappe.utils import getdate, nowdate, cint, add_days
from hrms.payroll.doctype.salary_slip.salary_slip import get_salary_component_data
from frappe.utils import (
    add_days,
    cint,
    cstr,
    date_diff,
    flt,
    formatdate,
    get_first_day,
    getdate,
    money_in_words,
    rounded,
)
from hrms.payroll.doctype.additional_salary.additional_salary import get_additional_salaries
from erpnext.accounts.utils import get_currency_precision
from hrms.hr.doctype.leave_application.leave_application import (
    get_leave_allocation_records,
    get_leave_balance_on,
    get_leave_details
)
import requests


def getAbsenceData(url, userName, password, P_PERSON_ID, P_ABSENCE_TYPE_ID):
    # P_DURATION = date_diff(P_END_DATE, P_START_DATE) + 1
    employeeLeaves = frappe.db.sql("""select * from `tabLeave Application`
    				WHERE p_person_id=%s and p_absence_type_id=%s
    				""", (P_PERSON_ID, P_ABSENCE_TYPE_ID), as_dict=1)
    for leave in employeeLeaves:
        from_date = leave['from_date']
        to_date = leave['to_date']
        duration = leave['total_leave_days']
        jsonData = """
            {
                "CREATE_ABSENCE_MANGEMENT_Input": {
                "@xmlns": "http://xmlns.oracle.com/apps/per/rest/ERPNextSelfService/create_absence_mangement/",
                "RESTHeader": {"xmlns": "http://xmlns.oracle.com/apps/fnd/rest/ERPNextSelfService/header",
                "Responsibility":"US_HRMS_MANAGER",
                "RespApplication":"PER",
                "SecurityGroup":"STANDARD",
                "NLSLanguage":"AMERICAN",
                "Org_Id" :"161"},
                 "InputParameters" : {
                 "P_PERSON_ID" : "+P_PERSON_ID+"",
                 "P_ABSENCE_TYPE_ID" : "+P_ABSENCE_TYPE_ID+"",
                 "P_START_DATE" : "+to_date+",
                 "P_END_DATE" : "+from_date+",
                 "P_DURATION" : "+duration+"
                    }
                }
            }"""
        headers = {'Content-Type': 'application/json'}
        # response = requests.post(url=url, data=jsonData, headers=headers)
        # if(response.status_code==200):
        # print('ok 200 status')
        f = open('absence_management_data.json')
        data = json.load(f)
        if data['OutputParameters']['P_OUTPUT']:
            frappe.msgprint(data['OutputParameters']['P_OUTPUT'])

            f.close()


@frappe.whitelist()
def validate_leaves(employee, leave_type):
    if leave_type == "Hajj Leave":
        service_details = get_years_of_service(employee)
        if service_details:
            print("service_details======================" + str(service_details))
            if cint(service_details["years"]) >= 2:
                if frappe.db.exists("Leave Application", {"leave_type": "Hajj Leave", "docstatus": 1}):
                    msg = _("This Employee Took The Leave Before")
                    validated = False
                    return msg
            else:
                msg = _("This Employee Does not pass Two Years in Service")
                validated = False
                return msg
    elif leave_type == "Birth Leave":
        if frappe.db.get_value("Employee", employee, "gender") != "Male":
            validated = False
            msg = _("This Leave is For Men Only")
            return msg
    elif leave_type == "Maternity Leave":
        if frappe.db.get_value("Employee", employee, "gender") != "Female":
            validated = False
            msg = _("This Leave is For Female Only")
            return msg


def get_years_of_service(employee):
    date_of_joining = frappe.db.get_value(
        "Employee", employee, "date_of_joining")
    if (not date_of_joining):
        frappe.throw("Please set date of joining")
    deducted_days = frappe.db.get_value("Deduct Days from Service Period",
                                        {"name": employee, "type": "Service Period"}, "number_of_days") or 0

    deduct_days_from_service_period = deducted_days
    service_details = get_dates_diff(
        add_days(date_of_joining, deducted_days), add_days(nowdate(), 1))

    return service_details


def Overlab_Dates(R1_Start_Date, R1_End_date, R2_Start_Date, R2_End_date):
    a, b, c, d = \
        datetime.strptime(R1_Start_Date, '%Y-%m-%d'), \
        datetime.strptime(R1_End_date, '%Y-%m-%d'), \
        datetime.strptime(R2_Start_Date, '%Y-%m-%d'), \
        datetime.strptime(R2_End_date, '%Y-%m-%d')

    Range = namedtuple('Range', ['start', 'end'])

    r1 = Range(start=datetime(a.year, a.month, a.day),
               end=datetime(b.year, b.month, b.day))
    r2 = Range(start=datetime(c.year, c.month, c.day),
               end=datetime(d.year, d.month, d.day))

    latest_start = max(r1.start, r2.start)
    earliest_end = min(r1.end, r2.end)
    delta = (earliest_end - latest_start).days + 1
    overlap = max(0, delta)

    return overlap


def get_month_days(start_date):
    option = frappe.db.get_single_value("HRMS Settings", "day_calculation")
    MonthDays = Switcher(option, start_date)

    return MonthDays


def get_month_full_name(month, lang=None):
    if lang is None:
        # Default to English or whatever default you prefer
        lang = "en"
    month_name = ""
    import datetime
    if (isinstance(month, datetime.date)) or (isinstance(month, str) and month.find('-') != -1):
        month = int(str(month).split('-')[1])
    else:
        if month:
            month = int(month)
    months = {
        1: _("January", lang=lang), 2: _("February", lang=lang), 3: _("March", lang=lang), 4: _("April", lang=lang),
        5: _("May", lang=lang), 6: _("June", lang=lang),
        7: _("July", lang=lang), 8: _("August", lang=lang), 9: _("September", lang=lang), 10: _("October", lang=lang),
        11: _("November", lang=lang), 12: _("December", lang=lang)
    }
    month_name = months.get(month, "Invalid Month")
    return month_name


def get_month_number(month):
    import calendar
    month_dict = (dict((v, k) for k, v in enumerate(calendar.month_name)))

    return month_dict[month]


def Switcher(option, start_date):
    switcher = calendar.monthrange(
        int(getdate(start_date).year), int(getdate(start_date).month))[1]
    if option == "360":
        switcher = float(360 / 12)
    elif option == "365":
        switcher = float(365 / 12)

    return switcher


@frappe.whitelist()
def get_user_group():
    ret_Dict = frappe.db.sql('''
                    select Module_Group,Icon
                    from (
                        select  distinct  (select  `name`  from `tabModule Def` where `name` = DT.module and `group` is not NULL
                            and restrict_to_domain = 'Services') Module_Group,
                            (select  idx from `tabModule Def` where `name` = DT.module) Idx,
                            (select  icon from `tabModule Def` where `name` = DT.module) Icon
                            from `tabHas Role` HR
                                inner join tabDocPerm DP
                                on HR.role = DP.role
                                inner join tabDocType DT
                                on DP.parent = DT.`name`
                                and HR.parent = %s
                                order by Idx
                                )T
                                where  T.Module_Group is not NULL

					''', (frappe.session.user), as_dict=True)
    # print("=====================" + str(ret_Dict))
    if ret_Dict != []:
        from frappe.desk.moduleview import get
        for item in ret_Dict:
            item.update(get(item["Module_Group"]))
        # item.update(get(item["Module_Group"]))
        # try:
        #     ret_Dict[item].update(get(ret_Dict[item]["Module_Group"]))
        # except:
        #     pass

    return ret_Dict


@frappe.whitelist()
def next_previous_item(doctype, element_name, filters=[], page_lenght=20, start=0, order_by=""):
    message_status = False
    if (doctype == '' or doctype == None or element_name == '' or element_name == None):
        return message_status
    filter_conditions = ""
    # print("====="+str(filters)+"====")
    if filters != "" and filters != "[]" and filters != []:
        filters = str(filters).replace(
            '[', '').replace(']', '').replace('"', '').split(',')

        filters = list(divide_chunks(filters, 4))

        for item in range(0, len(filters)):
            if filters[item][3] != 'null':
                filter_conditions += " AND " + \
                    filters[item][1] + " " + filters[item][2] + \
                    " '" + filters[item][3] + "'"

    ret_dict = {}
    teble_name = "`tab" + doctype + "`"
    try:
        tem_dict = frappe.db.sql(
            ""
            "    select (select `name` from {0} where idx > T.idx order by `name`  limit 1) next_item , \n"
            "    (select `name` from {1} where idx < T.idx order by `name` desc  limit 1) previous_item \n"
            "        from {2} T \n"
            "               where `name` = {3} \n"
            "                   {4}   \n"
            "           {5}  \n"
            " limit {6},{7}   \n".format(
                teble_name, teble_name, teble_name,
                "'" + element_name + "'",
                filter_conditions,
                ("order by " + order_by.split('.')
                 [1] if order_by != "" else ""),
                start,
                page_lenght
            ), as_dict=True, debug=False
        )
        if tem_dict != []:
            ret_dict["message_status"] = True
            ret_dict.update(tem_dict[0])
            return ret_dict
    except:
        return message_status


def divide_chunks(l, n):
    # looping till length l
    for i in range(0, len(l), n):
        yield l[i:i + n]


@frappe.whitelist()
def get_widgets(module, filter=[]):
    # module = "People"
    widgets = []
    module_widgets = frappe.db.sql('''
            select title , widget_name ,`query`,chart_type, hide_title ,widget_column_size , widget_order , background_color ,text_color , hide_filter
            from tabWidget
            where  module =%s 
            order by widget_order 
	''', format(module), as_dict=True)

    if module_widgets:
        i = 0
        for widget in module_widgets:
            json_result = {}
            widget_filter = []
            widget_query = frappe.get_value(
                "Widget Query", {"name": widget["query"]}, ['query'], as_dict=True)
            if widget["hide_filter"] == 0:
                widget_filter = frappe.get_value("Widget Filter", {"parent": widget["query"]},
                                                 ['label', 'type', 'value', 'ref_field'], as_dict=True)
                filter_result = handle_widget_filter(widget_filter)
                json_result["filters"] = filter_result

            result = frappe.db.sql(widget_query["query"], as_dict=True)
            # if widget["chart_type"]=="count-circle":
            json_result["result"] = result
            json_result.update(widget)
            widgets.append(json_result)
        # if widget["chart_type"]=="charts-column-wide":

    # frappe.msgprint(str(widgets))
    return widgets


def handle_widget_filter(filters):
    result = []
    if filters:
        filters["label"] = [filters["label"]]
        if filters["type"] == "Select":
            result = frappe.db.sql(filters["value"], as_dict=True)
            if result:
                filters["value"] = [d for d in result]
        if filters["type"] == "range_date":
            pass
        if filters["type"] == "date":
            pass

        result = [filters]

    # frappe.msgprint(str(result))
    return result


def monthdelta(d1, d2):
    d1 = getdate(d1)
    d2 = getdate(d2)
    delta = 0
    while True:
        mdays = monthrange(d1.year, d1.month)[1]
        d1 += timedelta(days=mdays)
        if d1 <= d2:
            delta += 1
        else:
            break
    return delta


def get_dates_diff(a, b):
    a = getdate(a)
    b = getdate(b)
    diff_dict = {}
    a = datetime(a.year, a.month, a.day)
    b = datetime(b.year, b.month, b.day)
    delta = relativedelta.relativedelta(b, a)
    diff_dict["years"] = delta.years
    diff_dict["months"] = delta.months
    diff_dict["days"] = delta.days

    return diff_dict


def Calculate_component_percentage(disbursement_period, posting_date, joining_date, relieving_date=None, double_NO=0.0):
    percentage = 0
    if relieving_date and getdate(relieving_date).month == getdate(posting_date).month:
        months = {"Quarterly": 3, "Biannual": 6, "Annual": 12}

        days = get_month_days(
            posting_date) - get_dates_diff(getdate(relieving_date), getdate(posting_date))["days"]
        if disbursement_period in ("Quarterly", "Biannual", "Annual"):
            if getdate(posting_date).month > months[disbursement_period]:
                percentage = ((getdate(posting_date).month - months[disbursement_period]) / months[
                    disbursement_period]) + (
                    (days / get_month_days(getdate(posting_date))) / months[disbursement_period])
            else:
                percentage = getdate(posting_date).month / months[disbursement_period] + (
                    (days / get_month_days(getdate(posting_date))) / months[disbursement_period])
            frappe
            if double_NO > 0:
                double_NO = float(percentage * double_NO)
            else:
                double_NO = float(percentage)
    else:
        double_NO = {"Quarterly": 3, "Biannual": 6,
                     "Annual": 12}[disbursement_period]
        dates_diff_details = get_dates_diff(
            getdate(joining_date), getdate(posting_date))

        if getdate(posting_date).year == getdate(joining_date).year and int(dates_diff_details["months"]) < int(
                double_NO):
            double_NO = get_diff_days(double_NO, joining_date)

    # frappe.msgprint(str(disbursement_period)+"====="+str(double_NO) + "======================" +str(percentage))

    return double_NO


def get_diff_days(double_NO, target_date):
    Calculation_option = frappe.db.get_single_value(
        "HRMS Settings", "day_calculation")
    days_diff = date_diff(get_last_day(target_date), target_date) + 1

    if Calculation_option == "Calendar":
        days_diff = days_diff / get_month_days(target_date)
    elif Calculation_option == "360":
        days_diff = (days_diff / 360) * 12
    elif Calculation_option == "365":
        days_diff = (days_diff / 365) * 12

    double_NO = (double_NO - 1) + days_diff

    return double_NO


def round_to_nearest_half(num):
    syllable = flt("0." + str(num).split('.')[1])

    if syllable > 0.5:
        syllable = syllable - 0.5
    num = num - syllable

    return num


def get_leaves_without_pay(from_date, to_date, employee):
    total_lwp_days = 0.0
    total_lwp_days = frappe.db.sql("""
            select sum(total_leave_days) total_lwp_days
                    from(
                        select leave_type ,from_date,to_date,
                            case
                                    when from_date BETWEEN %s and %s and to_date BETWEEN %s and %s then total_leave_days
                                    when from_date < %s and to_date > %s then DATEDIFF(to_date,%s)+1
                                    when from_date > %s and to_date > %s  then DATEDIFF(%s ,from_date)
                                    else total_leave_days
                                end 	total_leave_days
                            from `tabLeave Application`	L
                                where employee=%s
                                    and (select is_lwp from `tabLeave Type` where `name` = L.leave_type ) = 1
                                    and (
                                        from_date BETWEEN %s and %s
                                or to_date BETWEEN %s and %s
                                )
            )T
    """, (
        from_date,
        to_date,
        from_date,
        to_date,
        from_date,
        from_date,
        from_date,
        from_date,
        to_date,
        to_date,
        employee,
        from_date,
        to_date,
        from_date,
        to_date
    ), as_dict=1, debug=False)

    if total_lwp_days:
        total_lwp_days = flt(total_lwp_days[0]["total_lwp_days"])
    return total_lwp_days


def get_leave_allocation(encashment_date, leave_type, employee):
    leave_allocation = frappe.db.sql("""select name from `tabLeave Allocation` where '{0}'
		between from_date and to_date and docstatus=1 and leave_type='{1}'
		and employee= '{2}'""".format(encashment_date or getdate(nowdate()), leave_type, employee))

    return leave_allocation[0][0] if leave_allocation else None


def get_encashment_leaves(date, leave_type, employee):
    encashment_leaves = frappe.db.sql("""select total_leaves_encashed
        from `tabLeave Allocation` where '{0}'
		    between from_date and to_date and docstatus=1 and leave_type='{1}'
		    and employee= '{2}'""".format(date or getdate(nowdate()), leave_type, employee))

    return encashment_leaves[0][0] if encashment_leaves else None


def get_time_diffrence(time_from, time_to):
    from datetime import datetime
    FMT = '%H:%M:%S'
    tdelta = datetime.strptime(time_to, FMT) - \
        datetime.strptime(time_from, FMT)
    return tdelta


@frappe.whitelist()
def Calculation_option(date):
    Calculation_day = 0
    Calculation_option = frappe.db.get_single_value(
        "HRMS Settings", "day_calculation")
    if Calculation_option == "Calendar":
        Calculation_day = cint(get_month_days(date))
    else:
        Calculation_day = cint(Calculation_option)

    return Calculation_day


def validate_compensation(doc, method=None):
    # frappe.msgprint("before_insert")
    pass


def calculate_overtime_amounts(doc, method=None):
    return
    over_time_amount = 0
    overtimeminutes = frappe.db.sql("""		
            select sum(overtime_minutes) overtime_minutes
                from `tabOvertime Request`
                    where employee='{employee}'
                        and docstatus=1
                        and overtime_date BETWEEN '{start_date}' and '{end_date}'
            """.format(employee=doc.employee, start_date=doc.start_date, end_date=doc.end_date), as_dict=True)
    if overtimeminutes:
        overtimeminutes = overtimeminutes[0]
        monthly_working_hours = frappe.db.get_single_value(
            'HRMS Settings', 'monthly_working_hours')
        if monthly_working_hours == 0:
            frappe.throw(
                _("Please Add Monthly Working Hours in HRMS Settings"))
        basic_salary, total_salary = 0, 0
        data = doc.get_data_for_eval()[0]
        _salary_structure_doc = frappe.get_doc(
            "Salary Structure", data["salary_structure"])
        for struct_row in _salary_structure_doc.get("earnings"):
            amount = doc.eval_condition_and_formula(struct_row, data)
            if struct_row.salary_component in ("Housing", "Transportation"):
                import math
                frac, whole = math.modf(amount)
                if frac >= 0.5:
                    whole += 1
                    amount = whole
                else:
                    amount = whole
                if struct_row.salary_component == "Transportation" and amount < 300:
                    amount = 300
                if struct_row.salary_component == "Housing" and amount < 750:
                    amount = 750

            if struct_row.salary_component == "Basic":
                basic_salary = amount

            # frappe.msgprint("amount=========="+str(amount))
            if amount and struct_row.statistical_component == 0:
                total_salary += amount

        start_date = getdate(doc.start_date)
        end_date = getdate(doc.end_date)

        additional_salaries = get_additional_salaries(
            doc.employee, start_date, end_date, "earnings"
        )
        print("additional_salaries========================" +
              str(additional_salaries))

        for additional_salary in additional_salaries:
            if additional_salary.component in ("Housing", "Phone Allowance", "Responsibility Allowance", "Nature of work Allowance", "Fuel Allowance", "Transportation"):
                total_salary += flt(additional_salary.amount)

        total_hourly_rate = flt(total_salary)/flt(monthly_working_hours)
        basic_hourly_rate = flt(basic_salary) / flt(monthly_working_hours)

        _100_of_total_hourly_rate = total_hourly_rate
        _50_of_basic_hourly_rate = basic_hourly_rate/2
        hour_rate = flt(_100_of_total_hourly_rate) + \
            flt(_50_of_basic_hourly_rate)
        over_time_amount = flt(hour_rate) * \
            (flt(overtimeminutes["overtime_minutes"])/60)

        doc.update_component_row(
            get_salary_component_data("Over Time Allowance"),
            over_time_amount,
            "earnings"
        )
        #
        # doc.gross_pay+=over_time_amount
        # doc.rounded_total += over_time_amount
        # doc.net_pay += over_time_amount

    return over_time_amount


def auto_name(doc, method=None):
    id = frappe.db.sql("""
		select cast(`name` as UNSIGNED) +1 id
			from tabEmployee
			order by `name` desc
			limit 1
		""", as_dict=True)
    if id:
        doc.name = id[0]["id"]


def create_advance_leave(doc, method=None):
    if doc.request_advance_leave == 1:
        process_leave_advance(doc)
    else:
        delete_leave_advance(doc)


def process_leave_advance(doc):
    create_leave_advance(doc)

    # if getdate(doc.from_date).month != getdate(doc.to_date).month:
    # 	start_date= doc.from_date
    # 	end_date = get_last_day(doc.from_date)
    # 	create_leave_advance(doc, start_date=start_date, end_date=end_date)
    #
    # 	# frappe.throw("start_date======"+str(start_date)+"==========end_date======"+str(end_date))
    # 	next_start_date = get_first_day(doc.to_date)
    # 	next_end_date = doc.to_date
    #
    # 	create_leave_advance(doc, start_date=next_start_date, end_date=next_end_date)
    # else:
    # 	create_leave_advance(doc)


def create_leave_advance(doc, start_date="", end_date=""):
    salary_structure = frappe.db.get_value("Salary Structure Assignment", {
                                           "employee": doc.employee, "docstatus": 1}, "salary_structure")
    if start_date and end_date:
        total_advance_leave_days = date_diff(end_date, start_date)+1
    else:
        total_advance_leave_days = date_diff(doc.to_date, doc.from_date)+1
    start_date_month = getdate(doc.from_date).month
    end_date_month = getdate(doc.to_date).month

    if get_first_day(doc.from_date) == doc.from_date and get_last_day(doc.to_date) == doc.to_date:
        total_advance_leave_days = (
            cint(end_date_month) - cint(start_date_month)) + 1
        total_advance_leave_days = cint(total_advance_leave_days) * 30
        # frappe.throw(str(start_date_month)+"===========>"+str(end_date_month)+"===========>"+str(total_advance_leave_days))

    leave_adv_doc = frappe.new_doc("Advance Leave")
    leave_adv_doc.employee = doc.employee
    leave_adv_doc.leave_application = doc.name
    leave_adv_doc.start_date = (start_date if start_date else doc.from_date)
    leave_adv_doc.end_date = (end_date if end_date else doc.to_date)
    leave_adv_doc.total_advance_leave_days = total_advance_leave_days
    leave_adv_doc.salary_structure = salary_structure
    leave_adv_doc.save()
    # leave_adv_doc.submit()
    frappe.db.commit()


def add_transportation_for_1_to_3_grades(doc, method=None):
    grade = frappe.db.get_value("Employee", doc.employee, "grade")
    if grade:
        if grade.startswith("1") or grade.startswith("2") or grade.startswith("2"):
            pass


def cancel_advance_leave(doc, method=None):
    delete_leave_advance(doc)


def delete_leave_advance(doc):
    leave_adv_name = frappe.db.get_value(
        "Advance Leave", {"employee": doc.employee, "leave_application": doc.name})
    if leave_adv_name:
        frappe.delete_doc_if_exists("Advance Leave", leave_adv_name)
    if doc.leave_type == "Unpaid Leave":
        calculate_annual_leave_balance(doc.employee)


def check_advance_leave(doc, method=None):
    advance_leave = frappe.db.sql("""
			select 	`name` ,MONTH(start_date) start_date_month, MONTH(end_date) end_date_month
					from `tabAdvance Leave`
							where (MONTH(start_date) = '{month}' or MONTH(end_date) = '{month}' or ('{month}' > MONTH(start_date) and '{month}' < MONTH(end_date)))
										and year(start_date)='{year}'
										and employee = '{employee}'
										and docstatus = 1; 
		""".format(month=getdate(doc.start_date).month, year=getdate(doc.start_date).year, employee=doc.employee), as_dict=True, debug=True)
    if advance_leave:
        advance_doc = frappe.get_doc("Advance Leave", advance_leave[0]["name"])
        if cint(advance_leave[0]["start_date_month"]) == cint(advance_leave[0]["end_date_month"]):
            # monthrange(getdate(doc.start_date).year, getdate(doc.start_date).month)[1]
            days_in_month = cint(get_month_days(doc.start_date))
            doc.payment_days = flt(days_in_month) - \
                flt(advance_doc.total_advance_leave_days)
            doc.total_working_days = flt(
                days_in_month) - flt(advance_doc.total_advance_leave_days)
        elif cint(getdate(doc.start_date).month) == getdate(advance_doc.start_date).month:
            days_in_month = cint(get_month_days(doc.start_date))
            doc.payment_days = flt(
                days_in_month) - ((flt(days_in_month) - getdate(advance_doc.start_date).day)+1)
            doc.total_working_days = flt(
                days_in_month) - ((flt(days_in_month) - getdate(advance_doc.start_date).day)+1)
            # print("days_in_month=======================" + str(getdate(advance_doc.start_date).day))
            # print("payment_days=======================" + str(doc.payment_days))
        elif cint(getdate(doc.end_date).month) == getdate(advance_doc.end_date).month:
            days_in_month = cint(get_month_days(advance_doc.end_date))
            doc.payment_days = flt(days_in_month) - \
                getdate(advance_doc.end_date).day
            doc.total_working_days = flt(
                days_in_month) - getdate(advance_doc.end_date).day
        elif cint(advance_leave[0]["start_date_month"]) < cint(getdate(doc.start_date).month) < cint(advance_leave[0]["end_date_month"]):
            days_in_month = cint(get_month_days(advance_doc.end_date))
            doc.payment_days = 0
            doc.total_working_days = 0

        if flt(doc.total_working_days) < 0:
            doc.total_working_days = 0
            doc.payment_days = 0
        if flt(doc.leave_without_pay) > 0:
            doc.total_working_days -= flt(doc.leave_without_pay)
            doc.payment_days -= flt(doc.leave_without_pay)
        # frappe.msgprint("total_advance_leave_days=============="+str(advance_doc.total_advance_leave_days))
        earning_amount, deductions_amount = 0, 0
        for item in doc.get("earnings"):
            if item.depends_on_payment_days:
                amount = ((flt(item.default_amount) if flt(item.default_amount) > 0 else flt(
                    item.amount)) / flt(days_in_month)) * (doc.payment_days)
            else:
                amount = flt(item.amount)

            item.amount = amount
            earning_amount += amount

        doc.gross_pay = earning_amount
        doc.base_gross_pay = earning_amount
        doc.gross_year_to_date = earning_amount
        doc.base_gross_year_to_date = earning_amount

        for item in doc.get("deductions"):
            if item.depends_on_payment_days:
                amount = (flt(item.amount) / flt(days_in_month)) * \
                    (doc.payment_days)
            else:
                amount = flt(item.amount)
            item.amount = amount
            deductions_amount += amount

        doc.total_deduction = deductions_amount
        doc.base_total_deduction = deductions_amount

        doc.net_pay = flt(earning_amount) - flt(deductions_amount)
        doc.base_net_pay = doc.net_pay
        doc.rounded_total = round(
            flt(earning_amount) - flt(deductions_amount), 0)
        doc.base_rounded_total = round(
            flt(earning_amount) - flt(deductions_amount), 0)
        doc.year_to_date = flt(earning_amount) - flt(deductions_amount)
        doc.base_year_to_date = doc.year_to_date
        doc.month_to_date = flt(earning_amount) - flt(deductions_amount)
        doc.base_month_to_date = doc.month_to_date
        set_net_total_in_words(doc)


def validate_zero_salary_slip(doc, method=None):
    earning_amount, deductions_amount = 0, 0
    for item in doc.get("earnings"):
        amount = flt(item.amount)
        earning_amount += amount
    if flt(earning_amount) <= 0:
        for item in doc.get("deductions"):
            item.amount = 0

    if flt(earning_amount) <= 0:
        frappe.delete_doc("Salary Slip", doc.name, force=1)
        frappe.db.commit()
        msg = _("Salary Slip Is Deleted ... paid Leave in Advance ")
        frappe.msgprint(msg,
                        title="Info",
                        indicator="Yellow",
                        alert=True)


def set_net_total_in_words(doc):
    default_company = frappe.db.get_single_value(
        "Global Defaults", "default_company")
    company_currency = erpnext.get_company_currency(default_company)
    total = doc.net_pay
    doc.total_in_words = money_in_words(total, company_currency)


def validate_compensations(doc, method=None):
    # frappe.msgprint("validate")
    pass


def calculate_penalty(doc, method=None):
    penalty_list, month_penalty_list = [], []
    mounth_penalty, penalty_amount, calc_using_pre, amount = 0, 0, False, 0
    data = doc.get_data_for_eval()
    # frappe.msgprint("penalty.penalty_type=====" + str(doc.total_deduction))
    data = data[0]
    if "penalties_data" in data:
        # frappe.msgprint(str(data["penalties_data"]))
        CountItems = 0

        # penalties_data = sorted(data['penalties_data'].items(), key=lambda x: x[11], reverse=True)
        penalties_data = sorted(
            data['penalties_data'], key=lambda d: d['apply_date'])
        # penalties_data = dict(newlist)

        hrms_settings = frappe.db.get_singles_dict("HRMS Settings")
        start_date = add_months(getdate(data['start_date']), -1)
        start_date = getdate(str(getdate(start_date).year)+"-"+str(
            getdate(start_date).month)+"-" + str(hrms_settings.deductions_start_day))
        end_date = add_days(getdate(data['start_date']), cint(
            hrms_settings.deductions_end_day)-1)

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
                    # CountItems+=1

                    if penalty.apply_date < getdate(data['end_date']):
                        penalty_list.append(
                            {"penaltytype": penalty.penalty_type, "apply_date": penalty.apply_date})

                    CountItems = Counter(d['penaltytype']
                                         for d in penalty_list)
                    penalty_amount = calc_penalty_amount(
                        doc, penalty["penalty_type"], penalty["apply_date"], CountItems, data)

                    # frappe.msgprint(str(getdate(data['start_date'])) + "======|-----|=====>" + str(getdate(data['end_date'])))

                    if getdate(start_date) <= penalty.apply_date <= getdate(end_date):
                        mounth_penalty += penalty_amount

            # + mounth_penalty# Percentagei comment this because it acumelate the amount of last months to current
            amount = mounth_penalty
            # frappe.msgprint("amount=============" + str(amount))
            if amount:
                component = frappe.db.get_value("Salary Component", {
                                                "name": penalty["penalty_type"], "is_penalties_component": 1}, "name")
                # frappe.msgprint("component=============" + str(component))
                if not component:
                    frappe.throw(_("Please Check Penalty Component.."))
                doc.update_component_row(
                    get_salary_component_data(component),
                    amount,
                    "deductions"
                )
                # doc.gross_pay-=amount
                # doc.base_gross_pay=doc.gross_pay
                # doc.gross_year_to_date-=amount
                # doc.base_gross_year_to_date=doc.gross_year_to_date
                # frappe.msgprint("amount=============" + str(amount))
                # frappe.msgprint("total_deduction=============" + str(doc.total_deduction))
                # if doc.is_new():

                # frappe.msgprint("total_deduction=============" + str(doc.total_deduction))
                doc.base_month_to_date = doc.month_to_date

                doc_currency = doc.currency
                company_currency = erpnext.get_company_currency(doc.company)
                total = doc.net_pay if doc.is_rounding_total_disabled() else doc.rounded_total
                base_total = doc.base_net_pay if doc.is_rounding_total_disabled(
                ) else doc.base_rounded_total
                doc.total_in_words = money_in_words(total, doc_currency)
                doc.base_total_in_words = money_in_words(
                    base_total, company_currency)
        if doc.is_new():
            doc.total_deduction += amount
            doc.net_pay -= amount
            doc.base_net_pay = doc.net_pay
            doc.rounded_total -= amount
            doc.base_rounded_total = doc.base_rounded_total
            doc.year_to_date -= amount
            doc.base_year_to_date = doc.year_to_date
            doc.month_to_date -= amount
    else:
        return amount

    return amount


def calculate_penaltys(doc, method=None):
    penalty_list, month_penalty_list = [], []
    mounth_penalty, penalty_amount, calc_using_pre, amount = 0, 0, 0, False

    data = doc.get_data_for_eval()
    # frappe.msgprint("penalty.penalty_type=====" + str(data))
    if "penalties_data" in data:
        # frappe.msgprint(str(data))
        for penalty in data['penalties_data']:
            if data['end_date']:
                if not data['start_date']:
                    data['start_date'] = data['end_date'].replace(
                        data['end_date'].split('-')[-1], '1')

                rule_start_date = frappe.db.get_value("Penalties Settings", {"penalty_type": penalty.penalty_type},
                                                      "from_date")
                rule_end_date = frappe.db.get_value("Penalties Settings", {"penalty_type": penalty.penalty_type},
                                                    "to_date")
                # frappe.msgprint(str(rule_end_date)+"======"+str(penalty.apply_date)+"=====>" + str(rule_start_date))
                if getdate(rule_start_date) <= penalty.apply_date <= getdate(rule_end_date):
                    # frappe.msgprint(str(rule_end_date) + "======||=====>" + str(rule_start_date))
                    if penalty.apply_date < getdate(data['end_date']):
                        penalty_list.append(
                            {"penaltytype": penalty.penalty_type, "apply_date": penalty.apply_date})
                    if getdate(data['start_date']) <= penalty.apply_date <= getdate(data['end_date']):
                        month_penalty_list.append(
                            {"penaltytype": penalty.penalty_type, "apply_date": penalty.apply_date})

            CountItems = Counter(d['penaltytype'] for d in penalty_list)
            Count_month_penalty = Counter(
                d['penaltytype'] for d in month_penalty_list)

            # frappe.msgprint("additional_penalty============" + str(penalty.additional_penalty))
            penalty_amount = 0
            for item in list(CountItems):
                if Count_month_penalty[item] == 1:
                    calc_using_pre = True
                if (not CountItems[item] == Count_month_penalty[item]) and Count_month_penalty[item]:
                    mounth_penalty += mounth_penalty_amount(
                        month_penalty_list, item, Count_month_penalty[item], data)

            # frappe.msgprint("mounth_penalty=============" + str(mounth_penalty))
            if penalty.additional_penalty != 1 or mounth_penalty == 0:
                if mounth_penalty or calc_using_pre:
                    penalty_amount = pre_penalty_amount(
                        month_penalty_list, CountItems, data, list(Count_month_penalty))
            else:
                penalty_amount = mounth_penalty

            # + mounth_penalty# Percentagei comment this because it acumelate the amount of last months to current
            amount = penalty_amount
            # frappe.msgprint("penalty_amount=============" + str(penalty_amount))
            if amount:
                component = frappe.db.get_value(
                    "Salary Component", {"is_penalties_component": 1}, "name")
                doc.update_component_row(
                    get_salary_component_data(component),
                    amount,
                    "deductions"
                )
                doc.total_deduction += amount
                # doc.gross_pay-=amount
                # doc.base_gross_pay=doc.gross_pay
                # doc.gross_year_to_date-=amount
                # doc.base_gross_year_to_date=doc.gross_year_to_date
                doc.net_pay -= amount
                doc.base_net_pay = doc.net_pay
                doc.rounded_total -= amount
                doc.base_rounded_total = doc.base_rounded_total
                doc.year_to_date -= amount
                doc.base_year_to_date = doc.year_to_date
                doc.month_to_date -= amount
                doc.base_month_to_date = doc.month_to_date

                doc_currency = doc.currency
                company_currency = erpnext.get_company_currency(doc.company)
                total = doc.net_pay if doc.is_rounding_total_disabled() else doc.rounded_total
                base_total = doc.base_net_pay if doc.is_rounding_total_disabled(
                ) else doc.base_rounded_total
                doc.total_in_words = money_in_words(total, doc_currency)
                doc.base_total_in_words = money_in_words(
                    base_total, company_currency)
    else:
        return amount

    return amount


def calc_penalty_amount(doc, penalty_type, apply_date, CountItems, data):
    penalty_amount = 0
    formula = ""
    salary_structure = data["salary_structure"]
    # frappe.msgprint("data==================" + str(data))
    rule_dict = get_penalty_rule(
        doc, penalty_type, apply_date, CountItems, salary_structure, data["employee"])
    # frappe.msgprint("rule_dict==================" + str(rule_dict))
    try:
        formula = rule_dict.strip() if rule_dict else None
    except:
        penalty_amount = rule_dict
    # frappe.msgprint("formula=================="+str(formula))
    if formula:
        penalty_amount += frappe.safe_eval(formula, None, data)
    # frappe.msgprint("penalty_amount==================" + str(penalty_amount))
    return penalty_amount


def pre_penalty_amount(penalty_list, CountItems, data, mounth_pen_list):
    penalty_set = []
    penalty_amount = 0
    formula = ""
    salary_structure = data["salary_structure"]
    for emp_penalty in penalty_list:
        if emp_penalty["penaltytype"] in mounth_pen_list:
            if emp_penalty["penaltytype"] not in penalty_set:
                penalty_set.append(emp_penalty["penaltytype"])
                rule_dict = get_penalty_rule(emp_penalty["penaltytype"], emp_penalty['apply_date'],
                                             CountItems[emp_penalty["penaltytype"]], salary_structure, data["employee"], from_what="pre_penalty_amount")
                # frappe.msgprint("rule_dict==================" + str(rule_dict))
                try:
                    formula = rule_dict.strip() if rule_dict else None
                except:
                    penalty_amount = rule_dict
                # frappe.msgprint("formula=================="+str(formula))
                if formula:
                    penalty_amount += frappe.safe_eval(formula, None, data)
    # frappe.msgprint("penalty_amount==================" + str(penalty_amount))
    return penalty_amount


def get_penalty_rule(doc, penalty, apply_date, times, salary_structure, employee, from_what=""):
    formula = ""
    Penalty_Dict = frappe.db.sql((
        """
		   select PS.penalty_type,PS.from_date,PS.to_date,from_total_earnings ,
		   PD.times, PD.deduct_value,PD.deduct_value_type,PD.deduct_value_of,
		   (select salary_component_abbr from `tabSalary Component` where salary_component=PD.deduct_value_of)  abbr
			from `tabPenalties Settings` PS
				 INNER JOIN `tabPenalties Data` PD
				   on PS.name = PD.parent
				   and PS.penalty_type = %(penalty)s
				   and  %(apply_date)s  BETWEEN PS.from_date AND ifnull(PS.to_date,now())
				   and times = %(times)s
				   order by PS.penalty_type, PD.times ;
		 """
    ), ({'apply_date': apply_date, "penalty": penalty, "times": times[penalty]}),
        as_dict=True, debug=True)

    Calculation_day = cint(get_month_days(apply_date))

    # frappe.msgprint("from_what======||===="+str(from_what))
    # frappe.msgprint("apply_date======||===="+str(apply_date))
    if Penalty_Dict:
        Penalty_Dict = Penalty_Dict[0]
        deduct_value = Penalty_Dict["deduct_value"]
        deduct_value_type = Penalty_Dict["deduct_value_type"]
        abbr = Penalty_Dict["abbr"]
        # frappe.msgprint("from_total_earnings=======================>"+str(Penalty_Dict["from_total_earnings"]))
        if Penalty_Dict["from_total_earnings"]:
            abbr = doc.total_base_earnigns
            # earnings = frappe.db.get_all("Salary Detail",filters={"parent":salary_structure,"parentfield":"earnings"},fields=["abbr"])
            # if earnings:
            # 	abbr = "("
            # 	length = len(earnings)
            # 	counter=0
            # 	for row in earnings:
            # 		abbr+=row["abbr"]
            # 		counter+=1
            # 		if counter< length:
            # 			abbr+=" + "
            # 	start_date = str(get_first_day(apply_date))
            # 	end_date = str(get_last_day(apply_date))
            #
            # 	# frappe.msgprint(str(start_date) + "=======||=====" + str(end_date))
            # 	data = get_additional_salaries(employee, start_date, end_date, "earnings")
            # 	for item in data:
            # 		# print("==================="+str(item))
            # 		if item["include_in_penalty"]==1:
            # 			abbr += " + "+item["abbr"]
            #
            # 	abbr += ")"

        # frappe.msgprint(str(times)+"============"+str(deduct_value)+"==========="+str(abbr))
        if (deduct_value_type == "Day" or deduct_value_type == "Days"):
            formula = "( " + str(abbr) + "/"+str(Calculation_day) + \
                ") *  " + str(float(deduct_value)) + " "
        elif (deduct_value_type == "Percentage"):
            formula = "(" + str(float(deduct_value)) + \
                " / 100) * " + str(abbr) + " "
        elif (deduct_value_type == "Amount"):
            formula = deduct_value
    # frappe.msgprint("formula======||====" + str(formula))
    return formula


def calculate_employee_total_earnings(employee, month_date):
    # frappe.msgprint(str(employee)+"==================="+str(month_date)+"============"+ str(amount))
    data = get_data_for_eval(employee, month_date)

    salary_structure_assignment = check_salary_structure_assignment(
        employee, month_date)
    _salary_structure_doc = frappe.get_doc(
        "Salary Structure", salary_structure_assignment.salary_structure).as_dict()
    total_amount = 0
    for struct_row in _salary_structure_doc["earnings"]:
        amount = eval_condition_and_formula(struct_row, data)
        # print("amount==========================="+str(amount))
        if (
            amount
            or (struct_row.amount_based_on_formula and amount is not None)
            and struct_row.statistical_component == 0
        ):
            total_amount += amount

    return total_amount


def mounth_penalty_amount(month_penalty_list, item, Count_month_penalty, data):
    penalty_amount = 0
    penalty_set = []
    # frappe.msgprint("month_penalty_list============="+str(month_penalty_list))
    # frappe.msgprint("Count_month_penalty======<>======="+str(Count_month_penalty))

    salary_structure = data["salary_structure"]
    for emp_penalty in month_penalty_list:
        if emp_penalty["penaltytype"] == item not in penalty_set:
            if cint(Count_month_penalty) > 1:
                penalty_set.append(emp_penalty["penaltytype"])
                rule_dict = get_penalty_rule(emp_penalty["penaltytype"], emp_penalty['apply_date'],
                                             Count_month_penalty, salary_structure, data["employee"], from_what="mounth_penalty_amount")
                formula = str(rule_dict).strip() if rule_dict else None
                if formula:
                    penalty_amount += frappe.safe_eval(formula, None, data)

    return penalty_amount


def create_bus_captain_users():
    users = frappe.db.sql("""
			select *
				from bus_users ;
		""", as_dict=True)
    if users:
        counter = 0
        print("==========================Starting=============================")
        for user in users:
            counter += 1
            create_user(user["emp_id"], user["email"])
            print(str(counter)+"====User====>" +
                  str(user["email"])+"===========Created")


def create_user(employee, email=None):

    try:
        emp = frappe.get_doc("Employee", employee)
    except:
        print("Error in ==========================" + str(employee))
        return

    employee_name = emp.employee_name.split(" ")
    middle_name = last_name = ""

    if len(employee_name) >= 3:
        last_name = " ".join(employee_name[2:])
        middle_name = employee_name[1]
    elif len(employee_name) == 2:
        last_name = employee_name[1]

    first_name = employee_name[0]

    if email:
        emp.prefered_email = email
    if not frappe.db.exists("User", email):
        user = frappe.new_doc("User")
        user.update({
            "name": emp.employee_name,
            "email": emp.prefered_email,
            "enabled": 1,
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "gender": emp.gender,
            "birth_date": emp.date_of_birth,
            "phone": emp.cell_number,
            "bio": emp.bio,
            'send_welcome_email': 0,
            'user_type': 'System User',
            "new_password": "123456",
            "roles": [{"doctype": "Has Role", "role": "Employee Self Service"}]
        })
        user.insert()
        emp.user_id = email
        # emp.save()
        frappe.db.commit()
        return user.name


def validate_allocation(doc, method=None):
    apply_leave_allocation_policy(doc.name)


def apply_leave_allocation_policy(employee=""):
    print("=======================" + str(employee))
    leaves = {
        "Birth Leave": 3,
        "Death Leave": 5,
        "Exams Leave": 14,
        "Marriage Leave": 5,
        "Maternity Leave": 70,
        "Sick Leave": 90,
        "Annual Leave": 120,
        "Hajj Leave": 14
    }
    filters = {"Status": "Active"}
    if employee:
        filters["name"] = employee
    # filters["name"] = "12992"
    filters["date_of_joining"] = [">=", "2000-01-01"]
    print("======================="+str(filters))
    employees = frappe.db.get_all(
        "Employee", filters=filters, fields="*", order_by="name")
    for employee in employees:
        print(str(employee.date_of_joining) +
              "=======================" + str(employee.name))
        for key, value in leaves.items():
            print("key=======================" + str(key))
            if not frappe.db.exists("Leave Allocation", {"employee": employee.name, "leave_type": key}):
                if employee.gender == "Male" and key == "Maternity Leave":
                    continue
                if key == "Annual Leave" and flt(employee.yearly_vacation) == 0:
                    continue
                elif key == "Annual Leave" and flt(employee.yearly_vacation) > 0:
                    days = date_diff(getdate(), employee.date_of_joining)+1
                    if getdate(employee.date_of_joining) < getdate("2022-09-23"):
                        days = date_diff(
                            getdate(), employee.date_of_joining) + 2

                    rate_per_month = flt(employee.yearly_vacation)/365
                    value = flt(rate_per_month * days)

                allocation = frappe.new_doc("Leave Allocation")
                allocation.employee = employee.name
                allocation.employee_name = employee.employee_name
                allocation.leave_type = key
                allocation.from_date = (employee.date_of_joining if employee.date_of_joining and getdate(
                    employee.date_of_joining) > getdate('2023-01-01') else '2023-01-01')
                # ('2030-12-31' if key=="Hajj Leave" else '2023-12-31')
                allocation.to_date = '2030-12-31'
                allocation.new_leaves_allocated = value
                allocation.total_leaves_allocated = value

                allocation.insert(ignore_permissions=True)
                allocation.submit()
                frappe.db.commit()

                # print("employee====" + str(employee.name) +"=====days===" + str(days) + "=======" + str(key) + "=======" + str(value))


def submit_leave_allocations():
    leaves = frappe.db.get_all("Leave Allocation", filters={
                               "docstatus": 0}, fields=["*"])
    if leaves:
        print("=======================Starting=======================")
        for item in leaves:
            try:
                doc = frappe.get_doc("Leave Allocation", item["name"])
                doc.submit()
                print("=======================" +
                      str(item["name"])+" is Submited=======================")
            except:
                print("========Error In ===============" +
                      str(item["name"]) + "=======================")


def submit_ss_assignments():
    ss_assignments = frappe.db.get_all("Salary Structure Assignment", filters={
                                       "docstatus": 0}, fields=["*"])
    if ss_assignments:
        print("=======================Starting=======================")
        for item in ss_assignments:
            try:
                doc = frappe.get_doc(
                    "Salary Structure Assignment", item["name"])
                doc.submit()
                print("=======================" +
                      str(item["name"])+" is Submited=======================")
            except:
                print("========Error In ===============" +
                      str(item["name"]) + "=======================")


def create_dayoff_attendance():
    date = add_days(getdate(), -1)
    days = frappe.db.sql("""
		select *
			from `tabDayOff`
			where '{date}' between from_date and to_date
				and docstatus = 1
			 order by `tabDayOff`.docstatus asc, `tabDayOff`.`modified` DESC

		""".format(date=date), as_dict=True)
    if days:
        for row in days:
            try:
                att_name = create_attendance(
                    row["employee"], date, row["name"])
            except:
                pass


def create_old_dayoff():
    date = add_days(getdate(), -1)
    days = frappe.db.sql("""
		select *
			from `tabDayOff`
			where to between from_date and to_date
				and docstatus = 1
			 order by `tabDayOff`.docstatus asc, `tabDayOff`.`modified` DESC

		""".format(date=date), as_dict=True)
    if days:
        for row in days:
            try:
                att_name = create_attendance(
                    row["employee"], date, row["name"])
                frappe.db.sql("""
					update tabDayOff
						set attendance_reference_id= '{ref}'
							where `name` = '{row_id}'
					""".format(ref=att_name, row_id=row["name"]))
            except:
                pass


def create_attendance(employee, dt, docname):
    date = dt.strftime("%Y-%m-%d")
    doc = frappe.new_doc("Attendance")
    doc.employee = employee
    doc.attendance_date = date
    doc.status = "DayOff"
    doc.dayoff_reference_ = docname
    doc.attend_time = ""
    doc.leave_time = ""
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name


def migrate_payroll_data():
    # frappe.db.sql("truncate table `tabSalary Structure Assignment` ;", as_dict=True)
    # frappe.db.sql("truncate table `tabAdditional Salary` ; ", as_dict=True)
    data = frappe.db.sql(
        "select * from payroll_data order by id; ", as_dict=True)
    length = len(data)
    counter = 1
    if data:
        print("========================Starting=========================")
        for item in data:
            print(str(str(counter)+"/"+str(length)) +
                  "=========Working With ===================="+str(item["id"]))
            try:
                # frappe.db.get_value("Employee",item["id"],"date_of_joining")
                from_date = "2023-10-15"
                if not frappe.db.exists("Salary Structure Assignment", {"employee": item["id"]}):
                    if item["nationality"] == "Saudi":
                        create_salary_structure_assignment(
                            item["id"], "1-9 Standard Salary Structure (Saudi)", item["basic"], from_date)
                    else:
                        create_salary_structure_assignment(
                            item["id"], "1-9 Standard Salary Structure (None Saudi)", item["basic"], from_date)
                    print("====================Salary Structure Assignment Added")

                if not frappe.db.exists("Additional Salary", {"employee": item["id"], "salary_component": "Nature of work Allowance"}) and flt(item["n_of_work"]) > 0:
                    create_additional_salary(
                        item["id"], "Nature of work Allowance", flt(item["n_of_work"]), from_date)
                    print("====================Nature of work Allowance Added")

                if not frappe.db.exists("Additional Salary", {"employee": item["id"], "salary_component": "Phone Allowance"}) and flt(item["phone"]) > 0:
                    create_additional_salary(
                        item["id"], "Phone Allowance", flt(item["phone"]), from_date)
                    print("====================Phone Allowance Added")

                if not frappe.db.exists("Additional Salary", {"employee": item["id"], "salary_component": "Responsibility Allowance"}) and flt(item["respo"]) > 0:
                    create_additional_salary(
                        item["id"], "Responsibility Allowance", flt(item["respo"]), from_date)
                    print("====================Responsibility Allowance Added")

                if not frappe.db.exists("Additional Salary", {"employee": item["id"], "salary_component": "Fuel Allowance"}) and flt(item["fuel"]) > 0:
                    create_additional_salary(
                        item["id"], "Fuel Allowance", flt(item["fuel"]), from_date)
                    print("====================Fuel Allowance Added")

                if not frappe.db.exists("Additional Salary", {"employee": item["id"], "salary_component": "Other Additional", "payroll_date": from_date}) and flt(item["other_additional"]) > 0:
                    create_additional_salary(item["id"], "Other Additional", flt(
                        item["other_additional"]), from_date)
                    print("====================Other Additional Added")

                if not frappe.db.exists("Additional Salary", {"employee": item["id"], "salary_component": "Other Additional 25th", "payroll_date": from_date}) and flt(item["other_additional_25"]) > 0:
                    create_additional_salary(item["id"], "Other Additional 25th", flt(
                        item["other_additional_25"]), from_date)
                    print("====================Other Additional 25th Added")

                if not frappe.db.exists("Additional Salary", {"employee": item["id"], "salary_component": "End Of Service Benefits EOS", "payroll_date": from_date}) and flt(item["end_of_service"]) > 0:
                    create_additional_salary(item["id"], "End Of Service Benefits EOS", flt(
                        item["end_of_service"]), from_date)
                    print("====================End Of Service Benefits EOS Added")

                if not frappe.db.exists("Additional Salary", {"employee": item["id"], "salary_component": "Penalty", "payroll_date": from_date}) and flt(item["penalty"]) > 0:
                    create_additional_salary(
                        item["id"], "Penalty", flt(item["penalty"]), from_date)
                    print("====================Penalty Added")

                if not frappe.db.exists("Additional Salary", {"employee": item["id"], "salary_component": "Absence", "payroll_date": from_date}) and flt(item["absence"]) > 0:
                    create_additional_salary(item["id"], "Absence", flt(
                        item["absence"]), from_date, component_type="Deduction")
                    print("====================Absence Added")

                if not frappe.db.exists("Additional Salary", {"employee": item["id"], "salary_component": "Late Minutes", "payroll_date": from_date}) and flt(item["late"]) > 0:
                    create_additional_salary(item["id"], "Late Minutes", flt(
                        item["late"]), from_date, component_type="Deduction")
                    print("====================Late Added")

                if not frappe.db.exists("Additional Salary", {"employee": item["id"], "salary_component": "Half Day Deduction", "payroll_date": from_date}) and flt(item["half"]) > 0:
                    create_additional_salary(item["id"], "Half Day Deduction", flt(
                        item["half"]), from_date, component_type="Deduction")
                    print("====================Half Day Deduction Added")

                if not frappe.db.exists("Additional Salary", {"employee": item["id"], "salary_component": "Sick leave Deduction", "payroll_date": from_date}) and flt(item["sick"]) > 0:
                    create_additional_salary(item["id"], "Sick leave Deduction", flt(
                        item["sick"]), from_date, component_type="Deduction")
                    print("====================Sick leave Deduction Added")

            except Exception as e:
                print("======================"+str(e))

            counter += 1
            frappe.db.commit()
    print("========================Finished=========================")


def migrate_deductions_data():
    data = frappe.db.sql(
        "select * from deductions order by employee; ", as_dict=True)
    length = len(data)
    counter = 1
    if data:
        print("========================Starting=========================")
        for item in data:
            print(str(str(counter)+"/"+str(length)) +
                  "=========Working With ===================="+str(item["employee"]))
            # try:
            from_date = "2023-08-10"
            date_of_joining = frappe.db.get_value(
                "Employee", item["employee"], "date_of_joining")
            if getdate(date_of_joining) > getdate(from_date):
                from_date = date_of_joining
            if not frappe.db.exists("Additional Salary", {"employee": item["employee"], "salary_component": "Other Deduction", "payroll_date": ["=", from_date]}) and flt(item["other_deductions"]) > 0:
                create_additional_salary(item["employee"], "Other Deduction", flt(
                    item["other_deductions"]), from_date, component_type="Deduction")
                print("====================other deductions")

            # print("Traffic Violation======================"+str(frappe.db.exists("Additional Salary",{"employee": item["employee"], "salary_component": "Traffic Violation","payroll_date":["=",from_date]})))
            if not frappe.db.exists("Additional Salary", {"employee": item["employee"], "salary_component": "Traffic Violation", "payroll_date": ["=", from_date]}) and flt(item["traffic_violation"]) > 0:
                create_additional_salary(item["employee"], "Traffic Violation", flt(
                    item["traffic_violation"]), from_date, component_type="Deduction")
                print("====================Traffic Violation")

            if not frappe.db.exists("Additional Salary", {"employee": item["employee"], "salary_component": "Advance Pay Housing", "payroll_date": ["=", from_date]}) and flt(item["advance_ha"]) > 0:
                create_additional_salary(item["employee"], "Advance Pay Housing", flt(
                    item["advance_ha"]), from_date, component_type="Deduction")
                print("====================Advance Pay Housing")

            if not frappe.db.exists("Additional Salary", {"employee": item["employee"], "salary_component": "Absence", "payroll_date": ["=", from_date]}) and flt(item["absence"]) > 0:
                create_additional_salary(item["employee"], "Absence", flt(
                    item["absence"]), from_date, component_type="Deduction")
                print("====================Absence")

            if not frappe.db.exists("Additional Salary", {"employee": item["employee"], "salary_component": "Additional Penalty", "payroll_date": ["=", from_date]}) and flt(item["additional_penalty"]) > 0:
                create_additional_salary(item["employee"], "Additional Penalty", flt(
                    item["additional_penalty"]), from_date, component_type="Deduction")
                print("====================Additional Penalty")

            if not frappe.db.exists("Additional Salary", {"employee": item["employee"], "salary_component": "Late Minutes", "payroll_date": ["=", from_date]}) and flt(item["late_minutes"]) > 0:
                create_additional_salary(item["employee"], "Late Minutes", flt(
                    item["late_minutes"]), from_date, component_type="Deduction")
                print("====================Late Minutes")

            if not frappe.db.exists("Additional Salary", {"employee": item["employee"], "salary_component": "Half Day Deduction", "payroll_date": ["=", from_date]}) and flt(item["half_day_deduction"]) > 0:
                create_additional_salary(item["employee"], "Half Day Deduction", flt(
                    item["half_day_deduction"]), from_date, component_type="Deduction")
                print("====================Half Day Deduction")

            if not frappe.db.exists("Additional Salary", {"employee": item["employee"], "salary_component": "Sick leave Deduction", "payroll_date": ["=", from_date]}) and flt(item["sick_leave_deduction"]) > 0:
                create_additional_salary(item["employee"], "Sick leave Deduction", flt(
                    item["sick_leave_deduction"]), from_date, component_type="Deduction")
                print("====================Sick leave Deduction")

            # except Exception as e:
            # 	print("======================"+str(e))

            counter += 1
            frappe.db.commit()
    print("========================Finished=========================")


def migrate_resign_data():
    data = frappe.db.sql(
        "select * from resign_date order by employee; ", as_dict=True)
    length = len(data)
    counter = 1
    if data:
        print("========================Starting=========================")
        for item in data:
            print(str(str(counter)+"/"+str(length)) +
                  "=========Working With ===================="+str(item["employee"]))
            try:
                emp_doc = frappe.get_doc("Employee", item["employee"])
                emp_doc.relieving_date = item["resign_date"]
                emp_doc.save()
                print("====================relieving date Updated")
            except Exception as e:
                print("======================"+str(e))

            counter += 1
            frappe.db.commit()
    print("========================Finished=========================")


def add_salary_structure_assignment():
    data = frappe.db.sql("""
			select *
				from salary_assig;
		""", as_dict=True)
    if data:
        print("========================Started=========================")
        for row in data:
            employee = row.employee
            salary_structure = row.salary_structure
            base = row.base
            from_date = row.from_date
            print("========================" +
                  str(employee)+"=========================")
            date_of_joining = frappe.db.get_value(
                "Employee", employee, "date_of_joining")
            if getdate(date_of_joining) > getdate(from_date):
                from_date = date_of_joining
            if not frappe.db.exists("Salary Structure Assignment", {"employee": employee}):
                # try:
                create_salary_structure_assignment(
                    employee, salary_structure, base, from_date)
                print("========================" + str(employee) +
                      "=========================Submitted")
                # except Exception as e:
                # 	print(str(employee)+"======================"+str(e))

        print("========================Finished=========================")


def create_salary_structure_assignment(employee, salary_structure, base, from_date):
    assignment = frappe.new_doc("Salary Structure Assignment")
    assignment.employee = employee
    assignment.salary_structure = salary_structure
    assignment.company = "Saptco"
    assignment.currency = "SAR"
    assignment.payroll_payable_account = "2120 - Payroll Payable - SAT"
    assignment.from_date = (from_date if from_date else "2022-09-01")
    assignment.base = base
    assignment.variable = 0
    assignment.insert(ignore_permissions=True)
    assignment.submit()


def create_additional_salary(emp_id, component, amount, from_date, component_type="Earning"):  # Deduction
    add_sal = frappe.new_doc("Additional Salary")
    add_sal.employee = emp_id
    add_sal.salary_component = component
    add_sal.payroll_date = from_date
    # add_sal.is_recurring = 1
    # add_sal.from_date = (from_date if from_date else "2022-01-01")
    # add_sal.to_date = "2023-12-31"
    add_sal.amount = amount
    add_sal.type = component_type
    add_sal.year = 2023
    add_sal.overwrite_salary_structure_amount = 1
    add_sal.payroll_month = "June"
    add_sal.currency = "SAR"  # erpnext.get_default_currency()
    add_sal.insert()
    add_sal.submit()


@frappe.whitelist()
def check_user_id(employee):
    user_id = frappe.db.get_value(
        "Employee", {"user_id": frappe.session.user}, "name")
    # frappe.msgprint(str(user_id)+"==========="+str(employee))
    if (user_id == employee):
        return user_id


def create_banks():
    data = frappe.db.sql("""
			select *
				from temp;
		""", as_dict=True)
    if data:
        for item in data:
            if not frappe.db.exists("Bank", item["bank_name"]):
                doc = frappe.new_doc("Bank")
                doc.bank_name = item["bank_name"]
                doc.insert()
                frappe.db.commit()
                print("=====================================" +
                      str(item["bank_name"]))


def remove_stopped_employees(employee, start_date, end_date):
    # print("employee=================="+str(employee))
    # print("start_date==================" + str(start_date))
    # print("end_date==================" + str(end_date))
    salary_month = getdate(start_date).month
    salary_year = getdate(start_date).year

    data = frappe.db.get_value("Stop Salary Slip", {"employee": employee}, [
                               "name", "month_from", "month_to", "year"], as_dict=True)
    if data:
        # {'name': '11030-22-08-33937', 'month_from': 'August', 'month_to': 'October'}
        # print("data==================" + str(data))
        # print("employee==================" + str(employee))
        month_from = get_month_map(data["month_from"])
        month_to = get_month_map(data["month_to"])
        stop_year = cint(data["year"])
        # print("month_from==================" + str(month_from))
        # print("month_to==================" + str(month_to))
        if month_from <= salary_month <= month_to and salary_year == stop_year:
            # print("=========Stopped=========")
            return True
        else:
            print("=========Not Stopped=========")
    return False


def remove_not_iban_employees(employee):
    iban = frappe.db.get_value("Employee", employee, "bank_ac_no")
    if iban:
        return True
    else:
        return False


def validate_employee_iban(employee):
    iban = frappe.db.get_value("Employee", employee, "iban")
    if iban:
        return True
    else:
        return False


# def check_back_from_leave(employee, start_date, end_date):

#     data = frappe.db.sql("""

# 			""")


def get_month_map(month):
    months = frappe._dict(
        {
            "January": 1,
            "February": 2,
            "March": 3,
            "April": 4,
            "May": 5,
            "June": 6,
            "July": 7,
            "August": 8,
            "September": 9,
            "October": 10,
            "November": 11,
            "December": 12,
        }
    )
    return months.get(month, 0)


@frappe.whitelist()
def validate_lwp_leaves_for_employee_portal(doctype, txt, searchfield, start, page_len, filters):
    user = frappe.session.user
    roles = frappe.get_roles(user)
    for role in ["Employee Self Service", "Employee", "All", "Guest"]:
        if role in roles:
            roles.remove(role)
    condition = ""
    if len(roles) == 0:
        condition = " and is_lwp = 0 "
    # frappe.msgprint("condition==================="+str(condition))
    return frappe.db.sql(
        """select name from `tabLeave Type`
		where name is not NULL {condition}
		and %s like %s order by name limit %s, %s""".format(condition=condition)
        % (searchfield, "%s", "%s", "%s"),
        ("%%%s%%" % txt, start, page_len),
        as_list=1,
    )


def calculate_employee_deductions(employee, month_date, amount):
    # frappe.msgprint(str(employee)+"=========|=========="+str(month_date)+"======||======"+ str(amount))

    start_date = get_first_day(month_date)
    end_date = get_last_day(month_date)

    precision = get_currency_precision() or 2
    data = get_data_for_eval(employee, month_date)

    salary_structure_assignment = check_salary_structure_assignment(
        employee, month_date)
    _salary_structure_doc = frappe.get_doc(
        "Salary Structure", salary_structure_assignment.salary_structure).as_dict()

    total_earnigns = calculate_total_component_type(
        employee, _salary_structure_doc, data, "earnings", start_date, end_date)
    total_deductions = calculate_total_component_type(
        employee, _salary_structure_doc, data, "deductions", start_date, end_date)

    max_deductions_percentage_from_total_earnings = frappe.db.get_single_value(
        'HRMS Settings', 'max_deductions_percentage_from_total_earnings')

    max_amount = flt(total_earnigns) * \
        (flt(max_deductions_percentage_from_total_earnings)/100)

    remaining_Amount = flt(max_amount) - flt(total_deductions)
    # frappe.msgprint(str(max_amount) + "=====<====|=======>===>" + str(total_deductions))
    if flt(total_deductions+amount) > flt(total_earnigns) * (flt(max_deductions_percentage_from_total_earnings)/100):
        msg = frappe.bold(_("Total Deductions ({0}) Should not Exceed Max Percentage {1} % of Total Earnings , The reamining amount is ({2}) ").format(
            flt(total_deductions+amount, precision), cint(max_deductions_percentage_from_total_earnings), remaining_Amount))
        frappe.throw(msg)
    return total_earnigns, total_deductions


def calculate_total_component_type(employee, _salary_structure_doc, data, component_type, start_date, end_date):
    total_amount = 0
    for struct_row in _salary_structure_doc[component_type]:
        amount = eval_condition_and_formula(struct_row, data)

        if (
            amount
            or (struct_row.amount_based_on_formula and amount is not None)
            and struct_row.statistical_component == 0
        ):
            total_amount += amount

    additional_salaries = get_additional_salaries(
        employee, start_date=start_date, end_date=end_date, component_type=component_type)
    for additional_salary in additional_salaries:
        total_amount += flt(additional_salary.amount)
    # frappe.msgprint(str(employee) + "=========|==========>" + str(total_amount))
    return total_amount


def eval_condition_and_formula(d, data):
    try:
        whitelisted_globals = {
            "int": int,
            "float": float,
            "long": int,
            "round": round,
            "date": datetime.date,
            "getdate": getdate,
        }

        condition = d.condition.strip().replace("\n", " ") if d.condition else None
        if condition:
            if not frappe.safe_eval(condition, whitelisted_globals, data):
                return None
        amount = d.amount
        if d.amount_based_on_formula:
            formula = d.formula.strip().replace("\n", " ") if d.formula else None
            # frappe.msgprint("formula==================="+str(formula))
            if formula:
                precision = get_currency_precision() or 2
                amount = flt(frappe.safe_eval(
                    formula, whitelisted_globals, data), precision)
                # frappe.msgprint("amount===================" + str(amount))
        if amount:
            data[d.abbr] = amount

        return amount

    except NameError as err:
        frappe.throw(
            _("{0} <br> This error can be due to missing or deleted field.").format(err),
            title=_("Name error"),
        )
    except SyntaxError as err:
        frappe.throw(
            _("Syntax error in formula or condition: {0}").format(err))
    except Exception as e:
        frappe.throw(_("Error in formula or condition: {0}").format(e))
        raise


def get_data_for_eval(employee, month_date):
    """Returns data for evaluating formula"""
    data = frappe._dict()
    employee = frappe.get_doc("Employee", employee).as_dict()

    start_date = get_first_day(month_date)
    date_to_validate = (
        employee.date_of_joining if employee.date_of_joining > start_date else start_date
    )

    salary_structure_assignment = check_salary_structure_assignment(
        employee.name, date_to_validate)
    if not salary_structure_assignment:
        frappe.throw(
            _(
                "Please assign a Salary Structure for Employee {0} " "applicable from or before {1} first"
            ).format(
                frappe.bold(employee.employee_name),
                frappe.bold(formatdate(date_to_validate)),
            )
        )

    data.update(salary_structure_assignment)
    data.update(employee)
    # data.update(self.as_dict())

    # set values for components
    salary_components = frappe.get_all(
        "Salary Component", fields=["salary_component_abbr"])
    for sc in salary_components:
        data.setdefault(sc.salary_component_abbr, 0)

    sal_structure = frappe.get_doc(
        "Salary Structure", salary_structure_assignment.salary_structure)
    for key in ("earnings", "deductions"):
        for d in sal_structure.get(key):
            # print("d========================" + str(d))
            data[d.abbr] = d.amount

    return data


def check_salary_structure_assignment(employee, date):
    return frappe.get_value(
        "Salary Structure Assignment",
        {
            "employee": employee,
            "from_date": ("<=", date),
            "docstatus": 1,
        },
        "*",
        order_by="from_date desc",
        as_dict=True,
    )


def check_total_deduction_percentage(doc, method=None):
    if doc.type == "Deduction":
        if not doc.is_recurring:
            calculate_employee_deductions(
                doc.employee, doc.payroll_date, doc.amount)
        else:
            addDays = timedelta(days=30)
            from_date = getdate(doc.from_date)
            to_date = getdate(doc.to_date)
            while from_date <= to_date:
                # add a month
                from_date += addDays
                calculate_employee_deductions(
                    doc.employee, from_date, doc.amount)


def update_additional_salary_payroll_date(doc, method=None):
    if not doc.payroll_date:
        doc.payroll_date = getdate()
        doc.save()


def check_total_deductions_percentage(doc, method=None):
    calculate_employee_deductions(
        doc.employee, doc.date_of_the_cutoff, doc.amount)


def check_relieving_date():
    employees = frappe.db.get_all(
        "Employee", filters={"relieving_date": getdate()}, fields="name")
    if employees:
        for employee in employees:
            doc = frappe.get_doc("Employee", employee["name"])
            doc.status = "Left"
            doc.save()
            frappe.db.commit()


def add_monthly_leave_balance(doc, method=None):
    employees = frappe.db.get_all("Employee", filters={"yearly_vacation": [
                                  ">", 0]}, fields=["name", "yearly_vacation"])  # "name":"11030",
    if employees:
        for employee in employees:
            try:
                allocation = frappe.db.get_value("Leave Allocation", {
                                                 "employee": employee["name"], "leave_type": "Annual Leave"}, "name", order_by="from_date desc")
                ledger = frappe.db.get_value("Leave Ledger Entry", {
                                             "employee": employee["name"], "leave_type": "Annual Leave"}, "name", order_by="from_date desc")
                if allocation:
                    allocation_doc = frappe.get_doc(
                        "Leave Allocation", allocation)
                    # ledger_doc = frappe.get_doc("Leave Ledger Entry", ledger)

                    monthly_balance = flt(employee["yearly_vacation"])/12

                    # print("monthly_balance============="+str(monthly_balance)+"======="+str(flt(ledger_doc.leaves)))

                    # ledger_doc.db_set("leaves", (flt(ledger_doc.leaves)+monthly_balance))

                    new_allocation = (
                        flt(allocation_doc.new_leaves_allocated)+monthly_balance)
                    allocation_doc.db_set(
                        "new_leaves_allocated", new_allocation)
                    allocation_doc.db_set(
                        "total_leaves_allocated", new_allocation)

                    # ledger_doc.flags.ignore_validate_update_after_submit = True
                    allocation_doc.flags.ignore_validate_update_after_submit = True

                    frappe.db.commit()

                    print("Employee====="+str(employee)+"=====yearly_vacation" +
                          str(employee["yearly_vacation"])+"====="+str(monthly_balance))

            except Exception as e:
                print("employee==============="+str(employee) +
                      "====Error==============="+str(e))


def add_net_credit():
    employees = frappe.db.sql("""
			select employee `name`,net_credit
				from emp_data e
						order by employee
		""", as_dict=True)  # "name":"11030",
    # where employee ='11030'
    if employees:
        for employee in employees:
            try:
                allocation = frappe.db.get_value("Leave Allocation", {
                                                 "employee": employee["name"], "leave_type": "Annual Leave"}, "name", order_by="from_date desc")
                ledger = frappe.db.get_value("Leave Ledger Entry", {
                                             "employee": employee["name"], "leave_type": "Annual Leave", "leaves": [">", 0]}, "name", order_by="from_date desc")
                if allocation:
                    allocation_doc = frappe.get_doc(
                        "Leave Allocation", allocation)
                    ledger_doc = frappe.get_doc("Leave Ledger Entry", ledger)

                    monthly_balance = flt(employee["net_credit"])

                    # print("monthly_balance============="+str(monthly_balance)+"======="+str(flt(ledger_doc.leaves)))

                    ledger_doc.db_set("leaves", flt(monthly_balance))

                    allocation_doc.db_set(
                        "new_leaves_allocated", monthly_balance)
                    allocation_doc.db_set(
                        "total_leaves_allocated", monthly_balance)

                    # ledger_doc.flags.ignore_validate_update_after_submit = True
                    allocation_doc.flags.ignore_validate_update_after_submit = True

                    frappe.db.commit()

                    print("Employee====="+str(employee)+"=====net_credit====" +
                          str(employee["net_credit"])+"====="+str(monthly_balance))

            except Exception as e:
                print("employee==============="+str(employee) +
                      "====Error==============="+str(e))


def add_daily_leave_balance():
    # "name":["in",['10074','10085','10135','10141','10202','10318','10362','10366','10549','10673','10783','10803','10828','11145','11164','11213','11215','11230','11373']]
    employees = frappe.db.get_all("Employee", filters={"yearly_vacation": [">", 0], "status": "Active", }, fields=[
                                  "name", "yearly_vacation"], order_by="name")  # "name":"11030",
    if employees:
        days_in_month = monthrange(getdate().year, getdate().month)[1]
        for employee in employees:
            try:
                total_unpaid_days = 0
                if check_on_leave(employee.name):
                    unpaid = frappe.db.sql("""
								select (ifnull(sum(total_leave_days),0) + (select ifnull(sum(number_of_days),0) from `tabDeduct Days from Service Period` where employee=L.employee)) days
									from `tabLeave Application` L
										where leave_type='Unpaid Leave'
										 and employee = '{employee}'
										 and NOW() > from_date
							""".format(employee=employee.name), as_dict=True)
                    if unpaid:
                        total_unpaid_days = (0 if flt(unpaid[0]["days"]) <= 20 else (
                            flt(unpaid[0]["days"]) - 20))
                        if total_unpaid_days > 0:
                            continue
                allocation = frappe.db.get_value("Leave Allocation", {
                                                 "employee": employee["name"], "leave_type": "Annual Leave"}, "name", order_by="from_date desc")
                ledger = frappe.db.get_value("Leave Ledger Entry", {
                                             "employee": employee["name"], "leave_type": "Annual Leave", "leaves": [">", 0]}, "name", order_by="from_date desc")
                if allocation:
                    allocation_doc = frappe.get_doc(
                        "Leave Allocation", allocation)
                    ledger_doc = frappe.get_doc("Leave Ledger Entry", ledger)

                    ledger_doc.flags.ignore_validate_update_after_submit = True
                    allocation_doc.flags.ignore_validate_update_after_submit = True
                    data = get_years_of_service(employee["name"])
                    service_days = data[1]

                    # * 20 ----2022-11-04
                    monthly_balance = (flt(employee["yearly_vacation"])/365)
                    if service_days > 1825:
                        monthly_balance = (30 / 365)
                    # print("monthly_balance============="+str(monthly_balance)+"======="+str(flt(ledger_doc.leaves)))

                    new_allocation = (
                        flt(allocation_doc.new_leaves_allocated)+monthly_balance)

                    allocation_doc.db_set(
                        "new_leaves_allocated", new_allocation)
                    allocation_doc.db_set(
                        "total_leaves_allocated", new_allocation)

                    ledger_doc.db_set(
                        "leaves", (flt(ledger_doc.leaves)+monthly_balance))

                    frappe.db.commit()

                    print("Employee====="+str(employee)+"=====yearly_vacation"+str(employee["yearly_vacation"])+"============"+str(
                        (flt(employee["yearly_vacation"])/12))+"====="+str(monthly_balance))

            except Exception as e:
                print("employee==============="+str(employee) +
                      "====Error==============="+str(e))


def check_on_leave(employee):
    data = frappe.db.sql("""
		    select employee
					from `tabLeave Application`
						where leave_type='Unpaid Leave'
								and now() between from_date and to_date
								and employee = '{employee}'
		""".format(employee=employee), as_dict=True)
    if data:
        return True
    else:
        return False


def add_deduct_days_from_service_period():
    data = frappe.db.sql("""
					select *
						from emp_data
								where oracle_unpaid > 0	 
			""", as_dict=True)
    if data:
        print("================Starting=================")
        conter = 0
        for employee in data:
            conter += 1
            print(str(conter)+"-"+str(len(data)) +
                  "======================="+str(employee.employee))
            doc = frappe.new_doc("Deduct Days from Service Period")
            doc.employee = employee.employee
            doc.employee_name = employee.employee_name
            doc.type = "Service Period"
            doc.posting_date = "2023-01-01"
            doc.number_of_days = employee.oracle_unpaid
            try:
                doc.save()
                frappe.db.commit()
                print("Saved=========="+str(employee.employee))
            except:
                print("Error======"++str(employee.employee))


def check_relieving_date_for_leave_balance(doc, method=None):
    print("================Checking....================")
    if doc.relieving_date:
        print("================Proccessing....================")
        reduce_leave_balance(doc)


def reduce_leave_balance(employee):
    print("================starting....================")
    days = date_diff(getdate(), employee.relieving_date)+1
    days_in_month = monthrange(getdate().year, getdate().month)[1]

    print("days==================="+str(days))
    for i in range(days):
        try:
            allocation = frappe.db.get_value("Leave Allocation", {
                                             "employee": employee.name, "leave_type": "Annual Leave"}, "name", order_by="from_date desc")
            ledger = frappe.db.get_value("Leave Ledger Entry", {
                                         "employee": employee.name, "leave_type": "Annual Leave", "leaves": [">", 0]}, "name", order_by="from_date desc")
            if allocation:
                allocation_doc = frappe.get_doc("Leave Allocation", allocation)
                ledger_doc = frappe.get_doc("Leave Ledger Entry", ledger)

                ledger_doc.flags.ignore_validate_update_after_submit = True
                allocation_doc.flags.ignore_validate_update_after_submit = True

                # * 20 ----2022-11-04
                monthly_balance = (
                    (flt(employee.yearly_vacation)/12) / days_in_month) * -1

                # print("monthly_balance============="+str(monthly_balance)+"======="+str(flt(ledger_doc.leaves)))

                new_allocation = (
                    flt(allocation_doc.new_leaves_allocated)+monthly_balance)

                allocation_doc.db_set("new_leaves_allocated", new_allocation)
                allocation_doc.db_set("total_leaves_allocated", new_allocation)

                ledger_doc.db_set(
                    "leaves", (flt(ledger_doc.leaves)+monthly_balance))

                frappe.db.commit()

                print("Employee====="+str(employee.name)+"=====yearly_vacation"+str(employee.yearly_vacation) +
                      "============"+str((flt(employee.yearly_vacation)/12))+"====="+str(monthly_balance))

        except Exception as e:
            print("employee==============="+str(employee) +
                  "====Error==============="+str(e))


def submit_leave_allocations():
    allocations = frappe.db.get_all("Leave Allocation", filters={
                                    "docstatus": 0}, fields=["*"], order_by="employee")
    if allocations:
        for row in allocations:
            doc = frappe.get_doc("Leave Allocation", row["name"])
            try:
                doc.submit()
                frappe.db.commit()
                print("Employee=====" + str(row["employee"])+"===is Submittes")
            except Exception as e:
                print("employee===============" +
                      str(row["employee"])+"====Error==============="+str(e))


def submit_employee_hours_details():
    allocations = frappe.db.get_all("Employee Hours Details", filters={
                                    "docstatus": 0, "owner": "ahmed.gaber@ptco.com.sa"}, fields=["*"], order_by="employee")
    if allocations:
        for row in allocations:
            doc = frappe.get_doc("Employee Hours Details", row["name"])
            try:
                doc.submit()
                frappe.db.commit()
                print("Employee=====" + str(row["employee"])+"===is Submittes")
            except Exception as e:
                print("employee===============" +
                      str(row["employee"])+"====Error==============="+str(e))


def cancel_employee_hours_details():
    allocations = frappe.db.get_all("Employee Hours Details", filters={"docstatus": 0, "creation": [
                                    ">=", "2023-06-12"], "owner": ["!=", "ahmed.gaber@ptco.com.sa"]}, fields=["*"], order_by="employee")
    if allocations:
        for row in allocations:
            doc = frappe.get_doc("Employee Hours Details", row["name"])
            try:
                doc.submit()
                frappe.db.commit()
                print("Employee=====" + str(row["employee"])+"===is Submittes")
            except Exception as e:
                print("employee===============" +
                      str(row["employee"])+"====Error==============="+str(e))


def submit_leave_applications():
    allocations = frappe.db.get_all("Leave Application", filters={
                                    "docstatus": 0}, fields=["*"], order_by="employee desc")
    if allocations:
        for row in allocations:
            doc = frappe.get_doc("Leave Application", row["name"])
            try:
                doc.submit()
                frappe.db.commit()
                print("Employee=====" + str(row["employee"])+"===is Submittes")
            except Exception as e:
                print("employee===============" +
                      str(row["employee"])+"====Error==============="+str(e))


def make_stop_salary():
    data = frappe.db.sql("""
			select employee,reason
				from stop_salary
		""", as_dict=True)
    if data:
        for row in data:
            doc = frappe.new_doc("Stop Salary Slip")
            doc.employee = row["employee"]
            doc.month_from = "October"
            doc.month_to = "October"
            doc.posting_date = getdate()
            doc.reason = row["reason"]
            try:
                doc.insert()
                doc.submit()
                frappe.db.commit()
                print("employee===============" + str(row.employee))
            except Exception as e:
                print("====Error===============" + str(e))


def add_employee_overtime_data():
    list_employee_hours = frappe.db.sql("""
			select *
				from overtime;
			""", as_dict=True)
    for item in list_employee_hours:
        try:
            if not frappe.db.exists("Employee Hours Details", str(item.employee+"-2023-August-Day 15")):
                new_doc = frappe.new_doc("Employee Hours Details")
                new_doc.name = str(item.employee+"-2023-August-Day 15")
                new_doc.employee = item.employee
                # new_doc.employee_name = item.employee_name
                new_doc.year = 2023
                new_doc.overwrite_salary_structure_amount = 0
                new_doc.payroll_frequency = "Day 15"
                new_doc.month = "August"
                new_doc.over_time_in_working_hours = item.overtime
                new_doc.insert()
                new_doc.submit()
                print("employee==============="+str(item.employee) +
                      "====OverTime==============="+str(item.overtime))
        except Exception as e:
            print("employee==============="+str(item.employee) +
                  "====Error==============="+str(e))


def add_employee_contracts():
    data = frappe.db.sql("""
			select *
				from contracts 
				order by employee
				;
		""", as_dict=True)
    if data:
        length = len(data)
        counter = 0
        print("==========================Starting=============================")
        for row in data:
            try:
                if not frappe.db.exists("Employee contract", {"employee": row.employee, "docstatus": 1}):
                    counter += 1
                    doc = frappe.new_doc("Employee contract")
                    doc.contract_number = row.employee
                    doc.contract_number = row.employee
                    doc.statuss = "Active"
                    doc.employee = row.employee
                    doc.contract_type = (
                        "عقد عمل سعودى" if row.nationality == "Saudi" else "عقد عمل أجنبي")
                    doc.employee_nationality = row.nationality
                    doc.date_of_agreement = row.joining_date
                    doc.data_7 = flt(row.duration) * 12
                    contract_start_date = ("2022-01-01" if getdate("2022-01-01")
                                           > getdate(row.joining_date) else getdate(row.joining_date))
                    doc.contract_start_date = contract_start_date
                    doc.contratc_end_date = add_days(add_months(
                        contract_start_date, flt(row.duration) * 12), -1)
                    # print("============================"+str(add_days(add_months(contract_start_date,flt(row.duration) * 12),-1)))

                    if row.salary_structure:
                        doc.salary_structure = row.salary_structure
                    category = {
                        "21": "21 Day",
                        "30": "30 Day",
                        "38": "38 Day"
                    }
                    doc.employee_leave_category = category.get(
                        row.leave_balance, "21 Day")
                    doc.yearly_vacation = row.leave_balance

                    if row.salary_structure:
                        doc.salary_structure = row.salary_structure
                        doc.save()
                        doc.submit()
                    else:
                        doc.save()

                    print(str(counter) + "/"+str(length)+"====Employee====>" +
                          str(row.employee) + "===========Created")
            except Exception as e:
                print("employee==============="+str(row.employee) +
                      "====Error==============="+str(e))


def insert_salary_component(doc, method=None):
    component = frappe.db.get_value(
        "Salary Component", {"name": doc.name, "is_penalties_component": 1}, "name")
    print("component========================="+str(component))
    if not component:
        salary_component = frappe.new_doc("Salary Component")

        salary_component.salary_component = doc.name
        salary_component.type = "Deduction"
        salary_component.is_penalties_component = 1
        salary_component.depends_on_payment_days = 0
        salary_component.salary_component_abbr = make_autoname("PEN.#####")

        salary_component.append(
            "accounts",
            dict(
                company=erpnext.get_default_company(),
                # account="510068 - Employee Other Deductions - PT",
            ),
        )
        try:
            salary_component.insert()
            frappe.db.commit()
            print("======" + str(doc.name)+"==========Inserted")
        except Exception as e:
            print("======" + str(e)+"======")


def insert_component_from_pealty_type():
    for penalty in frappe.db.get_all("Penalty Type", filters={}, fields="*"):
        penalty = frappe._dict(penalty)
        print("========================="+str(penalty.name))
        insert_salary_component(penalty)


def get_month_name(date):
    month_number = date.month
    months = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }
    # from hrms.hr.doctype.attendance.attendance import get_month_map as get_month_name
    for month, number in months.items():
        if number == month_number:
            return month


def update_private_files(doc, method=None):
    data = frappe.db.sql("""
		select `name`,leave_attachment
			from `tabLeave Application`
				where leave_type='Sick Leave'
		""", as_dict=True)
    if data:
        for item in data:
            try:
                frappe.db.sql("""
						update  tabFile
								set is_private = 0,
								attached_to_name = '{attached_to_name}'
										where file_url = '{path}'
				""".format(attached_to_name=item["name"], path=item["leave_attachment"]))
            except:
                pass

            frappe.db.commit()


def update_traffic_private_files(doc, method=None):
    data = frappe.db.sql("""
		select `name`,violation_document
			from `tabTraffic Violations`
		""", as_dict=True)
    if data:
        for item in data:
            frappe.db.sql("""
					update  tabFile
							set is_private = 0,
							attached_to_name = '{attached_to_name}'
									where file_url = '{path}'
			""".format(attached_to_name=item["name"], path=item["violation_document"]))
            frappe.db.commit()


def update_exam_private_files(doc, method=None):
    data = frappe.db.sql("""
		select `name`, document
			from `tabDriving licenses Exam`
		""", as_dict=True)
    if data:
        for item in data:
            frappe.db.sql("""
					update  tabFile
							set is_private = 0,
							attached_to_name = '{attached_to_name}'
									where file_url = '{path}'
			""".format(attached_to_name=item["name"], path=item["document"]), debug=True)
            frappe.db.commit()


def get_attendence_sheet_status():
    emp_list = []
    emp_dict = {}
    prev = add_months(getdate(), -1)
    start_date = getdate(str(getdate(prev).year)+"-" +
                         str(getdate(prev).month)+"-15")
    end_date = getdate(str(getdate().year) + "-" +
                       str(getdate().month) + "-14")

    day_status = {
        "Present": "P",
        "Absent": "A",
        "Sick Leave": "SL",
        "Half day": "HD",
        "Day off": "DO",
        "Exam Leave": "EL",
        "Annual Leave": "AL",
        "Unpaid Leave": "UL",
        "Hajj Leave": "HL",
        "Marriage Leave": "RH",
        "Birth Leave": "RH",
        "Death Leave": "RH"
    }
    employees = frappe.db.get_all("Employee", filters={
                                  "name": "11030", "status": "active"}, fields="*", order_by="name")
    counter = 1
    if employees:

        for employee in employees:
            month_attended_list = []
            emp_dict["idx"] = counter
            emp_dict["id"] = employee.name
            emp_dict["name"] = employee.employee_name
            emp_dict["job_title"] = employee.designation
            emp_dict["date_of_joining"] = employee.date_of_joining
            emp_dict["nationality"] = employee.nationality

            while start_date <= end_date:
                if is_holiday(employee.holiday_list, start_date):
                    month_attended_list.append("DO")

                daystatus = get_days_status(start_date, employee.name)
                month_attended_list.append(day_status.get(daystatus, "P"))

                start_date = add_days(start_date, 1)
            counter += 1
            emp_list.append(emp_dict)
            emp_list.append(month_attended_list)
        print("=================="+str(emp_list))


def get_days_status(day, employee):
    leave_type = check_day_on_leave(day, employee)
    if leave_type:
        return leave_type


def check_day_on_leave(day, employee):
    leave_type = ""
    data = frappe.db.sql("""
		    select leave_type
					from `tabLeave Application`
						where '{day}' between from_date and to_date
								and employee = '{employee}'
								and docstatus = 1
		""".format(day=day, employee=employee), as_dict=True, debug=False)
    if data:
        return data[0]["leave_type"]
    # print("leave_type=================="+str(leave_type))
    return leave_type


def get_days_list():
    period_dict = {}
    first_days_list, second_days_list = [], []
    prev = getdate()
    if getdate().day <= 16:
        prev = add_months(getdate(), -1)
    start_date = getdate(str(getdate(prev).year)+"-" +
                         str(getdate(prev).month)+"-15")
    last_day = get_last_day(start_date)
    while start_date < last_day:
        start_date = add_days(start_date, 1)
        first_days_list.append(getdate(start_date).day)

    period_dict[str(get_month_full_name(getdate(prev).month)) +
                "."+str(getdate(prev).year)] = first_days_list

    end_date = getdate(str(getdate().year) + "-" +
                       str(getdate().month) + "-15")
    start_date = get_first_day(end_date)
    while start_date <= end_date:
        second_days_list.append(getdate(start_date).day)
        start_date = add_days(start_date, 1)

    period_dict[str(get_month_full_name(getdate().month)) +
                "." + str(getdate().year)] = second_days_list
    return period_dict


def update_employee_status(status="Late Minutes", day_date="2023-02-28", employee="11030", note="MiM", late_minutes=10):
    print("status====================="+str(status))
    switch = {
        "Late Minutes": add_late_minutes(day_date, employee, late_minutes, note),
        "Present": add_attendence("Present", day_date, employee, note),
        "Absent": add_attendence("Absent", day_date, employee, note),
        "Sick leave": add_leave("Sick leave", day_date, employee, note),
        "Half Day": add_leave("Half Day", day_date, employee, note),
        "Day Off": add_day_off(day_date, employee, note),
        "Exam leave": add_leave("Exam leave", day_date, employee, note),
        "Annual Leave": add_leave("Annual leave", day_date, employee, note),
        "Unpaid Leave": add_leave("Unpaid leave", day_date, employee, note),
        "Hajj Leave": add_leave("Hajj leave", day_date, employee, note),
        "Marriage": add_leave("Marriage leave", day_date, employee, note),
        "Birth": add_leave("Birth leave", day_date, employee, note),
        "Death": add_leave("Death leave", day_date, employee, note)
    }
    switch.get(status, "")


def upload_late_minuites_and_absence():
    data = frappe.db.sql("""
		select *	
			from late_abs
			order by employee
		""", as_dict=True)
    if data:
        counter = 1
        total_no = len(data)
        print("===============Starting===============")
        for row in data:
            print(str(total_no) + "/" + str(counter) +
                  "==>" + str(row["employee"]))
            try:
                if cint(row["late_min"]) > 0:
                    add_late_minutes(
                        "2023-05-15", row["employee"], cint(row["late_min"]), "MiM")
                    print("late============"+str(row["late_min"]))
                if cint(row["absent_days"]) > 0:
                    day = 1
                    while day <= cint(row["absent_days"]):
                        daydate = add_days("2023-04-16", day)
                        add_attendence("Absent", daydate,
                                       row["employee"], "MiM", submit=True)
                        day += 1
            except Exception as e:
                frappe.db.sql(
                    "update late_abs set `status` = %s where employee =%s ", (e, row["employee"]))
            counter += 1
        print("===============Finished===============")


def add_late_minutes(day_date, employee, late_minutes, note):
    check_day_status(employee, day_date)
    print("==========Here===========")
    # item = frappe.db.get_value("Late Minutes", {"employee": employee,"month":get_month_name(getdate(day_date)),"year":getdate(day_date).year},"name")
    item = frappe.db.get_value(
        "Late Minutes", {"employee": employee, "day_date": getdate(day_date)}, "name")
    print("================="+str(item))
    if item:
        dc = frappe.get_doc("Late Minutes", item)
        dc.cancel()
        frappe.delete_doc_if_exists("Late Minutes", item)

    print("=================" + str(get_month_name(getdate(day_date))))
    print("=================" + str(getdate(day_date).year))
    doc = frappe.new_doc("Late Minutes")
    doc.employee = employee
    doc.late_minutes = late_minutes
    # doc.month = get_month_name(getdate(day_date))
    # doc.year = getdate(day_date).year
    doc.day_date = getdate(day_date)
    doc.notes = note
    doc.save()
    doc.submit()


def add_day_off(day_date, employee, note):
    check_day_status(employee, day_date)
    doc = frappe.new_doc("DayOff")
    doc.employee = employee
    doc.from_date = day_date
    doc.to_date = add_days(day_date, 1)
    doc.small_text_8 = note
    doc.insert()


def add_attendence(status, day_date, employee, note, submit=False):
    check_day_status(employee, day_date)
    doc = frappe.new_doc("Attendance")
    doc.employee = employee
    doc.status = status
    doc.attendance_date = day_date
    doc.company = erpnext.get_default_company()
    doc.insert()
    if submit:
        doc.submit()


def add_leave(leave_type, day_date, employee, note, days=0):
    check_day_status(employee, day_date)
    emp_leave_approver = frappe.get_value(
        "Employee", employee, "leave_approver")
    department = frappe.get_value("Employee", employee, "department")
    if not emp_leave_approver:
        emp_leave_approver = frappe.get_value(
            "Department Approver", {"parent": department}, "approver")

    new_doc = frappe.new_doc("Leave Application")
    new_doc.posting_date = day_date
    new_doc.employee = employee
    new_doc.leave_type = leave_type
    new_doc.from_date = day_date
    new_doc.to_date = (add_days(day_date, 1) if days ==
                       0 else add_days(day_date, cint(days)))
    new_doc.status = 'Approved'
    new_doc.leave_approver = emp_leave_approver
    new_doc.follow_via_email = 0
    try:
        new_doc.save()
        new_doc.submit()
        frappe.db.commit()
    except Exception as e:
        print(str(e))
        return frappe.db.sql("""
			update sick_leaves set `status` = '{error}' where employee = '{employee}' ;
			""".format(error=str(e), employee=employee))


def check_day_status(employee, day_date):
    attendence = frappe.db.get_value(
        "Attendance", {"employee": employee, "attendance_date": day_date}, "name")
    if attendence:
        delete_overlab_doc(attendence, "Attendance")
        # frappe.throw(_("Day is Already Marked for Attendance"))

    leaves = frappe.db.get_value("Leave Application", {"employee": employee, day_date: [
                                 "between", ("from_date", "to_date")]}, "name")
    if leaves:
        delete_overlab_doc(leaves, "Leave Application")
        # frappe.throw(_("Day is Already Marked for Leave"))

    dayoff = frappe.db.get_value("DayOff", {"employee": employee, day_date: [
                                 "between", ("from_date", "to_date")]}, "name")
    if dayoff:
        delete_overlab_doc(dayoff, "DayOff")
        # frappe.throw(_("Day is Already Marked for DayOff"))


def delete_overlab_doc(docname, doctitle):
    doc = frappe.get_doc(doctitle, docname)
    if doc.docstatus == 1:
        doc.cancel()
    if doc.docstatus != 0:
        doc.delete()
    frappe.db.commit()


def add_sick_leaves():
    data = frappe.db.sql("""	
			select *
				from sick_leaves
				order by employee
		""", as_dict=True)
    if data:
        print("===============Starting===============")
        for employee in data:
            print("Employee==================="+str(employee["employee"]))
            add_leave("Sick Leave", employee["start_date"], employee["employee"], "", cint(
                employee["leaves"])-1)
        print("===============Finished===============")


def submit_sick_leaves():
    data = frappe.db.sql("""	
			select *
				from sick_leaves
				order by employee
		""", as_dict=True)
    if data:
        for employee in data:
            print("employee==============="+str(employee["employee"]))
            leaves = frappe.db.get_all("Leave Application", filters={
                                       "leave_type": "Sick Leave", "docstatus": 0, "employee": employee["employee"]}, fields="*")
            if leaves:
                for leave in leaves:
                    try:
                        doc = frappe.get_doc(
                            "Leave Application", leave["name"])
                        print("employee===============" + str(doc.name))
                        doc.submit()
                    except Exception as e:
                        print("=============="+str(e))


def get_days_list():
    period_dict_1 = {}
    period_dict_2 = {}
    months = []
    first_days_list, second_days_list = [], []
    prev = getdate()
    if getdate().day <= 16:
        prev = add_months(getdate(), -1)
    start_date = getdate(str(getdate(prev).year) + "-" +
                         str(getdate(prev).month) + "-15")
    last_day = get_last_day(start_date)
    while start_date < last_day:
        start_date = add_days(start_date, 1)
        first_days_list.append(getdate(start_date).day)

    period_dict_1[str('name')] = str(get_month_full_name(
        getdate(prev).month)) + "." + str(getdate(prev).year)
    period_dict_1[str('days')] = first_days_list
    months.append(period_dict_1)

    next = getdate()
    if getdate().day > 16:
        next = add_months(getdate(), 1)
    end_date = getdate(str(getdate().year) + "-" +
                       str(getdate(next).month) + "-15")
    start_date = get_first_day(end_date)
    while start_date <= end_date:
        second_days_list.append(getdate(start_date).day)
        start_date = add_days(start_date, 1)
    period_dict_2[str('name')] = str(get_month_full_name(
        getdate(next).month)) + "." + str(getdate(next).year)
    period_dict_2[str('days')] = second_days_list
    months.append(period_dict_2)
    return months


@frappe.whitelist()
def get_attendance_sheet_status(employee_name='', department='', limit_start=0, limit_page_length=10):
    emp_list = []
    day_status = {
        "Present": "P",
        "Absent": "A",
        "Absence Leave": "A",
        "Sick Leave": "SL",
        "Half day": "HD",
        "Day off": "DO",
        "Exam Leave": "EL",
        "Annual Leave": "AL",
        "Unpaid Leave": "UL",
        "Hajj Leave": "HL",
        "Marriage Leave": "RH",
        "Birth Leave": "RH",
        "Death Leave": "RH"
    }
    filters = {"status": "active"}
    if employee_name:
        filters["name"] = employee_name
    if department:
        filters["department"] = department

    employees = frappe.db.get_list("Employee", filters=filters, fields="*", order_by="name",
                                   limit=10, limit_start=limit_start, limit_page_length=limit_page_length)

    counter = 1
    if employees:
        for employee in employees:
            emp_dict = {}
            month_attended_list = []
            year_attended_list = [0, 0, 0, 0, 0,
                                  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
            prev = getdate()
            if getdate().day <= 16:
                prev = add_months(getdate(), -1)

            start_date = getdate(str(getdate(prev).year) +
                                 "-" + str(getdate(prev).month) + "-16")

            next = getdate()
            if getdate().day > 16:
                next = add_months(getdate(), 1)

            end_date = getdate(str(getdate(next).year) +
                               "-" + str(getdate(next).month) + "-15")

            emp_dict["idx"] = counter
            emp_dict["id"] = employee.name
            emp_dict["name"] = employee.employee_name
            emp_dict["job_title"] = employee.designation
            emp_dict["date_of_joining"] = employee.date_of_joining
            emp_dict["nationality"] = employee.nationality
            emp_dict["location"] = employee.branch

            while start_date <= end_date:
                if is_holiday(employee.holiday_list, start_date):
                    month_attended_list.append({str(start_date): 'DO'})
                    year_attended_list[0] += 1
                else:
                    daystatus = get_days_status(start_date, employee.name)
                    print("daystatus================"+str(daystatus))
                    status = day_status.get(daystatus, "P")
                    print("status================"+str(status))
                    if status == "P":
                        year_attended_list[0] += 1
                    if status == "A":
                        year_attended_list[1] += 1
                    if status == "SL":
                        year_attended_list[3] += 1
                    if status == "EL":
                        year_attended_list[5] += 1
                    if status == "AL":
                        year_attended_list[6] += 1
                    if status == "UL":
                        year_attended_list[7] += 1
                    if status == "HL":
                        year_attended_list[8] += 1
                    if status == "RH":
                        year_attended_list[9] += 1

                    month_attended_list.append({str(start_date): status})
                start_date = add_days(start_date, 1)
            counter += 1
            emp_dict["month_attended_list"] = month_attended_list
            emp_dict["year_attended_list"] = year_attended_list
            # print("emp_dict[month_attended_list]===============================" + str(emp_dict))
            emp_list.append(emp_dict)

    # emp_list.append(month_attended_list)

    return emp_list


def calculate_annual_leave_balance(selected_employee="13004", from_date=""):
    filters = {"status": "Active", "yearly_vacation": ["!=", ""]}
    if selected_employee:
        filters["name"] = selected_employee
    employees = frappe.db.get_all(
        "Employee", filters=filters, fields="*", order_by="name")  # ,"name":"11030"
    total_no = len(employees)
    emp = 1
    for employee in employees:
        print("employee==================="+str(employee.name))
        data = get_years_of_service(employee.name)
        service_details = data[0]
        service_days = data[1]
        start_date = employee.date_of_joining
        if from_date:
            additiona_days = date_diff(getdate(from_date), getdate())
            service_days += cint(additiona_days)

        end_date = add_days(employee.date_of_joining, service_days)
        print(str(service_days)+"===================" + str(service_details))
        leave_days = 0
        counter = 1
        while start_date <= end_date:
            leave_days += ((flt(employee.yearly_vacation)/365)
                           if counter <= 1825 else (30/365))
            # print(str(start_date)+"==================="+str(flt(employee.yearly_vacation)))
            start_date = add_days(start_date, 1)
            counter += 1
        # annual_used = frappe.db.sql("""
        # 		select ifnull(annual_used,0) annual_used
        # 		from emp_data
        # 			where employee ='{employee}'
        # 		""".format(employee=employee.name),as_dict=True)
        # if annual_used:
        # 	leave_days-=flt(annual_used[0]["annual_used"])

        # print("leave_days=========>>==========" + str(leave_days))
        # added_leaves = frappe.db.sql("""
        # 			select sum(days) days
        # 				from added_leaves
        # 				where employee='{employee}'
        # 				group by employee
        # 		""".format(employee=employee.name),as_dict=True)
        #
        # if added_leaves:
        # 	leave_days+=flt(added_leaves[0]["days"])

        print("("+str(total_no)+")--"+str(emp)+"=======================" +
              str(leave_days)+"=======================")

        if selected_employee:
            return leave_days

        allocation = frappe.db.get_value("Leave Allocation", {
                                         "employee": employee["name"], "leave_type": "Annual Leave"}, "name", order_by="from_date desc")
        ledger = frappe.db.get_value("Leave Ledger Entry", {
                                     "employee": employee["name"], "leave_type": "Annual Leave", "leaves": [">", 0]}, "name", order_by="from_date desc")
        if allocation:
            try:
                allocation_doc = frappe.get_doc("Leave Allocation", allocation)
                ledger_doc = frappe.get_doc("Leave Ledger Entry", ledger)

                ledger_doc.db_set("leaves", flt(leave_days))
                allocation_doc.db_set("new_leaves_allocated", leave_days)
                allocation_doc.db_set("total_leaves_allocated", leave_days)

                ledger_doc.flags.ignore_validate_update_after_submit = True
                allocation_doc.flags.ignore_validate_update_after_submit = True

                frappe.db.commit()
            except Exception as e:
                print("==================>"+str(e))
        emp += 1


def get_years_of_service(employee):
    date_of_joining = frappe.db.get_value(
        "Employee", employee, "date_of_joining")
    if (not date_of_joining):
        frappe.throw("Please set date of joining")
    deducted_days = frappe.db.get_value("Deduct Days from Service Period", {
                                        "name": employee, "type": "Service Period"}, "number_of_days") or 0
    total_leave_days = 0
    unpaid_leaves = frappe.db.sql("""
		select sum(DATEDIFF(case when to_date > NOW() then NOW() else to_date end,from_date)+1) total_leave_days
			from `tabLeave Application`
				where employee = '{employee}'
					and leave_type='Unpaid Leave'
					and NOW() >from_date
					and docstatus = 1
	""".format(employee=employee), as_dict=True)

    print("service_days===================" +
          str(date_diff(getdate(), date_of_joining)))
    print("unpaid_leaves===================" + str(unpaid_leaves))
    print("deducted_days===================" + str(deducted_days))
    if unpaid_leaves:
        total_leave_days = unpaid_leaves[0]["total_leave_days"] or 0

    total_leave_days += deducted_days
    print("total_leave_days===================" + str(total_leave_days))
    if total_leave_days < 20:
        total_leave_days = 0
    else:
        total_leave_days -= 20

    deducted_days = total_leave_days

    print("deducted_days===================" + str(deducted_days))
    service_details = get_dates_diff(
        add_days(date_of_joining, deducted_days), add_days(getdate(), 1))
    service_days = date_diff(getdate(), add_days(
        date_of_joining, deducted_days))
    return service_details, service_days


def upload_oracle_unpaid_days():
    data = frappe.db.sql("""
			select *
					from emp_data
						where oracle_unpaid is not NULL
			""", as_dict=True)
    if data:
        for emp in data:
            exist_row = frappe.db.get_value("Deduct Days from Service Period", {
                                            "employee": emp["employee"]}, "name")
            if not exist_row:
                doc = frappe.new_doc("Deduct Days from Service Period")
                doc.employee = emp["employee"]
                doc.type = "Service Period"
                doc.number_of_days = emp["oracle_unpaid"]
                doc.posting_date = getdate()
                doc.insert()


def check_daily_sick_leave(employee=""):
    filters = {"status": "Active"}
    if employee:
        filters["name"] = employee

    employees = frappe.db.get_all(
        "Employee", filters=filters, fields="*", order_by="name")
    total_no = len(employees)
    counter = 1
    for employee in employees:
        allocation = frappe.db.get_value("Leave Allocation", {
                                         "employee": employee.name, "leave_type": "Sick Leave"}, "name", order_by="from_date desc")
        try:
            if allocation:
                counter += 1
                allocation_doc = frappe.get_doc("Leave Allocation", allocation)
                if getdate() > getdate(allocation_doc.to_date):

                    start_date = add_days(getdate(allocation_doc.to_date), 1)
                    end_date = add_days(getdate(start_date), 365)

                    allocation = frappe.new_doc("Leave Allocation")
                    allocation.employee = employee.name
                    allocation.employee_name = employee.employee_name
                    allocation.leave_type = "Sick Leave"
                    allocation.from_date = start_date
                    allocation.to_date = end_date
                    allocation.new_leaves_allocated = 120
                    allocation.total_leaves_allocated = 120

                    allocation.insert(ignore_permissions=True)
                    allocation.submit()
                    frappe.db.commit()

                    print(str(total_no) + "/" + str(counter) + "==>" +
                          str(employee.name) + "=====> Succeeded")

        except Exception as e:
            print("Error============" + str(e))

        # print(str(total_no) + "/" + str(counter) + "==>" + str(employee.name) + "====" + str(start_date) + "====" + str(end_date) + "====" + str(left_days))


def renew_sick_leaves(employee=""):
    filters = {"status": "Active"}
    if employee:
        filters["name"] = employee

    employees = frappe.db.get_all(
        "Employee", filters=filters, fields="*", order_by="name")  # ,"name":"11030"
    total_no = len(employees)
    counter = 1
    for employee in employees:
        # print("employee==================="+str(employee.name))
        start_date, end_date = "", ""
        data = frappe.db.sql("""
			select *
				from `tabLeave Application`
					where leave_type='Sick Leave'
						and docstatus=1
						and employee = '{employee}'
						order by from_date
			""".format(employee=employee.name), as_dict=True)
        if data:
            for item in data:
                if not start_date:
                    start_date = item["from_date"]
                    end_date = add_days(start_date, 364)

                    # print(str(start_date)+"================"+str(end_date))
                    continue

                if getdate(item["to_date"]) > getdate(end_date):
                    start_date = end_date
                    end_date = add_days(getdate(end_date), 364)

                # print(str(start_date) + "================" + str(end_date))

            left_days = date_diff(end_date, getdate())

            print(str(total_no)+"/"+str(counter)+"==>"+str(employee.name)+"====" +
                  str(start_date) + "====" + str(end_date) + "====" + str(left_days))
            counter += 1

            status = frappe.db.sql("""
						select `status`
							from updated_employees
								where employee = '{employee}'
					""".format(employee=employee.name), as_dict=True)
            if status:
                status = status[0]["status"]
            if not status or status == "Failed":
                allocation = frappe.db.get_value("Leave Allocation", {
                                                 "employee": employee.name, "leave_type": "Sick Leave"}, "name", order_by="from_date desc")
                ledger = frappe.db.get_value("Leave Ledger Entry", {
                                             "employee": employee.name, "leave_type": "Sick Leave", "leaves": [">", 0]}, "name", order_by="from_date desc")
                try:
                    if allocation:
                        allocation_doc = frappe.get_doc(
                            "Leave Allocation", allocation)
                        ledger_doc = frappe.get_doc(
                            "Leave Ledger Entry", ledger)

                        ledger_doc.flags.ignore_validate_update_after_submit = True
                        allocation_doc.flags.ignore_validate_update_after_submit = True

                        allocation_doc.db_set("to_date", add_days(
                            getdate(start_date if getdate(end_date) > getdate() else end_date), -1))
                        ledger_doc.db_set("to_date", add_days(
                            getdate(start_date if getdate(end_date) > getdate() else end_date), -1))
                        frappe.db.commit()

                        # if allocation_doc.to_date == add_days(getdate(end_date),-1):
                        allocation = frappe.new_doc("Leave Allocation")
                        allocation.employee = employee.name
                        allocation.employee_name = employee.employee_name
                        allocation.leave_type = "Sick Leave"
                        allocation.from_date = (start_date if getdate(
                            end_date) > getdate() else end_date)
                        to_date = add_days(getdate(end_date), 364)
                        allocation.to_date = (end_date if getdate(
                            end_date) > getdate() else to_date)
                        allocation.new_leaves_allocated = 120
                        allocation.total_leaves_allocated = 120

                        allocation.insert(ignore_permissions=True)
                        allocation.submit()
                        frappe.db.commit()
                    update_employee_status(employee.name, "Succeed")
                except Exception as e:
                    update_employee_status(employee.name, "Failed")
                    print("============"+str(e))


def add_first_sick_leave_date():
    data = frappe.db.sql("""
			select *
				from first_sick_leave_dates
			""", as_dict=True)
    if data:
        total_no = len(data)
        counter = 0
        print("==========================Starting=============================")
        for row in data:
            counter += 1
            try:
                delete_sick_leaves(row["employee"])

                allocation = frappe.new_doc("Leave Allocation")
                allocation.employee = row.employee
                allocation.leave_type = "Sick Leave"
                allocation.from_date = row.first_sick_leave_date
                allocation.to_date = add_days(row.first_sick_leave_date, 364)
                allocation.new_leaves_allocated = 120
                allocation.total_leaves_allocated = 120
                allocation.insert(ignore_permissions=True)
                allocation.submit()
                frappe.db.commit()

                check_daily_sick_leave(row.employee)

                print(str(total_no) + "/" + str(counter) + "==>" +
                      str(row.employee) + "=====> Succeeded")
            except Exception as e:
                print("Error============" + str(e))
        print("==========================Finished=============================")


def delete_sick_leaves(employee):
    leaves = frappe.db.get_all("Leave Allocation", filters={
                               "leave_type": "Sick Leave", "employee": employee}, fields="*")
    if leaves:
        for item in leaves:
            frappe.db.sql("""
					delete from `tabLeave Allocation` 
						where `name` = '{leave}' 
				""".format(leave=item["name"]))


def update_employee_status(employee, status):
    check = frappe.db.sql("""
			select employee
				from updated_employees
		""", as_dict=True)
    if check:
        return frappe.db.sql("""
						update updated_employees set status='{status}' where employee='{employee}'
					""".format(employee=employee, status=status))

    return frappe.db.sql("""
				insert into updated_employees (employee,status) values ('{employee}','{status}')
			""".format(employee=employee, status=status))


def check_day_status(employee, day_date):
    attendence = frappe.db.get_value(
        "Attendance", {"employee": employee, "attendance_date": day_date}, "name")
    if attendence:
        delete_overlab_doc(attendence, "Attendance")

    # leaves = frappe.db.get_value("Leave Application",{"employee":employee,day_date:["between", ("from_date", "to_date")]},"name")
    leaves = frappe.db.sql("""
            select *
                from `tabLeave Application`
                    where employee = '{employee}'
                        and '{day_date}' between from_date and to_date
                            and docstatus != 2
    """.format(employee=employee, day_date=day_date), as_dict=True)
    if leaves:
        delete_overlab_doc(leaves[0]["name"], "Leave Application")

    # dayoff = frappe.db.get_value("DayOff",{"employee":employee,day_date:["between", ("from_date", "to_date")]},"name")
    dayoff = frappe.db.sql("""
            select *
                from `tabDayOff`
                    where employee = '{employee}'
                        and '{day_date}' between from_date and to_date
                            and docstatus != 2
    """.format(employee=employee, day_date=day_date), as_dict=True)

    if dayoff:
        delete_overlab_doc(dayoff[0]["name"], "DayOff")

    item = frappe.db.get_value(
        "Late Minutes", {"employee": employee, "day_date": day_date}, "name")
    if item:
        delete_overlab_doc(item, "Late Minutes")


def push_mails_queue(doc, method=None):
    push_mail_queue()


def push_mail_queue():
    from frappe.email.queue import send_one
    mails = frappe.db.get_all("Email Queue", filters={
                              "status": "Not Sent"}, fields="*")
    if mails:
        for mail in mails:
            try:
                send_one(mail.name, now=True)
            except:
                pass


def upload_employee_penalties():
    data = frappe.db.sql("""
			select *
				from penalities
		""", as_dict=True)
    if data:
        length = len(data)
        counter = 1
        print("========================Starting=========================")
        for row in data:
            try:
                if frappe.db.exists("Employee Penalties",
                                    {"docstatus": ["in", [0, 1]], "employee": row["emploee"], "penalty_type": row["penalty"], "penalty_date": row["p_date"], "apply_date": "2023-05-5", "remark": "MiM"}):
                    continue
                doc = frappe.new_doc("Employee Penalties")
                doc.posting_date = getdate()
                doc.employee = row["emploee"]
                doc.penalty_type = row["penalty"]
                doc.penalty_date = row["p_date"]
                doc.apply_date = "2023-05-5"
                doc.remark = "MiM"
                doc.insert()
                doc.submit()
                frappe.db.sql(
                    "update penalities set `status` = null where emploee = %s ", (row["emploee"]))
            except Exception as e:
                print(str(str(counter) + "/" + str(length)) +
                      "====Failed ====" + str(row["emploee"]))
                frappe.db.sql(
                    "update penalities set `status` = %s where emploee = %s ", (str(e), row["emploee"]))
                print("Error========"+str(e))
            counter += 1
        print("========================Finished=========================")


def upload_traffic_violatios():
    data = frappe.db.sql("""
			select *
				from traffic_violatios
		""", as_dict=True)
    if data:
        length = len(data)
        counter = 1
        print("========================Starting=========================")
        for row in data:
            try:
                if frappe.db.exists("Traffic Violations",
                                    {"docstatus": ["in", [0, 1]], "employee": row["employee"], "violation_type": row["violation"], "violation_type": row["violation"], "amount": row["amount"], "vehicle": row["number"]}):
                    continue
                doc = frappe.new_doc("Traffic Violations")
                doc.employee = row["employee"]
                # doc.employee_name = row["emp_name"]
                doc.posting_date = getdate()
                doc.vehicle = row["number"]
                doc.violation_type = row["violation"]
                doc.violation_date = getdate()
                doc.amount = row["amount"]
                doc.payroll_date = getdate()
                doc.insert()
                doc.submit()
                print(str(str(counter) + "/" + str(length)) +
                      "====Succedded ====" + str(row["employee"]))
            except Exception as e:
                print(str(str(counter) + "/" + str(length)) +
                      "====Failed ====" + str(row["employee"]))
                frappe.db.sql("update traffic_violatios set `status` = %s where employee = %s and amount=%s", (str(
                    e), row["employee"], row["amount"]))
                print("Error========"+str(e))
            counter += 1
        print("========================Finished=========================")


def update_slips():
    data = frappe.db.sql("""
			select *
				from `tabSalary Slip`
					where start_date='2023-07-01'
							and end_date='2023-07-31'
							and payroll_frequency='Monthly'
							and docstatus=0
							and employee in (select employee from slips)
		""", as_dict=True)
    if data:
        length = len(data)
        counter = 1
        print("========================Starting=========================")
        for row in data:
            try:
                doc = frappe.get_doc("Salary Slip", row["name"])
                doc.posting_date = '2023-06-21'
                doc.save()
                frappe.db.commit()
            except Exception as e:
                print(str(str(counter) + "/" + str(length)) +
                      "====Failed ====" + str(row["employee"]))
                frappe.db.sql(
                    "update slips set `status` = %s where employee = %s ", (str(e), row["employee"]))
                print("Error========"+str(e))
            counter += 1
        print("========================Finished=========================")


def delete_slips():
    data = frappe.db.sql("""
			select *
				from `tabSalary Slip`
					where start_date='2023-07-01'
							and end_date='2023-07-31'
							and payroll_frequency='Monthly'
							and docstatus=0
							and employee in (select employee from del_slips)
		""", as_dict=True)
    if data:
        length = len(data)
        counter = 1
        print("========================Starting=========================")
        for row in data:
            try:
                doc = frappe.get_doc("Salary Slip", row["name"])
                if doc.docstatus == 1:
                    doc.cancel()
                doc.delete()
                frappe.db.commit()
            except Exception as e:
                print(str(str(counter) + "/" + str(length)) +
                      "====Failed ====" + str(row["employee"]))
                frappe.db.sql(
                    "update slips set `status` = %s where employee = %s ", (str(e), row["employee"]))
                print("Error========"+str(e))
            counter += 1
        print("========================Finished=========================")


@frappe.whitelist()
def get_next_workflow_role(current_state, document_type):
    try:
        workflow_name = frappe.db.get_value(
            "Workflow", {"document_type": document_type, "is_active": 1}, "workflow_name")
        allowd_for_approve = frappe.db.get_all("Workflow Transition", filters={"parent": workflow_name, "state": current_state}, fields=[
            "allowed"], group_by="allowed", order_by="allowed", pluck="allowed")
        return allowd_for_approve
    except Exception as ex:
        frappe.log_error(frappe.get_traceback(),
                         "get_next_workflow_role:utils")
        return False


def get_dates_diff_in_month(d1, d2):
    # convert string to date object
    start_date = datetime.strptime(d1, '%Y-%m-%d')
    end_date = datetime.strptime(d2, '%Y-%m-%d')

    # Get the relativedelta between two dates
    delta = relativedelta.relativedelta(end_date, start_date)

    # get months difference
    res_months = delta.months + (delta.years * 12)
    print('Total Months between two dates is:', res_months)
    return res_months


def get_additional_salaries(employee, start_date, end_date, component_type):
    from frappe.query_builder import Criterion

    comp_type = "Earning" if component_type == "earnings" else "Deduction"

    additional_sal = frappe.qb.DocType("Additional Salary")
    component_field = additional_sal.salary_component.as_("component")
    overwrite_field = additional_sal.overwrite_salary_structure_amount.as_(
        "overwrite")

    additional_salary_list = (
        frappe.qb.from_(additional_sal)
        .select(
            additional_sal.name,
            component_field,
            additional_sal.type,
            additional_sal.amount,
            additional_sal.is_recurring,
            overwrite_field,
            additional_sal.deduct_full_tax_on_selected_payroll_date,
            additional_sal.from_over_time,
        )
        .where(
            (additional_sal.employee == employee)
            & (additional_sal.docstatus == 1)
            & (additional_sal.type == comp_type)
        )
        .where(
            Criterion.any(
                [
                    Criterion.all(
                        [  # is recurring and additional salary dates fall within the payroll period
                            additional_sal.is_recurring == 1,
                            additional_sal.from_date <= end_date,
                            additional_sal.to_date >= end_date,
                            # start_date <= additional_sal.from_date,
                        ]
                    ),
                    Criterion.all(
                        [  # is not recurring and additional salary's payroll date falls within the payroll period
                            additional_sal.is_recurring == 0,
                            additional_sal.payroll_date[start_date:end_date],
                        ]
                    ),
                ]
            )
        )
        .run(as_dict=True)
    )

    additional_salaries = []
    components_to_overwrite = []
    # print("additional_salary_list======================"+str(additional_salary_list))
    for d in additional_salary_list:
        # if d.overwrite:
        # if d.component in components_to_overwrite:
        #     frappe.throw(
        #         _(
        #             "Multiple Additional Salaries with overwrite property exist for Salary Component {0} between {1} and {2}."
        #         ).format(frappe.bold(d.component), start_date, end_date),
        #         title=_("Error"),
        #     )
        #
        # components_to_overwrite.append(d.component),,,,

        additional_salaries.append(d)

    return additional_salaries


def save_emps():
    data = frappe.db.sql("""
			select *
				from `tabEmployee`
		""", as_dict=True)
    if data:
        length = len(data)
        counter = 1
        print("========================Starting=========================")
        for row in data:
            doc = frappe.get_doc("Employee", row["name"])
            doc.employment_type = "Full Time"
            try:
                doc.save()
                frappe.db.commit()
                print(str(str(counter) + "/" + str(length)) +
                      "====Failed ====" + str(row["name"]))
            except Exception as e:
                print("Error========"+str(e))
        print("========================Finished=========================")


@frappe.whitelist(allow_guest=True)
def add_chart_of_account():
    accounts = frappe.db.sql("""
            select *
                from accounts
            """, as_dict=True)
    if accounts:
        length = len(accounts)
        counter = 1
        print("========================Starting=========================")
        for row in accounts:
            try:
                if not frappe.db.get_value("Account", filters={"account_name": row.account_name, "company": "SAT"}):
                    acc = frappe.new_doc("Account")
                    acc.account_name = row.account_name
                    acc.parent_account = frappe.db.get_value(
                        "Account", filters={"account_name": row.parent_account, "company": "SAT"})
                    acc.company = "SAT"
                    acc.is_group = row.is_group
                    acc.account_currency = "SAR"
                    acc.root_type = row.root_type
                    acc.account_type = row.account_type
                    acc.insert(ignore_permissions=True)
                    frappe.db.commit()
                    print(str(str(counter) + "/" + str(length)) +
                          "====Success ====" + str(row["account_name"]))
            except Exception as e:
                print("Error========"+str(e))
                break
        print("========================Finished=========================")


@frappe.whitelist(allow_guest=True)
def update_accounts():
    accounts = frappe.db.get_all(
        "Account", filters={"company": "SAT"}, fields="*")

    length = len(accounts)
    counter = 1
    print("========================Starting=========================")
    for account in accounts:
        doc = frappe.get_doc("Account", account.name)
        doc.account_currency = "SAR"
        try:
            doc.save()
            frappe.db.commit()
            print(str(str(counter) + "/" + str(length)) +
                  "====Success ====" + str(account["account_name"]))
        except Exception as e:
            pass
        counter += 1
    print("========================Finished=========================")


@frappe.whitelist(allow_guest=True)
def get_leaves(manager, page_no=1, posting_date="", leave_type="", leave_status="", employee="", search_txt="", page_limit=10, from_date="", to_date=""):
    page_limit = cint(page_limit)
    or_filters, filters = {}, {}
    limit_page_length = cint(page_no) * page_limit
    page_no = cint(page_no) - 1
    limit_start = cint(page_no) * page_limit

    manager_mail = frappe.db.get_value(
        "Employee", {"name": manager}, ["user_id"])
    logeduser = frappe.get_doc("User", {"name": manager_mail})
    linemanager = False
    for role in logeduser.roles:
        if (role.role == "Line Manager"):
            linemanager = True
    arry = ''
    dsntion = ''
    Employees = []
    if linemanager == True:
        permitted_dept = frappe.db.sql(
            f"""SELECT for_value FROM `tabUser Permission` WHERE user='{manager_mail}' AND allow='Department';""",
            as_dict=True)
        permitted_designations = frappe.db.sql(
            f"""SELECT for_value FROM `tabUser Permission` WHERE user='{manager_mail}' AND allow='Designation';""",
            as_dict=True)

        print(f">>>>>>>>>>>>>>>>>> len(permitted_dept): {len(permitted_dept)}")
        print(
            f">>>>>>>>>>>>>>>>>> len(permitted_designations): {len(permitted_designations)}")

        if (len(permitted_dept) > 0):
            arry = '('
            li = permitted_dept[-1:][0]
            for d in permitted_dept:

                if (d.for_value == li.for_value):
                    arry = arry + "'" + d.for_value + "')"
                else:
                    arry = arry + "'" + d.for_value + "'" + ","
            emp1 = frappe.db.sql(
                f""" SELECT name ,employee_number,employee_name,designation,(select health_insurance_grade from `tabEmployee contract` where employee = E.name and health_insurance=1 order by contract_start_date limit 1) health_insurance_grade  FROM tabEmployee E WHERE  department in {arry}  ;""",
                as_dict=True)

            Employees += emp1

        if (len(permitted_designations) > 0):
            dsntion = '('
            ld = permitted_designations[-1:][0]
            for i in permitted_designations:

                if (i.for_value == ld.for_value):
                    dsntion = dsntion + "'" + i.for_value + "')"
                else:
                    dsntion = dsntion + "'" + i.for_value + "'" + ","
            emp2 = frappe.db.sql(
                f""" SELECT name ,employee_number,employee_name,designation,(select health_insurance_grade from `tabEmployee contract` where employee = E.name and health_insurance=1 order by contract_start_date limit 1) health_insurance_grade FROM tabEmployee E WHERE designation in {dsntion}   ;""",
                as_dict=True)
            print(f">>>>> emp2: {emp2}")
            Employees += emp2

    if manager:
        if Employees:
            reports_to = [x["name"] for x in Employees]
            filters = {"employee": ["in", reports_to]}
        else:
            return _("There is no Employee/s report to such Manager")

    if posting_date:
        filters["posting_date"] = getdate(posting_date)

    if leave_type:
        filters["leave_type"] = leave_type

    if employee:
        filters["employee"] = employee

    if leave_status == "Pending":
        filters["workflow_state"] = "Created by Employee"
    elif leave_status == "Approved":
        filters["workflow_state"] = [
            "in", ('Approved', 'Approved by HR', 'Approved by Line Manager')]
    elif leave_status == "Rejected":
        filters["workflow_state"] = [
            "in", ('Rejected by Line Manager', 'Rejected by HR')]

    if from_date and to_date:
        filters["from_date"] = (">=", from_date)
        filters["to_date"] = ("<=", to_date)
    elif from_date and not to_date:
        filters["from_date"] = (">=", from_date)
    elif to_date and not from_date:
        filters["to_date"] = ("<=", to_date)

    selected_fields = ["name", "employee", "from_date", "to_date", "leave_type", "workflow_state",
                       "posting_date", "employee_name", "leave_approver", "creation as creation_date"]

    emp_leaves = frappe.db.get_all("Leave Application", filters=filters, fields=selected_fields,
                                   order_by="creation desc",
                                   limit=page_limit, limit_start=limit_start, limit_page_length=limit_page_length)
    total_leaves = []
    if emp_leaves:
        if search_txt:
            # search_txt = search_txt.lower()
            for item in emp_leaves:
                if item["employee_name"].__contains__(search_txt) or item["workflow_state"].__contains__(search_txt) or item["leave_type"].__contains__(search_txt) or item["employee"].__contains__(search_txt):
                    total_leaves.append(item)
        else:
            total_leaves = emp_leaves

    pages = {}
    total_pages = 0

    leaves_no = frappe.db.get_all(
        "Leave Application", filters=filters, fields=selected_fields, order_by="creation desc")
    leaves = []
    if leaves_no:
        if search_txt:
            for item in leaves_no:
                if item["employee_name"].__contains__(search_txt) or item["workflow_state"].__contains__(search_txt) or \
                        item["leave_type"].__contains__(search_txt) or item["employee"].__contains__(search_txt):
                    leaves.append(item)
        else:
            leaves = leaves_no

    if leaves:
        total_pages = frappe.utils.ceil(len(leaves) / cint(page_limit))
        pages = {"total_pages": total_pages, "current_page": page_no+1}

    total_leaves.append(pages)
    return total_leaves


@frappe.whitelist(allow_guest=True)
def calculate_employee_salary_details(employee):
    month_date = get_first_day(getdate())
    salary = []
    json_data = {}
    start_date = get_first_day(month_date)
    end_date = get_last_day(month_date)

    precision = get_currency_precision() or 2
    try:
        data = get_data_for_eval(employee, month_date)
    except Exception as e:
        return return_response("Fail", str(e), 417)

    salary_structure_assignment = check_salary_structure_assignment(
        employee, month_date)
    if not salary_structure_assignment:
        msg = _(
            "You need to Assign Salary Structure First to Calculate Employee Deductions")
        frappe.throw(
            msg
        )
    _salary_structure_doc = frappe.get_doc(
        "Salary Structure", salary_structure_assignment.salary_structure).as_dict()

    earnigns = calculate_all_component_type(
        employee, _salary_structure_doc, data, "earnings", start_date, end_date)
    deductions = calculate_all_component_type(
        employee, _salary_structure_doc, data, "deductions", start_date, end_date)

    # salary.append(earnigns)
    # salary.append(deductions)
    gross_pay, net_pay = 0, 0
    if earnigns:
        for row in earnigns:
            if "amount" in row:
                gross_pay += flt(row["amount"])

    json_data["gross_pay"] = gross_pay

    if earnigns:
        for row in deductions:
            if "amount" in row:
                gross_pay -= flt(row["amount"])
        net_pay = gross_pay

    json_data["net_pay"] = net_pay
    json_data["total_in_words"] = money_in_words(
        net_pay, erpnext.get_default_currency())
    json_data["bank_iban"] = frappe.db.get_value(
        "Employee", employee, "bank_ac_no")
    json_data["earnings"] = earnigns
    json_data["deductions"] = deductions
    return json_data


def calculate_all_component_type(employee, _salary_structure_doc, data, component_type, start_date, end_date):
    details = {}
    components = []
    total_amount = 0
    for struct_row in _salary_structure_doc[component_type]:

        json_data = {}
        amount = eval_condition_and_formula(struct_row, data)
        if (
                amount
                or (struct_row.amount_based_on_formula and amount is not None)
                and struct_row.statistical_component == 0
        ):
            json_data["salary_component"] = struct_row.salary_component
            json_data["amount"] = amount
            components.append(json_data)
            total_amount += amount
    additional_salaries = get_additional_salaries(
        employee, start_date=start_date, end_date=end_date, component_type=component_type)
    for additional_salary in additional_salaries:
        additional = {}
        if additional_salary.component in ("Housing", "Phone Allowance", "Responsibility Allowance", "Nature of work Allowance", "Fuel Allowance", "Transportation"):
            additional["salary_component"] = additional_salary.component
            additional["amount"] = additional_salary.amount
            total_amount += flt(additional_salary.amount)
            components.append(additional)
    components.append({"total_"+str(component_type): total_amount})
    # details[component_type] = components
    return components


@frappe.whitelist(allow_guest=True)
def check_back_from_leave(leave_name, joining_date):
    leave_doc = frappe.get_doc("Leave Application", leave_name)
    if leave_doc.docstatus == 0:
        return _("Leave Application Draft and is Not Submitted ")
    elif leave_doc.docstatus == 2:
        return _("Leave Application is Not Cancelled ")

    try:
        joining_date = getdate(joining_date)
    except Exception as e:
        return str(e)

    if getdate(leave_doc.to_date) >= joining_date:
        msg = _("Joining Date Should Be Greater Than to Date for Leave Application")
        return msg
    elif joining_date > getdate(leave_doc.to_date):
        exceeded_days = date_diff(joining_date, getdate(leave_doc.to_date))
        return {"exceeded_days": exceeded_days}


@frappe.whitelist(allow_guest=True)
def get_bfl_for_managers(manager, page_no=1, leave_status="", employee="", search_txt="", page_limit=10, from_date="", to_date=""):
    page_limit = cint(page_limit)
    or_filters, filters = {}, {}
    limit_page_length = cint(page_no) * page_limit  # 1*10
    page_no = cint(page_no) - 1
    limit_start = cint(page_no) * page_limit  # 1*10

    linemanager = False
    manager_mail = frappe.db.get_value(
        "Employee", {"name": manager}, ["user_id"])
    logeduser = frappe.get_doc("User", {"name": manager_mail})
    for role in logeduser.roles:
        if (role.role == "Line Manager"):
            linemanager = True
    Employees = all_employee = []
    if (linemanager == True):
        from ptco_hr.utils.api_Service import get_all_employees
        all_employee = get_all_employees(manager)

    if manager:
        if all_employee:
            # reports_to = [x["name"] for x in Employees]
            filters = {"employee": ["in", all_employee]}
        else:
            return _("There is no Employee/s report to such Manager")

    if employee:
        filters["employee"] = employee

    filters["docstatus"] = ("!=", "2")
# "workflow_state"
    selected_fields = ["name", "employee", "from_date", "to_date", "leave_type",
                       "posting_date", "employee_name", "creation as creation_date", "exceeded_days", "joining_date", "designation", "department"]

    if from_date and to_date:
        filters["from_date"] = (">=", from_date)
        filters["to_date"] = ("<=", to_date)
    elif from_date and not to_date:
        filters["from_date"] = (">=", from_date)
    elif to_date and not from_date:
        filters["to_date"] = ("<=", to_date)

    emp_bfls = frappe.db.get_all("Back From Leave", filters=filters, fields=selected_fields,
                                 order_by="creation desc",
                                 # limit=page_limit, limit_start=limit_start, limit_page_length=limit_page_length
                                 )
    total_bfls = []
    if emp_bfls:
        if search_txt:
            # search_txt = search_txt.lower()
            for item in emp_bfls:
                if item["employee_name"].__contains__(search_txt) or item["workflow_state"].__contains__(search_txt) or \
                        item["leave_type"].__contains__(search_txt) or item["employee"].__contains__(search_txt):
                    # item['actions']=get_back_from_leave_actions(item["name"])
                    total_bfls.append(item)
        else:
            total_bfls = emp_bfls

    total_emp_bfls = []
    for item in range(limit_start, limit_page_length):
        try:
            from_date, to_date = frappe.db.get_value("Leave Allocation", {"employee": total_bfls[item]['employee'], "leave_type": total_bfls[item]['leave_type']}, [
                                                     "from_date", "to_date"], order_by="from_date desc")
            # balance = get_leave_balance_on(total_bfls[item]['employee'], total_bfls[item]['leave_type'], today())
            balance = get_leave_day_details(
                total_bfls[item]['employee'], today(), total_bfls[item]['leave_type'])
            branch = frappe.db.get_value(
                "Employee", total_bfls[item]['employee'], "branch")

            total_bfls[item]['branch'] = branch
            total_bfls[item]['leave_balance'] = balance
            total_bfls[item]['actions'] = get_back_from_leave_actions(
                total_bfls[item]["name"])
            total_emp_bfls.append(total_bfls[item])
        except Exception as ex:
            continue

    total_pages = math.ceil(len(total_bfls) / cint(page_limit))
    pages = {"total_pages": total_pages, "current_page": page_no + 1}

    total_emp_bfls.append(pages)
    return total_emp_bfls


def get_leave_day_details(employee, date, leave_type):
    allocation_records = get_leave_allocation_records(
        employee, date, leave_type)
    leave_allocation = {}
    dataary = []
    # x=1
    for d in allocation_records:
        allocation = allocation_records.get(d, frappe._dict())
        remaining_leaves = get_leave_balance_on(
            employee, d, date, to_date=allocation.to_date, consider_all_leaves_in_the_allocation_period=True
        )

        end_date = allocation.to_date
        leaves_taken = get_leaves_for_period(
            employee, d, allocation.from_date, end_date) * -1
        leaves_pending = get_leaves_pending_approval_for_period(
            employee, d, allocation.from_date, end_date
        )
        expired_leaves = allocation.total_leaves_allocated - \
            (remaining_leaves + leaves_taken)

        leave_allocation[d] = {
            "type": d,
            "remaining_leaves": remaining_leaves,
        }
    if leave_allocation:
        return leave_allocation[leave_type]["remaining_leaves"]


def get_back_from_leave_actions(bfl_name):
    actions = frappe.db.get_all("Back From Leave Actions", filters={"parent": bfl_name}, fields=[
                                "action", "current_allocation", "days", "leave_approver", "leave_approver_name", "applied_month"])
    return actions


@frappe.whitelist(allow_guest=True)
def get_leaves_for_period(
        employee, leave_type, from_date, to_date, skip_expired_leaves: bool = True
) -> float:
    leave_entries = get_leave_entries(employee, leave_type, from_date, to_date)
    leave_days = 0

    for leave_entry in leave_entries:
        inclusive_period = leave_entry.from_date >= getdate(
            from_date
        ) and leave_entry.to_date <= getdate(to_date)

        if inclusive_period and leave_entry.transaction_type == "Leave Encashment":
            leave_days += leave_entry.leaves

        elif (
                inclusive_period
                and leave_entry.transaction_type == "Leave Allocation"
                and leave_entry.is_expired
                and not skip_expired_leaves
        ):
            leave_days += leave_entry.leaves

        elif leave_entry.transaction_type == "Leave Application":
            if leave_entry.from_date < getdate(from_date):
                leave_entry.from_date = from_date
            if leave_entry.to_date > getdate(to_date):
                leave_entry.to_date = to_date

            half_day = 0
            half_day_date = None
            # fetch half day date for leaves with half days
            if leave_entry.leaves % 1:
                half_day = 1
                half_day_date = frappe.db.get_value(
                    "Leave Application", {
                        "name": leave_entry.transaction_name}, ["half_day_date"]
                )

            leave_days += (
                get_number_of_leave_days(
                    employee,
                    leave_type,
                    leave_entry.from_date,
                    leave_entry.to_date,
                    half_day,
                    half_day_date,
                    holiday_list=leave_entry.holiday_list,
                )
                * -1
            )

    return leave_days


@frappe.whitelist(allow_guest=True)
def get_leaves_pending_approval_for_period(
        employee, leave_type: str, from_date, to_date
) -> float:
    """Returns leaves that are pending for approval"""
    leaves = frappe.get_all(
        "Leave Application",
        filters={"employee": employee,
                 "leave_type": leave_type, "status": "Open"},
        or_filters={
            "from_date": ["between", (from_date, to_date)],
            "to_date": ["between", (from_date, to_date)],
        },
        fields=["SUM(total_leave_days) as leaves"],
    )[0]
    return leaves["leaves"] if leaves["leaves"] else 0.0


@frappe.whitelist(allow_guest=True)
def get_leave_entries(employee, leave_type, from_date, to_date):
    """Returns leave entries between from_date and to_date."""
    return frappe.db.sql(
        """
		SELECT
			employee, leave_type, from_date, to_date, leaves, transaction_name, transaction_type, holiday_list,
			is_carry_forward, is_expired
		FROM `tabLeave Ledger Entry`
		WHERE employee=%(employee)s AND leave_type=%(leave_type)s
			AND docstatus=1
			AND (leaves<0
				OR is_expired=1)
			AND (from_date between %(from_date)s AND %(to_date)s
				OR to_date between %(from_date)s AND %(to_date)s
				OR (from_date < %(from_date)s AND to_date > %(to_date)s))
	""",
        {"from_date": from_date, "to_date": to_date,
            "employee": employee, "leave_type": leave_type},
        as_dict=1,
    )


@frappe.whitelist(allow_guest=True)
def get_number_of_leave_days(
        employee,
        leave_type: str,
        from_date,
        to_date,
        half_day: Optional[int] = None,
        half_day_date: Optional[str] = None,
        holiday_list: Optional[str] = None,
) -> float:
    """Returns number of leave days between 2 dates after considering half day and holidays
        (Based on the include_holiday setting in Leave Type)"""
    number_of_days = 0
    if cint(half_day) == 1:
        if getdate(from_date) == getdate(to_date):
            number_of_days = 0.5
        elif half_day_date and getdate(from_date) <= getdate(half_day_date) <= getdate(to_date):
            number_of_days = date_diff(to_date, from_date) + 0.5
        else:
            number_of_days = date_diff(to_date, from_date) + 1

    else:
        number_of_days = date_diff(to_date, from_date) + 1

    if not frappe.db.get_value("Leave Type", leave_type, "include_holiday"):
        number_of_days = flt(number_of_days) - flt(
            get_holidays(employee, from_date, to_date,
                         holiday_list=holiday_list)
        )
    return number_of_days


@frappe.whitelist()
def get_holidays(employee, from_date, to_date, holiday_list=None):
    """get holidays between two dates for the given employee"""
    if not holiday_list:
        holiday_list = get_holiday_list_for_employee(employee)

    holidays = frappe.db.sql(
        """select count(distinct holiday_date) from `tabHoliday` h1, `tabHoliday List` h2
		where h1.parent = h2.name and h1.holiday_date between %s and %s
		and h2.name = %s""",
        (from_date, to_date, holiday_list),
    )[0][0]

    return holidays


@frappe.whitelist(allow_guest=True)
def update_bfl_status(access_token, request_type, app_name, status):
    JWT_setting = frappe.get_doc("HRMS Settings").as_dict()
    JWT_Key = JWT_setting["jwt_api_secret_key"]
    decoded = jwt.decode(access_token, JWT_Key, algorithms=["HS256"])
    manager = decoded[('ID')]
    level = 2
    hr = 2
    manager_mail = frappe.db.get_value(
        "Employee", {"name": manager}, ["user_id"])

    logeduser = frappe.get_doc("User", {"name": manager_mail})
    # print(f">>>>>>>>>>>> logeduser: {logeduser}")

    # return logeduser
    if logeduser.get("name"):
        frappe.set_user(logeduser.get("name"))

    for role in logeduser.roles:
        if (role.role == "HR Manager"):
            hr = 0
        if (role.role == "Line Manager"):
            level = 1
    doc_status = ''
    leave_status = ''
    # if(hrmanager==True and linemanager==True) :
    # 	level=0
    # if(hrmanager==False and linemanager==True) :
    # 	level=1

    if (hr == 0):
        if (status == 'accept'):
            doc_status = 'Approved by HR'
            leave_status = 'Approved'
        else:
            doc_status = 'Rejected by HR'
            leave_status = 'Rejected'

    if ((level == 1 and hr != 0)):
        if (status == 'accept'):
            doc_status = 'Approved by Line Manager'
            leave_status = 'Approved'
        else:
            doc_status = 'Rejected by Line Manager'
            leave_status = 'Rejected'

    doctype = request_type
    if (level == 2 and hr == 2):
        return {'Faild': 'user has no manager or hr permission'}
    try:
        # frappe.set_user("Administrator")
        request = frappe.get_doc(doctype, app_name)
        request.db_set('status', leave_status)
        # request.db_set('workflow_state', doc_status)
        frappe.db.commit()
        # request.status	 = leave_status
        # request.workflow_state = doc_status
        request.save(ignore_permissions=True)
        request.submit()
        frappe.db.commit()
        return {'Success': 'Request status updated successfuly', 'doctype': doctype, 'name': app_name,
                'status': doc_status, 'employee_id': request.employee}

    except:
        print(frappe.get_traceback())
        return {'Faild': 'Some error happend'}

# not found


@frappe.whitelist(allow_guest=True)
def get_employees_for_manager(manager):
    linemanager = False
    manager_mail = frappe.db.get_value(
        "Employee", {"name": manager}, ["user_id"])
    logeduser = frappe.get_doc("User", {"name": manager_mail})

    for role in logeduser.roles:
        if role.role == "Line Manager":
            linemanager = True

    if not linemanager:
        return []

    employee_filters = []
    from ptco_hr.utils.api_Service import get_all_employees
    all_employee = get_all_employees(manager)
    if len(all_employee):
        employee_filters = {"name": ["in", all_employee]}

    employees = []
    if employee_filters:
        employees = frappe.get_all(
            'Employee', filters=employee_filters, fields=['name'])
        employee_ids = [e['name'] for e in employees]
    else:
        employee_ids = []

    return employee_ids


@frappe.whitelist(allow_guest=True)
def get_employee_id_from_JWT_token(access_token):
    JWT_setting = frappe.get_doc("HRMS Settings").as_dict()
    JWT_Key = JWT_setting["jwt_api_secret_key"]
    decoded = jwt.decode(access_token, JWT_Key, algorithms=["HS256"])
    return decoded['ID']


@frappe.whitelist(allow_guest=True)
def add_employee_to_hcp(doc, method):
    try:
        hcp_settings = frappe.db.get_singles_dict("HCP Settings")
        HOSTINFO = hcp_settings.hostinfo
        AK = hcp_settings.ak
        SK = hcp_settings.sk
        SIGNATURE = generate_hcp_signature()
        API_VER = hcp_settings.api_ver

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json;charset=UTF-8',
            "X-Ca-Key": AK,
            "X-Ca-Signature": SIGNATURE
        }
        payload = json.dumps({
            "personCode": "2"+str(doc.name),
            "personFamilyName": doc.prefered_email,
            "personGivenName": doc.employee_name,
            "gender": doc.gender,
            "orgIndexCode": frappe.db.get_value("Department", doc.department, "custom_hcp_id") or 36,
            "remark": doc.employee_name,
            "phoneNo": doc.emergency_phone_number,
            # "email": doc.prefered_email,
            # "beginTime":"2024-08-22T15:00:00+08:00", # get_datetime(doc.date_of_joining),
            # "endTime": "2024-08-22T15:00:00+08:00" # get_datetime(doc.date_of_joining)  # add_years(get_datetime(doc.date_of_birth), 60)
        })
        response = requests.post(HOSTINFO,
                                 headers=headers,
                                 data=payload,
                                 verify=False
                                 )
        frappe.log_error(str(response.status_code), _(
            f"  'update_agent_limit' - Response Request - response reason {response.reason} - \n\n response.text {response.text}- \n\n request data - {payload}"))
        text = eval(response.text)
        # if text["code"] == "131":
        #     doc.db_set("hcp_id", doc.employee_name)
        if text["code"] == "0":
            doc.db_set("custom_hcp_id", text["data"])
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _(
            "Error in send agent Limit " + str(e)))


@frappe.whitelist(allow_guest=True)
def add_department_to_hcp(doc, method=None):
    if doc.custom_hcp_id:
        return
    try:
        hcp_settings = frappe.db.get_singles_dict("HCP Settings")
        HOSTINFO = "https://192.168.45.20/artemis/api/resource/v1/org/single/add"
        AK = hcp_settings.ak
        SK = hcp_settings.sk
        SIGNATURE = generate_hcp_signature()
        API_VER = hcp_settings.api_ver

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json;charset=UTF-8',
            "X-Ca-Key": AK,
            "X-Ca-Signature": SIGNATURE
        }
        payload = json.dumps({
            "orgName": doc.name,
            "parentIndexCode": "36"
        }
        )
        response = requests.post(HOSTINFO,
                                 headers=headers,
                                 data=payload,
                                 verify=False
                                 )
        frappe.log_error(str(response.status_code), _(
            f"  'update_agent_limit' - Response Request - response reason {response.reason} - \n\n response.text {response.text}- \n\n request data - {payload}"))
        text = eval(response.text)
        # if text["code"] == "131":
        #     doc.db_set("hcp_id", doc.employee_name)
        if text["code"] == "0":
            doc.db_set("custom_hcp_id", text["data"]["orgIndexCode"])
            frappe.db.commit()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _(
            "Error in send agent Limit " + str(e)))


def generate_hcp_signature():
    try:
        # api = '/artemis/api/resource/v1/cameras'
        api = '/artemis/api/common/v1/version'
        return make_signature(api)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(),
                         "generate_hcp_signature:utils")


def make_signature(api):
    line_break = "\n"
    http_method = "POST"
    accept = "application/json"
    content_type = "application/json;charset=UTF-8"
    # appkey = "27378018"
    appkey = "20673699"
    x_ca_key = appkey
    X_CA_KEY = "x-ca-key"
    X_CA_NONCE = "x-ca-nonce"
    x_ca_nonce = str(uuid.uuid4())
    X_CA_TIMESTAMP = "x-ca-timestamp"
    x_ca_timestamp = str(int(time.time() * 1000))
    # secretkey = "g5sHMqORfPFsC8To0X9P"
    secretkey = "7NFWG2bWEAbMfYr1ngkV"

    original_test = http_method + line_break + accept + line_break + content_type + line_break + \
        X_CA_KEY + ":" + appkey + line_break + X_CA_NONCE + ":" + x_ca_nonce + line_break + \
        X_CA_TIMESTAMP + ":" + x_ca_timestamp + line_break + api

    key = secretkey.encode('utf-8')
    message = original_test.encode('utf-8')

    signature = base64.b64encode(
        hmac.new(key, message, digestmod=sha256).digest())
    signature = str(signature, 'utf-8')

    return signature


def return_response(status, data, status_code, page_info=None):
    frappe.response['status'] = status
    frappe.response['data'] = data
    frappe.response['page_info'] = page_info
    frappe.response['status_code'] = status_code
    frappe.response['http_status_code'] = status_code
    return


def cancel_all_invoices_with_redundent_booking_id():
    sql ="""
            select I.`name` invoice ,T.invoice_name
                from `tabPOS Invoice` I
                    left JOIN
                    tabTicket T
                    on I.`name` = T.invoice_name
                    where T.invoice_name is NULL
                    and I.docstatus=1
      """
    data =  frappe.db.sql(sql,as_dict=True)
    if data:
        print("==========================Starting=============================")
        counter = 1
        length = len(data)

        for invoice in data:
            try:
                doc = frappe.get_doc("POS Invoice",invoice["invoice"])
                doc.cancel()
                frappe.db.commit()
                print(str(str(counter) + "/" + str(length)) + "====Succedded ====" + str(invoice["invoice"]))
                counter += 1
            except Exception as e:
                print("===================" + str(e))
        print("==========================Finished=============================")



def delete_all_invoices_with_redundent_booking_id():
    sql ="""
            select I.`name` invoice ,T.invoice_name
                from `tabPOS Invoice` I
                    left JOIN
                    tabTicket T
                    on I.`name` = T.invoice_name
                    where T.invoice_name is NULL
                    and I.docstatus=2
      """
    data =  frappe.db.sql(sql,as_dict=True)
    if data:
        print("==========================Starting=============================")
        counter = 1
        length = len(data)
        for invoice in data:
            try:
                doc = frappe.get_doc("POS Invoice",invoice["invoice"])
                # doc.cancel()
                frappe.delete_doc_if_exists("POS Invoice",invoice["invoice"])
                frappe.db.commit()
                print(str(str(counter) + "/" + str(length)) + "====Succedded ====" + str(invoice["invoice"]))
                counter += 1
            except Exception as e:
                print("===================" + str(e))
        print("==========================Finished=============================")


def encode_pos_invoices_booking_id():
    sql ="""
            select *
                from `tabPOS Invoice`
                        where booking_id_ is not NULL
      """
    data =  frappe.db.sql(sql,as_dict=True)
    if data:
        print("==========================Starting=============================")
        counter = 1
        length = len(data)
        for invoice in data:
            try:
                doc = frappe.get_doc("POS Invoice",invoice["name"])
                hashed_output = hash_string_with_limit(invoice["booking_id_"])
                doc.db_set("booking_id",hashed_output)
                frappe.db.commit()
                print(str(str(counter) + "/" + str(length)) + "====Succedded ====" + str(invoice["name"]))
                counter += 1
            except Exception as e:
                print("Error===================" + str(e))
        print("==========================Finished=============================")


def encode_sales_invoices_booking_id():
    sql ="""
            select *
                from `tabSales Invoice`
                        where booking_id is not NULL
      """
    data =  frappe.db.sql(sql,as_dict=True)
    if data:
        print("==========================Starting=============================")
        counter = 1
        length = len(data)
        for invoice in data:
            try:
                doc = frappe.get_doc("Sales Invoice",invoice["name"])
                hashed_output = hash_string_with_limit(invoice["full_booking_id"])
                doc.db_set("booking_id",hashed_output)
                frappe.db.commit()
                print(str(str(counter) + "/" + str(length)) + "====Succedded ====" + str(invoice["name"]))
                counter += 1
            except Exception as e:
                print("Error===================" + str(e))
        print("==========================Finished=============================")

import hashlib

def hash_string_with_limit(input_string, length=20):
    # Use SHA-256 hashing algorithm
    sha256_hash = hashlib.sha256()

    # Update the hash object with the string (encoded in bytes)
    sha256_hash.update(input_string.encode('utf-8'))

    # Get the full hash (hexadecimal string)
    full_hash = sha256_hash.hexdigest()

    # Truncate the hash to the desired length
    return full_hash[:length]


# # Example usage:
# input_string = "Your string to hash"
# desired_length = 16  # You can set the limit here
# hashed_output = hash_string_with_limit(input_string, desired_length)
# 
# print(hashed_output)  # Output will be limited to the specified length (16 characters here)

# from ptco_hr.utils.finance_api import enque_online_sales , enqueu_create_agent_invoice
def migrate_all_json_files_and_get_invoices():
    all_logs = frappe.db.get_all("Finance Log File", filters={"posting_date": getdate()},fields=["name"],order_by="name")
    if all_logs:
        for row in all_logs:
            continue





def custom_log_error(title=None, message=None, reference_doctype=None, reference_name=None, *, defer_insert=False):
	"""Log error to Error Log"""
	from frappe.monitor import get_trace_id
	from frappe.utils.sentry import capture_exception

	traceback = None
	if message:
		if "\n" in title:  # traceback sent as title
			traceback, title = title, message
		else:
			traceback = message

	title = title or "Error"
	traceback = frappe.as_unicode(traceback or frappe.get_traceback(with_context=True))

	if not frappe.db:
		print(f"Failed to log error in db: {title}")
		return

	trace_id = get_trace_id()
	error_log = frappe.get_doc(
		doctype="Custom Log Error",
		error=traceback,
		method=title,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		trace_id=trace_id,
	)

	# Capture exception data if telemetry is enabled
	capture_exception(message=f"{title}\n{traceback}")

	if frappe.flags.read_only or defer_insert:
		error_log.deferred_insert()
	else:
		return error_log.insert(ignore_permissions=True)

