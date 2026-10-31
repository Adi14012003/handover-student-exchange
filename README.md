# Handover — Move-Out Meets Move-In

A runnable prototype helping departing students offer free household
items to incoming students whose pickup availability overlaps.

## Core workflow

Create listing → request compatible pickup → receive temporary offer
→ confirm reservation → owner confirms collection.

Unconfirmed offers expire after five simulated minutes.
Pickup appointments require at least 15 minutes of overlapping availability.

## Requirements

Python 3.13 is the locally tested version.
Dependencies are listed in requirements.txt.

## Setup and run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\activate
```

## Run tests

```bash
python -m unittest -v
```

The current suite contains 18 tests covering matching, conflicting claims,
offer expiration, confirmation, cancellation, and collection rules.

## Sample data

Each new browser session starts with two synthetic listings:

- Study desk, owned by Priya
- Kitchen starter set, owned by Neha

Both have pickup windows tomorrow from 9 a.m. to noon,
America/Los_Angeles time.

Demo identities: Adi, Priya, and Neha.
Pickup location: fictional Student Community Lobby.

## Representative demonstration

1. Act as Adi.
2. Request Priya's desk using the default pickup window.
3. Confirm the offer.
4. Switch to Priya.
5. Advance simulated time until the appointment begins.
6. Confirm collection.

Expected result: the desk becomes COLLECTED.

## Difficult cases

### Incompatible timing

Request an available item for the day after its pickup window.

Expected result: no compatible pickup window; no offer is created.

### Unconfirmed offer

Request an item without confirming, then advance six minutes.

Expected result: the offer expires and the item becomes AVAILABLE,
provided sufficient pickup time remains.

### Conflicting claim

While one student holds an offer, switch to another student.

Expected result: the held item cannot receive another request.

## Architecture

- app.py: Streamlit interface and isolated demo session
- core.py: SQLite storage, time matching, and reservation transitions
- test_core.py: matching and temporary-offer tests
- test_lifecycle.py: confirmation, cancellation, and collection tests

## Implemented

- Listing creation
- Pickup overlap validation
- Temporary offers and expiration
- Reservation confirmation and cancellation
- Owner-confirmed collection
- Transaction-protected claims
- Automated tests

## Simulated

- Student identities, without authentication
- Sample users and items
- Paused clock with manual advancement
- Fixed fictional pickup location

## Limitations and deferred work

- This is an isolated demonstration, not a shared marketplace.
- Each browser session has a separate temporary SQLite database.
- Data survives application reruns within that session, but persistence
  across new sessions or server restarts is not guaranteed.
- Expiration is reconciled on application interaction, not by a
  continuously running background scheduler.
- No payments, transport, storage, email, SMS, or university integration.
- User-created pickup windows are same-day.
- Identity checks are demonstration controls, not security boundaries.
- No immutable audit trail or independent verification of physical pickup.

## AI assistance

ChatGPT assisted with brainstorming, implementation suggestions, test
creation, debugging guidance, and documentation. I ran the automated tests
and manually exercised the successful and difficult workflows.
The application itself does not call an AI model.

## Next validation

Interview departing and incoming students to determine whether timing
coordination is a frequent obstacle, or whether transport and storage
are the larger problems.