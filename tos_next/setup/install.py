import frappe

ROLES = ['Terminal Admin', 'Yard Planner', 'Equipment Operator', 'Gate Clerk', 'Gate Supervisor', 'Appointment Planner', 'Carrier Portal User']


def after_install():
	create_roles()


def create_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 0 if role == "Carrier Portal User" else 1}).insert(ignore_permissions=True)
	frappe.db.commit()
