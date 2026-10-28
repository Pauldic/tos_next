1. Copy the files over apps/tos_next (frontend/src/... and tos_next/...), restart bench, rebuild the frontend.
2. In tos_next/hooks.py add (or merge into an existing role_home_page):
     role_home_page = {"Carrier Portal User": "tos/portal"}
3. Make a carrier login:
     bench --site tos.test execute tos_next.setup.portal_user.create --kwargs '{"email": "dispatch@acme.test", "carrier": "<carrier name>", "password": "ChangeMe-123"}'
4. Sign in as that user at /tos/portal. Check: they see only their carrier's trucks, drivers and appointments.
