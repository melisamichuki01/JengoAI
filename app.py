import streamlit as st
from notion_client_wrapper import get_draft_reports, get_all_reports, update_report_status
from inventory import get_inventory, get_reorder_alerts, pm_adjust_inventory, resolve_alert, update_inventory
from agent import extract_update, generate_report, build_inventory_summary
from notion_client_wrapper import save_report_to_notion

st.set_page_config(page_title="JengoAI | Kamau Construction", page_icon="🏗️", layout="wide")


# ── SHARED PIPELINE ───────────────────────────────────────────────────────────
def run_pipeline(extracted: dict):
    site     = extracted.get("site_name", "Other")
    progress = extracted.get("progress_percentage") or 0
    alerts   = []

    for m in extracted.get("materials_used", []):
        name = m.get("name", "")
        qty  = m.get("quantity") or 0
        if name and qty > 0:
            updated = update_inventory(name, site, qty, progress)
            if updated.get("needs_reorder"):
                alerts.append(name)

    with st.spinner("Generating report..."):
        inventory_items   = get_inventory(site=site)
        inventory_summary = build_inventory_summary(inventory_items)
        report            = generate_report(extracted, inventory_summary)

    with st.spinner("Saving to Notion..."):
        notion_url = save_report_to_notion(report, extracted)

    st.success("Report saved to Notion.")
    st.markdown(f"[Open in Notion]({notion_url})")

    if alerts:
        st.warning(f"Reorder alerts raised for: {', '.join(alerts)}")

    with st.expander("View generated report"):
        st.write(report)

    st.session_state.pop("show_confirm_text", None)
    st.session_state.pop("extracted_text", None)


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏗️ JengoAI")
    st.caption("Kamau Construction")
    st.divider()
    page = st.radio("Navigate", ["Overview", "Foreman Input", "Pending Review", "All Reports", "Inventory"])


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1: OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
if page == "Overview":
    st.title("Dashboard")

    with st.spinner("Loading..."):
        all_reports = get_all_reports()
        alerts      = get_reorder_alerts(resolved=False)

    pending  = [r for r in all_reports if r["report_status"] in ("Draft", "Needs Correction")]
    blockers = [r for r in all_reports if r["status"] == "Has Blockers"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Reports",   len(all_reports))
    c2.metric("Pending Review",  len(pending))
    c3.metric("Active Blockers", len(blockers))
    c4.metric("Reorder Alerts",  len(alerts))

    st.divider()

    col1, col2 = st.columns([3, 2])

    with col1:
        st.subheader("Recent Reports")
        for r in all_reports[:6]:
            with st.container(border=True):
                a, b = st.columns([3, 1])
                with a:
                    st.markdown(f"**{r['site_name']}** — {r['foreman']}")
                    st.caption(r["date"])
                with b:
                    st.markdown(f"**{r['progress']}%**")
                    st.caption(r["report_status"])

    with col2:
        st.subheader("Reorder Alerts")
        if not alerts:
            st.success("No active alerts")
        for a in alerts[:6]:
            with st.container(border=True):
                st.markdown(f"**{a['material']}** — {a['site']}")
                st.caption(f"{a['priority']} priority · {a['stock_pct']}% stock remaining")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2: FOREMAN INPUT
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Foreman Input":
    st.title("Foreman Site Update")

    tab_text, tab_form = st.tabs(["Free Text", "Structured Form"])

    with tab_text:
        st.write("Paste the foreman's message. Can be English, Swahili, or mixed.")
        raw = st.text_area("Message", height=140, label_visibility="collapsed",
                           placeholder="e.g. westlands james hapa. kazi 60%. cement haijafika. salama")

        if st.button("Process Update", type="primary"):
            if not raw.strip():
                st.warning("Please enter a message.")
            else:
                with st.spinner("Extracting..."):
                    extracted = extract_update(raw)
                if extracted.get("confidence") == "low":
                    st.error("Low confidence. Please provide a clearer message.")
                else:
                    st.session_state["extracted_text"] = extracted
                    st.session_state["show_confirm_text"] = True

        if st.session_state.get("show_confirm_text"):
            extracted = st.session_state["extracted_text"]
            st.divider()
            st.subheader("Confirm extracted data")

            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**Site:** {extracted.get('site_name')}")
                st.write(f"**Foreman:** {extracted.get('foreman_name')}")
                st.write(f"**Progress:** {extracted.get('progress_percentage')}%")
                st.write(f"**Safety:** {extracted.get('safety_incidents')}")
            with c2:
                st.write(f"**Blockers:** {', '.join(extracted.get('blockers', [])) or 'None'}")
                st.write(f"**Materials Needed:** {extracted.get('materials_needed', 'None')}")
                st.write(f"**Labor:** {extracted.get('labor_needed', 'None')}")

            if extracted.get("materials_used"):
                st.write("**Materials Used:**")
                for m in extracted["materials_used"]:
                    st.write(f"- {m['name']}: {m.get('quantity','?')} {m.get('unit','units')}")

            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("Confirm and Save", type="primary"):
                    run_pipeline(extracted)
            with c2:
                if st.button("Discard"):
                    st.session_state.pop("show_confirm_text", None)
                    st.session_state.pop("extracted_text", None)
                    st.rerun()

    with tab_form:
        st.write("Fill in the fields directly.")

        f_site     = st.selectbox("Site", ["Westlands", "Kilimani", "Eastleigh", "Other"])
        f_foreman  = st.text_input("Foreman Name")
        f_progress = st.slider("Progress %", 0, 100, 50)
        f_blockers = st.text_area("Blockers (one per line)", height=80)
        f_materials_used = st.text_area("Materials Used (name, quantity, unit — one per line)\ne.g. Cement, 10, bags", height=100)
        f_materials_needed = st.text_input("Materials Needed (to order)")
        f_labor    = st.text_input("Labor Needed")
        f_safety   = st.text_input("Safety Incidents", value="No incidents reported")

        if st.button("Submit Update", type="primary"):
            if not f_foreman.strip():
                st.warning("Please enter the foreman's name.")
            else:
                materials_used = []
                for line in f_materials_used.strip().split("\n"):
                    parts = [p.strip() for p in line.split(",")]
                    if parts[0]:
                        materials_used.append({
                            "name":     parts[0],
                            "quantity": float(parts[1]) if len(parts) > 1 and parts[1].replace(".", "").isdigit() else None,
                            "unit":     parts[2] if len(parts) > 2 else None,
                        })

                extracted = {
                    "site_name":           f_site,
                    "foreman_name":        f_foreman,
                    "progress_percentage": f_progress,
                    "blockers":            [b.strip() for b in f_blockers.strip().split("\n") if b.strip()],
                    "materials_used":      materials_used,
                    "materials_needed":    f_materials_needed or "None",
                    "labor_needed":        f_labor or "None",
                    "safety_incidents":    f_safety,
                    "confidence":          "high",
                }
                run_pipeline(extracted)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3: PENDING REVIEW
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Pending Review":
    st.title("Pending Review")
    st.caption("Reports waiting for your approval before sending to the client.")

    with st.spinner("Loading..."):
        reports = get_draft_reports()

    if not reports:
        st.success("All clear. No reports pending review.")
        st.stop()

    st.caption(f"{len(reports)} report(s) waiting")

    for r in reports:
        with st.expander(f"{r['site_name']} — {r['date']} — {r['report_status']}"):
            c1, c2 = st.columns([2, 1])

            with c1:
                st.subheader("Generated Report")
                st.write(r["report_text"])

            with c2:
                st.write(f"**Progress:** {r['progress']}%")
                st.write(f"**Foreman:** {r['foreman']}")
                st.write(f"**Status:** {r['status']}")
                st.write(f"**Blockers:** {r['blockers'] or 'None'}")
                st.write(f"**Safety:** {r['safety'] or 'No incidents'}")

            if r.get("verification_notes"):
                st.info(r["verification_notes"])

            notes = st.text_area("Notes (optional)", key=f"notes_{r['id']}", label_visibility="collapsed",
                                  placeholder="Add notes or corrections...")

            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("✅ Approve", key=f"approve_{r['id']}", type="primary"):
                    update_report_status(r["id"], "Verified", notes, verified=True)
                    st.success("Approved.")
                    st.rerun()
            with c2:
                if st.button("🚩 Flag for Correction", key=f"flag_{r['id']}"):
                    if not notes.strip():
                        st.warning("Add a note explaining what needs correction.")
                    else:
                        update_report_status(r["id"], "Needs Correction", notes)
                        st.warning("Flagged.")
                        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4: ALL REPORTS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "All Reports":
    st.title("All Reports")

    with st.spinner("Loading..."):
        reports = get_all_reports()

    if not reports:
        st.info("No reports yet.")
        st.stop()

    c1, c2 = st.columns(2)
    with c1:
        sites  = sorted(set(r["site_name"] for r in reports if r["site_name"]))
        site_f = st.selectbox("Filter by site", ["All sites"] + sites)
    with c2:
        status_f = st.selectbox("Filter by status",
            ["All statuses", "Draft", "PM Review", "Verified", "Needs Correction", "Sent to Client"])

    filtered = reports
    if site_f   != "All sites":    filtered = [r for r in filtered if r["site_name"]     == site_f]
    if status_f != "All statuses": filtered = [r for r in filtered if r["report_status"] == status_f]

    st.caption(f"{len(filtered)} report(s)")

    for r in filtered:
        with st.expander(f"{r['site_name']} — {r['date']} — {r['progress']}% — {r['report_status']}"):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(r["report_text"])
            with c2:
                st.write(f"**Foreman:** {r['foreman']}")
                st.write(f"**PM Verified:** {'Yes' if r['pm_verified'] else 'No'}")
                if r.get("verification_notes"):
                    st.caption(r["verification_notes"])


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5: INVENTORY
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Inventory":
    st.title("Inventory")

    inv_tab, alert_tab = st.tabs(["Stock Levels", "Reorder Alerts"])

    with inv_tab:
        with st.spinner("Loading..."):
            all_inventory = get_inventory()

        if not all_inventory:
            st.info("No inventory records yet. They are created automatically when foremen report materials used.")
            st.stop()

        sites    = sorted(set(i["site"] for i in all_inventory if i["site"]))
        site_sel = st.selectbox("Filter by site", ["All sites"] + sites)
        filtered_inv = all_inventory if site_sel == "All sites" else \
                       [i for i in all_inventory if i["site"] == site_sel]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Materials", len(filtered_inv))
        c2.metric("Critical (<20%)", len([i for i in filtered_inv if (i["stock_pct"] or 0) < 20]))
        c3.metric("Low (20-40%)",    len([i for i in filtered_inv if 20 <= (i["stock_pct"] or 0) < 40]))

        st.divider()

        for item in filtered_inv:
            pct = item["stock_pct"] or 0
            icon = "🔴" if pct < 20 else "🟡" if pct < 40 else "🟢"

            with st.expander(f"{icon} {item['material_name']} — {item['site']} — {pct}% remaining"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Opening Stock", f"{item['opening_stock']} {item['unit']}")
                c2.metric("Total Used",    f"{item['total_used']} {item['unit']}")
                c3.metric("Remaining",     f"{item['remaining']} {item['unit']}")

                st.progress(int(min(pct, 100)) / 100)
                st.caption(f"Last updated: {item['last_updated'] or 'never'}")

                st.subheader("PM Adjustment")
                a1, a2 = st.columns(2)
                with a1:
                    new_opening   = st.number_input("Opening Stock",  value=float(item["opening_stock"] or 0),    key=f"o_{item['id']}")
                    new_remaining = st.number_input("Remaining",      value=float(item["remaining"] or 0),        key=f"r_{item['id']}")
                with a2:
                    new_threshold = st.number_input("Min Threshold",  value=float(item["minimum_threshold"] or 0), key=f"t_{item['id']}")
                    new_notes     = st.text_input("Notes",            value=item["notes"] or "",                   key=f"n_{item['id']}")

                if st.button("Save", key=f"save_{item['id']}"):
                    pm_adjust_inventory(item["id"], "opening_stock",     new_opening)
                    pm_adjust_inventory(item["id"], "remaining",         new_remaining)
                    pm_adjust_inventory(item["id"], "minimum_threshold", new_threshold)
                    if new_notes:
                        pm_adjust_inventory(item["id"], "notes", new_notes)
                    st.success("Updated.")
                    st.rerun()

    with alert_tab:
        show_resolved = st.checkbox("Show resolved alerts")

        with st.spinner("Loading..."):
            alerts = get_reorder_alerts(resolved=show_resolved)

        if not alerts:
            st.success(f"No {'resolved' if show_resolved else 'active'} alerts.")
        else:
            for a in alerts:
                icon = "✅" if a["resolved"] else "⚠️"
                with st.expander(f"{icon} {a['material']} — {a['site']} — {a['priority']} Priority"):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Stock Remaining", f"{a['stock_pct']}%")
                    c2.metric("Project Progress", f"{a['progress_pct']}%")
                    c3.metric("Flagged On", a["flagged_on"])

                    st.write(a["reason"])

                    if not a["resolved"]:
                        if st.button("Mark as Resolved", key=f"resolve_{a['id']}"):
                            resolve_alert(a["id"])
                            st.success("Resolved.")
                            st.rerun()
                    else:
                        st.caption(f"Resolved on {a['resolved_on']}")