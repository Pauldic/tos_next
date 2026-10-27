import frappe

no_cache = 1


def get_context(context):
    # The frontend reads these as globals on `window`. frappe-ui sends csrf_token with every request.
    # site_name and socketio_port let the 3D yard connect to realtime.
    print("\n\n>>>>>>>>>>>>>> ", {
        "csrf_token": frappe.sessions.get_csrf_token(),
        "user": frappe.session.user,
        "site_name": frappe.local.site,
        "socketio_port": frappe.conf.get("socketio_port") or 9000,
    })

    context.boot = {
        "csrf_token": frappe.sessions.get_csrf_token(),
        "user": frappe.session.user,
        "site_name": frappe.local.site,
        "socketio_port": frappe.conf.get("socketio_port") or 9000,
    }
