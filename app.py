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
    refresh_expired,
    utc_now,
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

    return datetime.fromtimestamp(
        value, LOCAL_TZ
    ).strftime("%b %d, %I:%M %p %Z")


def local_datetime(day, clock):
    return datetime.combine(day, clock, tzinfo=LOCAL_TZ)


def perform_action(function, *args):
    try:
        function(*args)
    except ValueError as error:
        st.error(str(error))
    else:
        st.session_state["notice"] = "Action completed successfully."
        st.rerun()


# Each browser session gets an isolated demonstration database.
# This prevents one visitor's demo clock from changing another's data.
if "database_path" not in st.session_state:
    demo_folder = Path(mkdtemp(prefix="handover-demo-"))
    st.session_state["database_path"] = str(
        demo_folder / "demo.db"
    )
    st.session_state["demo_now"] = utc_now()
    st.session_state["seeded"] = False

now = st.session_state["demo_now"]
db = connect(st.session_state["database_path"])

# Close the connection even when Streamlit reruns the application.
try:
    if not st.session_state["seeded"]:
        tomorrow = (
            now.astimezone(LOCAL_TZ) + timedelta(days=1)
        ).date()
        sample_start = datetime(
            tomorrow.year,
            tomorrow.month,
            tomorrow.day,
            9,
            0,
            tzinfo=LOCAL_TZ,
        )

        sample_end = sample_start + timedelta(hours=3)

        create_listing(
            db,
            "Study desk — free",
            "Priya",
            sample_start,
            sample_end,
        )
        create_listing(
            db,
            "Kitchen starter set — free",
            "Neha",
            sample_start,
            sample_end,
        )

        st.session_state["seeded"] = True

    st.title("🏠 Handover")
    st.subheader("Move-out items. Move-in essentials. A pickup that works.")

    st.info(
        "Interactive prototype: synthetic users and listings. "
        "Free items, local pickup only. "
        "Identity selection is not authentication."
    )

    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))

    with st.sidebar:
        st.header("Demo controls")

        actor = st.selectbox(
            "Act as student",
            ["Adi", "Priya", "Neha"],
        )

        st.write("**Simulated time**")
        st.write(format_time(now.timestamp()))
        st.caption(
            "Time is paused until you advance it. "
            "Use one browser tab and switch students here."
        )

        if st.button("Advance 6 minutes"):
            st.session_state["demo_now"] += timedelta(minutes=6)
            st.rerun()

        if st.button("Advance 1 hour"):
            st.session_state["demo_now"] += timedelta(hours=1)
            st.rerun()

        st.caption(
            "Each browser session has a separate demo database. "
            "It survives button clicks, but is not durable "
            "account storage across new sessions or server restarts."
        )

    refresh_expired(db, now)

    browse_tab, create_tab = st.tabs(
        ["Browse and manage items", "List an item"]
    )

    with create_tab:
        st.write(f"Listing as **{actor}**")

        default_start = (
            now.astimezone(LOCAL_TZ) + timedelta(hours=1)
        )
        default_end = default_start + timedelta(hours=2)

        with st.form("create_listing"):
            title = st.text_input(
                "Item name",
                placeholder="Example: Desk lamp — free",
            )

            pickup_day = st.date_input(
                "Pickup date",
                value=default_start.date(),
            )

            start_time = st.time_input(
                "Pickup window starts",
                value=default_start.time().replace(tzinfo=None),
            )

            end_time = st.time_input(
                "Pickup window ends",
                value=default_end.time().replace(tzinfo=None),
            )

            st.caption(
                "All times are Los Angeles time. "
                "This version supports same-day pickup windows."
            )

            submitted = st.form_submit_button("Publish free item")

        if submitted:
            start = local_datetime(pickup_day, start_time)
            end = local_datetime(pickup_day, end_time)

            if start < now:
                st.error("Choose a pickup start at or after demo time.")
            else:
                perform_action(
                    create_listing,
                    db, title, actor, start, end,
                )

    with browse_tab:
        st.caption(
            "Pickup location for this demonstration: "
            "the fictional Student Community Lobby. "
            "No delivery or temporary storage is provided."
        )

        rows = db.execute(
            "SELECT * FROM listings ORDER BY id DESC"
        ).fetchall()

        for row in rows:
            item = dict(row)
            item_id = item["id"]

            with st.expander(
                f"#{item_id} · {item['title']} · "
                f"{item['status'].upper()}",
                expanded=True,
            ):
                st.write(f"**Owner:** {item['owner']}")
                st.write(
                    "**Owner's pickup window:** "
                    f"{format_time(item['pickup_start'])} → "
                    f"{format_time(item['pickup_end'])}"
                )

                if item["recipient"]:
                    st.write(
                        f"**Recipient:** {item['recipient']}"
                    )
                    st.write(
                        "**Pickup appointment:** "
                        f"{format_time(item['appointment_start'])} → "
                        f"{format_time(item['appointment_end'])}"
                    )

                if item["status"] == "offered":
                    st.warning(
                        "Temporary offer. Confirm before "
                        f"{format_time(item['hold_until'])}."
                    )

                if (
                    item["status"] == "available"
                    and actor != item["owner"]
                ):
                    owner_start = datetime.fromtimestamp(
                        item["pickup_start"], LOCAL_TZ
                    )
                    owner_end = datetime.fromtimestamp(
                        item["pickup_end"], LOCAL_TZ
                    )

                    with st.form(f"request_{item_id}"):
                        day = st.date_input(
                            "Your pickup date",
                            value=owner_start.date(),
                            key=f"day_{item_id}",
                        )
                        start_clock = st.time_input(
                            "You are available from",
                            value=owner_start.time().replace(
                                tzinfo=None
                            ),
                            key=f"from_{item_id}",
                        )
                        end_clock = st.time_input(
                            "You are available until",
                            value=owner_end.time().replace(
                                tzinfo=None
                            ),
                            key=f"until_{item_id}",
                        )

                        requested = st.form_submit_button(
                            "Find pickup time and request"
                        )

                    if requested:
                        perform_action(
                            request_item,
                            db,
                            item_id,
                            actor,
                            local_datetime(day, start_clock),
                            local_datetime(day, end_clock),
                            now,
                        )

                if (
                    item["status"] == "offered"
                    and actor == item["recipient"]
                ):
                    if st.button(
                        "Confirm pickup",
                        key=f"confirm_{item_id}",
                    ):
                        perform_action(
                            confirm_offer,
                            db, item_id, actor, now,
                        )

                if (
                    item["status"] in ("offered", "reserved")
                    and actor in (
                        item["owner"], item["recipient"]
                    )
                ):
                    if st.button(
                        "Cancel offer or reservation",
                        key=f"cancel_{item_id}",
                    ):
                        perform_action(
                            cancel_reservation,
                            db, item_id, actor, now,
                        )

                if (
                    item["status"] == "reserved"
                    and actor == item["owner"]
                ):
                    if st.button(
                        "Confirm item collected",
                        key=f"collect_{item_id}",
                    ):
                        perform_action(
                            mark_collected,
                            db, item_id, actor, now,
                        )

finally:
    db.close()