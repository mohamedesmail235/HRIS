# Copyright (c) 2022, MiM and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class EmployeePenalties(Document):
    def on_submit(self):
        # self.apply_date = getdate()
        doc = frappe.get_doc("Employee", self.employee)
        doc.append("penalties_data", {
            "penalty_type": self.penalty_type,
            "penalty_date": self.penalty_date,
            "apply_date": self.apply_date,
            "penalty_reference": self.name
        })
        doc.save()
        frappe.db.commit()

    def on_cancel(self):
        self.delete_reference()

    def delete_reference(self):
        return frappe.db.sql("""
				delete from `tabEmployee Penalty`
					where penalty_reference = '{name}'
			""".format(name=self.name))
