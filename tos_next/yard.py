"""Yard placement rules. The only code that changes a container's position.

20 ft containers use one bay slot. 40 ft and 45 ft containers use two adjacent bays
in the same row: an odd "anchor" bay and the next even bay. A 40 ft container is only
placed on an anchor, both stacks must be the same height, and both heights rise by one.
"""
import frappe
from frappe import _

POSITION_FLAG = "meridian_position_update"


def slot_span(container_type: str) -> int:
    return frappe.get_cached_value("Container Type", container_type, "slot_span") or 1


def footprint(stack: str, span: int) -> list[str]:
    """Stacks a container would occupy if its anchor is `stack`. Anchor first."""
    d = frappe.db.get_value("Yard Stack", stack, ["is_forty_anchor", "pair_stack"], as_dict=True)
    if not d:
        frappe.throw(_("Yard Stack {0} does not exist.").format(stack))
    if span == 1:
        return [stack]
    if not d.is_forty_anchor or not d.pair_stack:
        frappe.throw(_("A 40 ft container needs an odd (anchor) bay with a neighbour. {0} is not one.").format(stack))
    return [stack, d.pair_stack]


def check_can_place(stack: str, container_type: str, lock: bool = False) -> tuple[list[str], int]:
    """Return (stacks, tier) the container would take, or throw why it cannot go there."""
    span = slot_span(container_type)
    names = footprint(stack, span)
    rows = []
    for n in sorted(names):  # fixed order avoids deadlocks
        rows.append(frappe.db.get_value(
            "Yard Stack", n, ["name", "tier_count", "max_tier", "is_blocked", "terminal"],
            as_dict=True, for_update=lock))
    for r in rows:
        if not r:
            frappe.throw(_("Paired stack is missing. Generate stacks for the block again."))
        if r.is_blocked:
            frappe.throw(_("Stack {0} is blocked.").format(r.name))
    counts = {r.tier_count for r in rows}
    if len(counts) > 1:
        frappe.throw(_("A 40 ft container needs both slots at the same height. Stacks {0} are at different heights.").format(", ".join(names)))
    tier = counts.pop() + 1
    limit = min(r.max_tier for r in rows)
    if tier > limit:
        frappe.throw(_("Stack {0} is full ({1} tiers).").format(names[0], limit))
    return names, tier


def get_blockers(container) -> list[str]:
    """Containers sitting above this one, highest first."""
    if not container.yard_stack:
        return []
    stacks = [s for s in (container.yard_stack, container.partner_stack) if s]
    rows = frappe.db.sql("""select name from `tabContainer` where tier > %s and (yard_stack in %s or partner_stack in %s)
           order by tier desc""", (container.tier, tuple(stacks), tuple(stacks)))
    return [r[0] for r in rows]


def _remove(container):
    names = [s for s in (container.yard_stack, container.partner_stack) if s]
    for n in sorted(names):
        row = frappe.db.get_value("Yard Stack", n, ["tier_count"], as_dict=True, for_update=True)
        if row.tier_count != container.tier:
            frappe.throw(_("{0} is not on top of stack {1}. Move the containers above it first.").format(container.name, n))
    for n in names:
        frappe.db.set_value("Yard Stack", n, "tier_count", container.tier - 1, update_modified=False)


def log_movement(container, movement_type, from_stack=None, from_tier=None, to_stack=None, to_tier=None,
                 source_doctype=None, source_name=None, equipment=None):
    return frappe.get_doc({
        "doctype": "Container Movement",
        "container": container.name,
        "terminal": container.terminal,
        "movement_type": movement_type,
        "from_stack": from_stack, "from_tier": from_tier,
        "to_stack": to_stack, "to_tier": to_tier,
        "source_doctype": source_doctype, "source_name": source_name,
        "equipment": equipment,
        "performed_by": frappe.session.user,
        "timestamp": frappe.utils.now_datetime(),
    }).insert(ignore_permissions=True)


def move_container(container_name, to_stack=None, movement_type="Yard Move",
                   source_doctype=None, source_name=None, equipment=None):
    """Take a container off its stack (if any) and put it on `to_stack` (if given).

    Runs in the caller's transaction, so a failure leaves nothing half-done.
    """
    c = frappe.get_doc("Container", container_name)
    if c.is_on_hold and movement_type in ("Yard Move", "Gate Out", "Vessel Load"):
        frappe.throw(_("{0} is on hold and cannot be moved.").format(c.name))

    from_stack, from_tier = c.yard_stack, c.tier
    if c.yard_stack:
        _remove(c)

    if to_stack:
        names, tier = check_can_place(to_stack, c.container_type, lock=True)
        for n in names:
            frappe.db.set_value("Yard Stack", n, "tier_count", tier, update_modified=False)
        c.yard_stack = names[0]
        c.partner_stack = names[1] if len(names) > 1 else None
        c.tier = tier
    else:
        c.yard_stack = None
        c.partner_stack = None
        c.tier = None

    frappe.flags[POSITION_FLAG] = True
    try:
        c.save(ignore_permissions=True)
    finally:
        frappe.flags[POSITION_FLAG] = False

    log_movement(c, movement_type, from_stack, from_tier, c.yard_stack, c.tier,
                 source_doctype, source_name, equipment)
    return c


def suggest_target(container_name: str) -> str | None:
    """Nearest suitable stack: same block first, lowest stack first, matching cargo type."""
    c = frappe.get_doc("Container", container_name)
    span = slot_span(c.container_type)
    cur = frappe.db.get_value("Yard Stack", c.yard_stack, ["yard_block", "bay", "row_no"], as_dict=True) if c.yard_stack else None
    stacks = frappe.get_all("Yard Stack", filters={"terminal": c.terminal, "is_blocked": 0},
        fields=["name", "yard_block", "bay", "row_no", "tier_count", "max_tier", "is_forty_anchor", "pair_stack"])
    by_name = {s.name: s for s in stacks}
    block_types = {b.name: b.block_type for b in frappe.get_all("Yard Block", filters={"terminal": c.terminal}, fields=["name", "block_type"])}
    wanted = {"Import": "Import", "Export": "Export", "Empty": "Empty", "Reefer": "Reefer"}.get(c.cargo_status)
    own = {c.yard_stack, c.partner_stack}
    best, best_score = None, None
    for s in stacks:
        if s.name in own:
            continue
        if span == 2:
            p = by_name.get(s.pair_stack) if s.is_forty_anchor else None
            if not p or p.name in own or p.tier_count != s.tier_count:
                continue
            limit = min(s.max_tier, p.max_tier)
        else:
            limit = s.max_tier
        if s.tier_count >= limit:
            continue
        score = s.tier_count * 10
        score += 0 if (cur and s.yard_block == cur.yard_block) else 100
        bt = block_types.get(s.yard_block)
        if wanted and bt not in (wanted, "Mixed"):
            score += 50
        if cur and s.yard_block == cur.yard_block:
            score += abs(s.bay - cur.bay) + abs(s.row_no - cur.row_no)
        if best_score is None or score < best_score:
            best, best_score = s.name, score
    return best
