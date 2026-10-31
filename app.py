from datetime import datetime, timedelta
from pathlib import Path
from tempfile import mkdtemp
from zoneinfo import ZoneInfo

import streamlit as st

from core import (
    connect,
    create_listing,
    request_item,
    confirm_offer,
    cancel_reservation,
    mark_collected,
    utc_now,
    browse_listings,
    delete_listing,
    request_late_pickup,
    decide_late_pickup,
)


st.set_page_config(
    page_title="Handover",
    page_icon="🏠",
    layout="wide",
)

LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def format_time(value):
    if value is None:
        return "—"
    return datetime.fromtimestamp(value, LOCAL_TZ).strftime(
        "%b %d, %I:%M %p %Z"
    )


def local_datetime(day, clock):
    return datetime.combine(
        day, clock.replace(tzinfo=None), tzinfo=LOCAL_TZ
    )


def next_morning(now):
    tomorrow = (now.astimezone(LOCAL_TZ) + timedelta(days=1)).date()
    return datetime(
        tomorrow.year, tomorrow.month, tomorrow.day,
        9, 0, tzinfo=LOCAL_TZ,
    )


def perform_action(function, *args):
    try:
        function(*args)
    except ValueError as error:
        st.error(str(error))
    else:
        st.session_state["notice"] = "Action completed successfully."
        st.rerun()


def availability_form(prefix, default_start, default_end, button):
    with st.form(prefix):
        day = st.date_input(
            "Pickup date",
            value=default_start.date(),
            key=f"{prefix}_day",
        )
        start_clock = st.time_input(
            "Available from",
            value=default_start.time().replace(tzinfo=None),
            key=f"{prefix}_start",
        )
        end_clock = st.time_input(
            "Available until",
            value=default_end.time().replace(tzinfo=None),
            key=f"{prefix}_end",
        )
        st.caption("Los Angeles time. Start and end must be on the same day.")
        submitted = st.form_submit_button(button)

    return (
        submitted,
        local_datetime(day, start_clock),
        local_datetime(day, end_clock),
    )


if "database_path" not in st.session_state:
    folder = Path(mkdtemp(prefix="handover-demo-"))
    st.session_state["database_path"] = str(folder / "demo.db")
    st.session_state["demo_now"] = utc_now()
    st.session_state["seeded"] = False

now = st.session_state["demo_now"]
db = connect(st.session_state["database_path"])

try:
    if not st.session_state["seeded"]:
        start = next_morning(now)
        end = start + timedelta(hours=3)

        create_listing(
            db, "Study desk — free", "Priya", start, end,
            "Demo Residence A, main lobby — fictional",
        )
        create_listing(
            db, "Kitchen starter set — free", "Neha", start, end,
            "Demo Residence B, reception — fictional",
        )
        st.session_state["seeded"] = True

    st.title("🏠 Handover")
    st.subheader("Move-out items. Move-in essentials. A pickup that works.")
    st.info(
        "Synthetic demonstration. Free items and local pickup only. "
        "Use fictional addresses. Identity selection is not authentication."
    )

    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))

    with st.sidebar:
        st.header("Demo controls")
        actor = st.selectbox("Act as student", ["Adi", "Priya", "Neha"])
        st.write("**Simulated time**")
        st.write(format_time(now.timestamp()))
        st.caption(
            "Time is paused. Use one browser tab and switch students here."
        )

        if st.button("Advance 6 minutes"):
            st.session_state["demo_now"] += timedelta(minutes=6)
            st.rerun()

        if st.button("Advance 1 hour"):
            st.session_state["demo_now"] += timedelta(hours=1)
            st.rerun()

        st.caption(
            "Separate temporary database per browser session. "
            "No durable account storage, email, or SMS."
        )

    browse_tab, create_tab = st.tabs(
        ["Browse and manage items", "List an item"]
    )

    with create_tab:
        st.write(f"Listing as **{actor}**")

        default_start = next_morning(now)
        default_end = default_start + timedelta(hours=2)

        with st.form("create_listing"):
            title = st.text_input("Item name")
            address = st.text_input(
                "Pickup address / meeting point",
                help="Visible to browsers. Use a fictional public meeting point.",
            )
            day = st.date_input("Pickup date", value=default_start.date())
            start_clock = st.time_input(
                "Pickup window starts",
                value=default_start.time().replace(tzinfo=None),
            )
            end_clock = st.time_input(
                "Pickup window ends",
                value=default_end.time().replace(tzinfo=None),
            )
            st.caption(
                "Same-day windows, Los Angeles time. "
                "To relist an expired item, publish it here with a new window."
            )
            submitted = st.form_submit_button("Publish free item")

        if submitted:
            start = local_datetime(day, start_clock)
            end = local_datetime(day, end_clock)

            if start < now:
                st.error("Pickup cannot start before the current demo time.")
            else:
                perform_action(
                    create_listing, db, title, actor, start, end, address
                )

    with browse_tab:
        st.caption(
            "Expired listings remain visible but cannot receive ordinary "
            "requests. Only the original recipient can propose late pickup. "
            "The owner must approve. Removed listings are hidden."
        )

        items = browse_listings(db, actor, now)

        if not items:
            st.info("No listings to display.")

        for item in items:
            item_id = item["id"]
            status = item["status"]
            participant = actor in (item["owner"], item["recipient"])

            # Outsiders see late arrangements as expired, not available.
            display_status = status
            if status in ("late_requested", "late_reserved") and not participant:
                display_status = "expired"

            with st.expander(
                f"#{item_id} · {item['title']} · "
                f"{display_status.replace('_', ' ').upper()}",
                expanded=True,
            ):
                st.write(f"**Owner:** {item['owner']}")
                st.write("**Pickup meeting point:**")
                st.text(item["pickup_address"] or "Contact the owner.")

                st.write(
                    "**Original owner pickup window:** "
                    f"{format_time(item['pickup_start'])} → "
                    f"{format_time(item['pickup_end'])}"
                )

                if participant and item["recipient"]:
                    st.write(f"**Recipient:** {item['recipient']}")

                    if item["appointment_start"] is not None:
                        st.write(
                            "**Original appointment:** "
                            f"{format_time(item['appointment_start'])} → "
                            f"{format_time(item['appointment_end'])}"
                        )

                if display_status == "expired":
                    st.warning(
                        "Expired: ordinary pickup requests are closed. "
                        "This does not confirm whether physical collection occurred."
                    )

                if status == "offered" and participant:
                    st.warning(
                        "Confirm the temporary offer before "
                        f"{format_time(item['hold_until'])}."
                    )

                if status == "reserved" and participant:
                    st.info("Original pickup is confirmed.")

                if status == "late_requested" and participant:
                    st.warning(
                        "Late pickup requested — awaiting owner approval. "
                        "This is not yet a confirmed appointment."
                    )
                    st.write(
                        "**Proposed late window:** "
                        f"{format_time(item['late_start'])} → "
                        f"{format_time(item['late_end'])}"
                    )

                if status == "late_reserved" and participant:
                    st.success(
                        "The owner approved late pickup. "
                        "The recipient is expected during the window below."
                    )
                    st.write(
                        "**Approved late window:** "
                        f"{format_time(item['late_start'])} → "
                        f"{format_time(item['late_end'])}"
                    )

                if status == "collected":
                    st.success("Owner recorded collection.")

                if actor == item["owner"]:
                    with st.expander("Owner controls"):
                        if status in (
                            "offered", "reserved",
                            "late_requested", "late_reserved",
                        ):
                            st.warning(
                                "Removing this listing ends the arrangement. "
                                "No external notification is sent."
                            )

                        remove = st.checkbox(
                            "I understand: remove this listing.",
                            key=f"remove_check_{item_id}",
                        )
                        if st.button(
                            "Remove listing",
                            key=f"remove_{item_id}",
                            disabled=not remove,
                        ):
                            perform_action(
                                delete_listing, db, item_id, actor
                            )

                        if status == "expired":
                            st.caption(
                                "To offer this item again, use 'List an item' "
                                "with a new pickup window. Remove this old "
                                "listing if you no longer need it."
                            )

                if status == "available" and actor != item["owner"]:
                    start = datetime.fromtimestamp(
                        item["pickup_start"], LOCAL_TZ
                    )
                    end = datetime.fromtimestamp(
                        item["pickup_end"], LOCAL_TZ
                    )
                    submitted, start, end = availability_form(
                        f"request_{item_id}", start, end,
                        "Find pickup time and request",
                    )
                    if submitted:
                        perform_action(
                            request_item,
                            db, item_id, actor, start, end, now,
                        )

                if status == "offered" and actor == item["recipient"]:
                    if st.button("Confirm pickup", key=f"confirm_{item_id}"):
                        perform_action(
                            confirm_offer, db, item_id, actor, now
                        )

                if (
                    status == "expired"
                    and actor == item["recipient"]
                    and item["appointment_start"] is not None
                ):
                    st.write("**Request a late pickup**")
                    st.caption(
                        "Propose a new window. The owner may approve or reject. "
                        "An unanswered request lapses when its proposed start arrives."
                    )
                    start = next_morning(now)
                    end = start + timedelta(hours=1)

                    submitted, start, end = availability_form(
                        f"late_{item_id}", start, end,
                        "Request owner approval for late pickup",
                    )
                    if submitted:
                        perform_action(
                            request_late_pickup,
                            db, item_id, actor, start, end, now,
                        )

                if status == "late_requested" and actor == item["owner"]:
                    if st.button(
                        "Approve late pickup", key=f"approve_{item_id}"
                    ):
                        perform_action(
                            decide_late_pickup,
                            db, item_id, actor, True, now,
                        )

                    if st.button(
                        "Reject late pickup", key=f"reject_{item_id}"
                    ):
                        perform_action(
                            decide_late_pickup,
                            db, item_id, actor, False, now,
                        )

                if (
                    status in ("offered", "reserved", "late_reserved")
                    and participant
                ):
                    if st.button(
                        "Cancel arrangement", key=f"cancel_{item_id}"
                    ):
                        perform_action(
                            cancel_reservation, db, item_id, actor, now
                        )

                if (
                    status in ("reserved", "late_reserved")
                    and actor == item["owner"]
                ):
                    if st.button(
                        "Confirm item collected", key=f"collect_{item_id}"
                    ):
                        perform_action(
                            mark_collected, db, item_id, actor, now
                        )

finally:
    db.close()