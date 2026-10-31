# Handover — Move-Out Meets Move-In

A working prototype helping departing students offer free household
items to incoming students whose pickup availability overlaps.

The focus is feasible handover timing—not payments, delivery,
or temporary storage.

## Core workflow

Create listing → request compatible pickup → receive temporary offer
→ confirm reservation → owner records collection.

If a confirmed reservation expires:

Recipient proposes late pickup → owner approves or rejects →
approved pickup can be completed during the new window.

## Features

- Create a free-item listing with a pickup address and time window.
- Match owner and recipient availability.
- Propose a 15-minute pickup appointment.
- Temporarily hold an item for five simulated minutes.
- Prevent conflicting claims.
- Confirm or cancel a reservation.
- Record collection through the owner.
- Expire uncollected reservations at the owner's final pickup deadline.
- Request and approve late pickup.
- Reject late pickup and manually relist with a new time window.
- Remove listings through owner-only controls.

## Setup

Python 3.13 is the locally tested version.

Run these commands from the project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On Windows, replace the activation command with:

```powershell
.venv\Scripts\activate
```

## Tests

```bash
python -m unittest -v
```

The current suite contains 31 passing tests:

- test_core.py: 9 tests
- test_lifecycle.py: 16 tests
- test_listing_management.py: 6 tests

These test matching, offers, expiration, lifecycle transitions,
late-pickup decisions, address storage, visibility, and removal.

The suite does not constitute production security, load, or
end-to-end browser testing.

## Sample data

Each new browser session starts with:

- Study desk, owned by Priya
- Kitchen starter set, owned by Neha

Both have fictional pickup locations and pickup windows tomorrow
from 9 a.m. to noon, America/Los_Angeles time.

Demo students: Adi, Priya, and Neha.

All items are free. Use fictional addresses only.

## Demo clock

The clock is paused until advanced using the sidebar.

- Advance 6 minutes: demonstrate temporary-offer expiration.
- Advance 1 hour: move toward or beyond pickup deadlines.

Real-world waiting alone does not advance the simulated clock.

Use one browser tab and switch identities through the sidebar.
Each separate browser session has its own demo data.

## Listing states

- available: can receive an ordinary request.
- offered: temporarily held while awaiting recipient confirmation.
- reserved: original pickup is confirmed.
- expired: ordinary pickup is closed.
- late_requested: recipient proposed a new window; owner decision pending.
- late_reserved: owner approved the new window.
- collected: owner recorded handover.
- deleted: removed from browsing through soft deletion.

## Expiration and visibility rules

Expired listings remain visible to everyone as EXPIRED.

For late_requested and late_reserved arrangements:

- The owner and recipient see the actual late-pickup status and window.
- Other students see EXPIRED and cannot submit an ordinary request.

The backend retains the actual state. The interface applies the
outsider-facing EXPIRED label.

Removed listings are hidden from everyone.

## Late-pickup rules

Only the original confirmed recipient can request late pickup.

The proposed window must:

- Start after the current simulated time.
- Start at or after the original owner's pickup deadline.
- Be at least 15 minutes long.

Late pickup is not confirmed until the owner approves.

An unanswered proposal expires when its proposed start arrives.
An approved late reservation expires when its new end time arrives.

If the owner rejects the request, the arrangement ends.
The owner can create a new listing with new availability through
the "List an item" tab. Relisting is manual, not automatic.

An expired reservation does not prove a physical no-show.
It means collection was not recorded before the applicable deadline.

## Representative demonstration

1. Act as Adi.
2. Request Priya's desk using compatible availability.
3. Confirm the offer before five simulated minutes pass.
4. Switch to Priya.
5. Advance time into the pickup appointment.
6. Confirm collection.

Expected result: COLLECTED.

## Difficult demonstrations

### Incompatible availability

Request an available item for the day after its pickup window.

Expected: a clear error and no offer created.

### Unconfirmed offer

Request an item without confirming, then advance six minutes.

Expected: the offer is released. The item becomes AVAILABLE
if sufficient pickup time remains; otherwise it becomes EXPIRED.

### Late pickup

1. Confirm a reservation.
2. Advance beyond the owner's final pickup deadline.
3. As the recipient, propose a future late window.
4. As the owner, approve.
5. As a third student, verify the listing still displays EXPIRED.
6. Advance into the approved window.
7. As the owner, confirm collection.

Expected: owner-approved late collection succeeds.

Alternatively, reject the request.

Expected: the arrangement ends and the listing remains EXPIRED.

### Removal

As the owner, open Owner controls, tick the confirmation checkbox,
and remove a listing.

Expected: it disappears from everyone's browse view.

## Architecture

- app.py: Streamlit interface, demo identities, and simulated clock.
- core.py: SQLite storage, matching, and state transitions.
- test_core.py: matching and temporary-offer tests.
- test_lifecycle.py: reservation and late-pickup tests.
- test_listing_management.py: address, visibility, and removal tests.

SQLite write transactions serialize competing claims.
SQL parameters are used for user-supplied values.

## Implemented

The matching and reservation logic actually runs.
Data is stored in SQLite during the demonstration.

The address column and late-window columns are added to older
database schemas when needed.

Removal uses soft deletion rather than erasing the database record.

## Simulated and deferred

- Student identities are simulated; there is no authentication.
- Ownership checks use selected names, not verified accounts.
- Users, sample items, and pickup addresses are fictional.
- Messages appear in the application; no email or SMS is sent.
- There is no payment, delivery, storage, or university integration.
- There is no independent verification of physical handover.
- There is no immutable audit history.
- There are no product-image or category-filter features.

## Storage and scheduling limitations

Each browser session uses a separate temporary SQLite database.

Data survives interface reruns within that session.
Persistence across new sessions or server restarts is not guaranteed.

Expiration is reconciled during application interaction.
There is no continuously running background scheduler.

The interface supports same-day availability windows.
Times are displayed in America/Los_Angeles.

## Privacy

Use synthetic information only.

Pickup addresses are visible to people browsing the listing.
This prototype is not suitable for storing real private addresses
or coordinating real transactions without further security work.

## AI assistance

ChatGPT assisted with brainstorming, code suggestions, debugging,
test creation, and documentation.

I ran the automated tests locally. The latest run reported
31 passing tests.

The application itself does not use an AI model.
Matching and state transitions use deterministic rules.

## Next validation

Interview departing and incoming students to determine:

- How frequently usable items fail to find recipients.
- Whether pickup timing is a major obstacle.
- Whether transport or storage is the larger problem.
- Whether students keep availability and listings updated.
- Whether existing group chats already solve the problem adequately.

A future pilot could measure completed handovers, failed matches,
cancellations, and user effort. No measured waste reduction,
cost savings, or adoption results are claimed.
