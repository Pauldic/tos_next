"""Create a carrier login and link it to its carrier (the link is a User Permission, which is what keeps it
to that carrier's data).

bench --site tos.test execute tos_next.setup.portal_user.create --kwargs '{"email": "dispatch@acme.test", "carrier": "<carrier name>", "password": "ChangeMe-123"}'
"""
import frappe


def create(email, carrier, password=None, first_name=None):
    if not frappe.db.exists("Carrier", carrier):
        frappe.throw(f"Carrier {carrier} does not exist.")
    if not frappe.db.exists("User", email):
        user = frappe.get_doc({
            "doctype": "User", "email": email, "first_name": first_name or email.split("@")[0],
            "user_type": "Website User", "send_welcome_email": 0, "enabled": 1,
            "new_password": password or frappe.generate_hash(length=14),
        })
        user.insert(ignore_permissions=True)
    user = frappe.get_doc("User", email)
    if "Carrier Portal User" not in [r.role for r in user.roles]:
        user.append("roles", {"role": "Carrier Portal User"})
        user.save(ignore_permissions=True)
    if not frappe.db.exists("User Permission", {"user": email, "allow": "Carrier", "for_value": carrier}):
        frappe.get_doc({"doctype": "User Permission", "user": email, "allow": "Carrier", "for_value": carrier,
                        "apply_to_all_doctypes": 1}).insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"{email} can sign in at /tos/portal and sees only carrier {carrier}.")
    return email
