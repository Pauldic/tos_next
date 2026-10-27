"""bench --site yoursite execute tos_next.setup.api_smoke.run"""
import frappe

from tos_next import api


def run():
    t = api.terminals()[0].name
    c = frappe.db.get_value("Container", {"status": "On Terminal", "yard_stack": ["is", "set"]}, ["name", "yard_stack"], as_dict=True)
    snap = api.yard_snapshot(t)
    cap = api.capacity_for_day(terminal=t)
    results = {
        "yard_snapshot": {k: len(v) for k, v in snap.items() if isinstance(v, list)},
        "stack_detail": len(api.stack_detail(c.yard_stack)["containers"]) if c else "no container",
        "search_container": len(api.search_container(c.name[:6], t)) if c else "no container",
        "work_queue": {k: len(v) for k, v in api.work_queue(t).items()},
        "gate_board": {"lanes": len(api.gate_board(t)["lanes"]), "queue": len(api.gate_board(t)["arrival_queue"])},
        "capacity_for_day": len(cap),
        "appointments_for_slot": len(api.appointments_for_slot(cap[0].name)) if cap else "no slots today",
        "kpis": api.kpis(t),
    }
    for k, v in results.items():
        print(f"{k}: {v}")
    return "ok"
