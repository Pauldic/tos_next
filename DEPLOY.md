# TOS Next: go-live checklist

Work top to bottom on a **staging copy first**, then repeat on production. Commands assume a standard bench and a site named `tos.example.com`; change the names.

## 1. Lock down permissions (once, in the repo)

```bash
cd ~/frappe-bench
python3 apps/tos_next/tools/harden_permissions.py apps/tos_next   # Carrier Portal User becomes read-only on Appointment, Truck, Driver
```
Optional but recommended: add `"track_changes": 1` to `driver.json` and `truck.json` so licence and block changes leave an audit trail.
Commit the change, then deploy it with step 3.

## 2. Server

- [ ] HTTPS is on (`bench setup lets-encrypt tos.example.com`). Camera scanning and the QR pass **need** HTTPS.
- [ ] Production mode: `sudo bench setup production <your-linux-user>` (nginx + supervisor, including the realtime process).
- [ ] `bench --site tos.example.com set-config developer_mode 0`
- [ ] Scheduler on: `bench --site tos.example.com scheduler enable` (late/no-show marking and override expiry depend on it).
- [ ] Staff accounts: strong passwords, and turn on Two Factor Auth in System Settings.
- [ ] Backups: a cron job running `bench --site tos.example.com backup --with-files`, copied off the server. **Restore one into staging once** to prove it works.

## 3. Deploy the app

```bash
cd ~/frappe-bench/apps/tos_next/frontend
npm ci && npm run build
cd ~/frappe-bench
bench --site tos.example.com migrate
bench build --app tos_next
bench --site tos.example.com clear-cache
sudo supervisorctl restart all
```
Then open `https://tos.example.com/tos` in a private window and sign in.

## 4. Master data (in this order)

1. Terminal (set `require_appointment`, tier limit, opening hours).
2. Shipping Lines (with colours), Container Types (20/40/45 ft, `slot_span`).
3. Yard Blocks (even bay counts), then **Generate Stacks** on each.
4. Gate Lanes: at least one In and one Out.
5. Equipment, with correct tier reach and 40 ft ability.
6. Slot Template, then **Generate Slots** (the audit wants slots for the next 7 days).
7. Do **not** run `demo_data.seed` on production. Use staging for demos and training.

## 5. People

| Role | Who |
|---|---|
| Terminal Admin | Terminal manager, IT |
| Yard Planner | Yard control room |
| Equipment Operator | Crane, RTG and reach stacker drivers. They use `/tos/ops` |
| Gate Clerk | Gate staff |
| Gate Supervisor | Gate shift leads. The only ones who approve overrides, besides admins |
| Appointment Planner | Customer service and planning |
| Carrier Portal User | Haulier logins only. Create with `tos_next.setup.portal_user.create` |

- [ ] Add `role_home_page = {"Carrier Portal User": "tos/portal"}` to `hooks.py` (if not there yet).
- [ ] Give each carrier a login with `portal_user.create`. That also creates the User Permission that keeps it to its own carrier.

## 6. Run the audit. Every line must be PASS or an understood WARN

```bash
bench --site tos.example.com execute tos_next.setup.audit.run
```
It checks roles, that carriers have no direct write rights, that every carrier login is tied to a carrier, the scheduler, the master data, and it **tries to break the carrier boundary** with two throwaway carriers and logins (rolled back afterwards; run it on staging first, and if you ever see leftovers they are named `AUDIT A/B ...`).

## 7. Smoke test with real roles (30 minutes)

1. Carrier login: add a truck and driver, book a slot, open the pass.
2. Gate clerk: Scan pass, start the visit, advance every step, let the truck through.
3. Planner: open 3D Yard, find the container, create a move order, assign it to a machine.
4. Operator on a phone: sign on, start, complete. Watch the container move in the yard.
5. Try a walk-in with no appointment: it must be refused. Request an override as a clerk, approve it as a *different* supervisor, and start the visit.
6. Second carrier login: confirm it sees none of the first carrier's data.
7. Switch every screen to dark mode and back.

## 8. Updating later

```bash
cd ~/frappe-bench/apps/tos_next && git pull
cd frontend && npm ci && npm run build && cd ../../..
bench --site tos.example.com migrate && bench build --app tos_next
bench --site tos.example.com clear-cache && sudo supervisorctl restart all
bench --site tos.example.com execute tos_next.setup.audit.run
```
Take a backup first, every time.

## Known gaps (be honest with your users)

- **Realtime** subscription (`doc_subscribe` on the Terminal room) was written from the Frappe docs and not run against v16. If the yard shows "Updating every 10 s" instead of "Live", the screens still work by polling; check the browser console and the nginx websocket proxy.
- **Strict ISO 6346**: the container number check only warns unless the strict site-config flag is set (its key was renamed by your project-wide replace; look in `container.py`).
- **No billing, vessel planning or customs** yet.
- **Carriers cannot delete** trucks or drivers (the terminal blocks them instead).
