"""Yard layout endpoints for the designer and the Desk. Call as /api/method/tos_next.api_layout.<name>.
Reading the live layout is part of tos_next.api.yard_snapshot."""
import frappe
from frappe import _

from tos_next import layout as yard_layout

DESIGNERS = ["Terminal Admin", "Yard Planner", "System Manager"]


@frappe.whitelist()
def create_draft(terminal):
    """A draft copy of the live layout (or of the automatic one, for a terminal that has never had a layout).
    If a draft already exists it is returned, so work is never overwritten."""
    frappe.only_for(DESIGNERS)
    existing = frappe.db.get_value("Yard Layout", {"terminal": terminal, "status": "Draft"}, "name")
    if existing:
        return existing
    live = yard_layout.published(terminal)
    if live:
        items = [yard_layout._row(i) for i in live.items]
        name, based_on = _("Draft from version {0}").format(live.version), live.name
    else:
        items = yard_layout.auto_items(yard_layout.active_blocks(terminal))
        name, based_on = _("First draft"), None
    doc = frappe.get_doc({
        "doctype": "Yard Layout", "terminal": terminal, "layout_name": name, "status": "Draft", "based_on": based_on,
        "base_surface": live.base_surface if live else "Default", "items": items,
        **({f: live.get(f) for f in BACKDROP} if live else {}),
    })
    doc.insert()
    frappe.db.commit()  # keep the draft even when the caller was a GET request, which Frappe would otherwise roll back
    return doc.name


PUBLISHERS = ["Terminal Admin", "System Manager"]
NUMBERS = ("x", "z", "rotation", "length", "width", "height")
BACKDROP = ["backdrop_image", "backdrop_x", "backdrop_z", "backdrop_width", "backdrop_rotation", "backdrop_opacity"]


def _blocks(terminal):
    g = yard_layout.geometry()
    out = []
    for b in yard_layout.active_blocks(terminal):
        w, d = yard_layout.block_size(b, g)
        out.append(dict(b, w=w, d=d))
    return out


def _backdrop(doc):
    return {"image": doc.backdrop_image or "", "x": doc.backdrop_x or 0, "z": doc.backdrop_z or 0, "width": doc.backdrop_width or 0,
            "rotation": doc.backdrop_rotation or 0, "opacity": doc.backdrop_opacity if doc.backdrop_opacity is not None else 50}


def _draft(name):
    doc = frappe.get_doc("Yard Layout", name)
    if doc.status != "Draft":
        frappe.throw(_("Only a draft can be edited."))
    doc.check_permission("write")
    return doc


@frappe.whitelist()
def designer_data(terminal):
    """Everything the yard designer needs: the terminal's draft (created from the live layout if there is none), its blocks and the geometry."""
    frappe.only_for(DESIGNERS)
    name = create_draft(terminal)
    doc = frappe.get_doc("Yard Layout", name)
    live = yard_layout.published(terminal)
    return {
        "draft": doc.name, "modified": str(doc.modified), "layout_name": doc.layout_name, "base_surface": doc.base_surface or "Default",
        "items": [yard_layout._row(i) for i in doc.items], "blocks": _blocks(terminal), "geometry": yard_layout.geometry(),
        "live_version": live.version if live else 0, "based_on": doc.based_on, "backdrop": _backdrop(doc),
        "can_publish": bool(set(frappe.get_roles()) & set(PUBLISHERS)),
    }


@frappe.whitelist(methods=["POST"])
def save_draft(layout, items, base_surface="Default", modified=None, backdrop=None):
    """Replace the draft's items. `modified` is what the designer last saw; if the draft changed since, nothing is overwritten."""
    frappe.only_for(DESIGNERS)
    doc = _draft(layout)
    if modified and str(doc.modified) != str(modified):
        frappe.throw(_("This draft was changed by someone else. Reload the designer to see their changes."), title=_("Draft changed"))
    rows = frappe.parse_json(items) or []
    clean = []
    for r in rows:
        row = {k: r.get(k) for k in yard_layout.ITEM_FIELDS}
        for k in NUMBERS:
            row[k] = round(float(row[k] or 0), 3)
        row["locked"] = 1 if row.get("locked") else 0
        clean.append(row)
    doc.set("items", [])
    for row in clean:
        doc.append("items", row)
    doc.base_surface = base_surface or "Default"
    b = frappe.parse_json(backdrop) if backdrop else None
    if b is not None:
        doc.backdrop_image = b.get("image") or None
        for key in ("x", "z", "width", "rotation"):
            doc.set("backdrop_" + key, round(float(b.get(key) or 0), 3))
        doc.backdrop_opacity = max(0, min(100, int(b.get("opacity", 50))))
    doc.save()
    return {"modified": str(doc.modified)}


@frappe.whitelist()
def check_draft(layout):
    """Reasons the draft cannot be published yet (an empty list when it can)."""
    frappe.only_for(DESIGNERS)
    doc = _draft(layout)
    return yard_layout.publish_problems(doc)


@frappe.whitelist(methods=["POST"])
def publish_draft(layout):
    frappe.only_for(PUBLISHERS)
    doc = _draft(layout)
    doc.publish()
    return doc.name


@frappe.whitelist(methods=["POST"])
def discard_draft(layout):
    """Delete the draft. The next time the designer opens, a fresh draft is made from the live layout."""
    frappe.only_for(DESIGNERS)
    doc = _draft(layout)
    frappe.delete_doc("Yard Layout", doc.name, ignore_permissions=True)
    return True


@frappe.whitelist()
def layout_history(terminal):
    """Every layout this terminal has had: the draft first, then newest to oldest."""
    frappe.only_for(DESIGNERS)
    rows = frappe.get_all("Yard Layout", filters={"terminal": terminal}, order_by="modified desc",
                          fields=["name", "layout_name", "status", "version", "published_by", "published_on", "based_on", "modified"])
    for r in rows:
        r["item_count"] = frappe.db.count("Yard Layout Item", {"parent": r["name"]})
    return sorted(rows, key=lambda r: (r["status"] != "Draft", -(r["version"] or 0)))


@frappe.whitelist()
def layout_view(layout):
    """A saved layout in the shape the 3D yard draws, so an old version can be previewed."""
    frappe.only_for(DESIGNERS)
    doc = frappe.get_doc("Yard Layout", layout)
    doc.check_permission("read")
    return yard_layout.effective(doc.terminal, doc)


@frappe.whitelist(methods=["POST"])
def restore_version(layout, replace=0):
    """Copy an earlier layout into a new draft. An existing draft must be replaced (thrown away) explicitly."""
    frappe.only_for(DESIGNERS)
    old = frappe.get_doc("Yard Layout", layout)
    old.check_permission("read")
    existing = frappe.db.get_value("Yard Layout", {"terminal": old.terminal, "status": "Draft"}, "name")
    if existing:
        if existing == old.name:
            return existing
        if not int(replace):
            frappe.throw(_("There is already a draft for this terminal. Discard it, or choose to replace it."), title=_("Draft in the way"))
        frappe.delete_doc("Yard Layout", existing, ignore_permissions=True)
    doc = frappe.get_doc({
        "doctype": "Yard Layout", "terminal": old.terminal, "layout_name": _("Restored from version {0}").format(old.version or old.name),
        "status": "Draft", "based_on": old.name, "base_surface": old.base_surface or "Default",
        "items": [yard_layout._row(i) for i in old.items], **{f: old.get(f) for f in BACKDROP},
    })
    doc.insert()
    frappe.db.commit()
    return doc.name
