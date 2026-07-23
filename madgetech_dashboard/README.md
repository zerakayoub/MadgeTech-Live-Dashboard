# MadgeTech CCA2 Wall Dashboard

## Important security step

The `userauth` value visible in your screenshot is effectively a login/session credential.
Log out of MadgeTech Cloud and log back in before using this project so the exposed value is
invalidated. Then copy the new value privately into `.env`. Never upload `.env` to GitHub.

## What "every second" means

The dashboard itself refreshes every second. The backend can also request MadgeTech Cloud every
second when `CLOUD_POLL_SECONDS=1`.

However, the logger response says `rdgratesecs: 60`, so the RFRHTemp2000A currently records a new
temperature/humidity sample only once every 60 seconds. Polling every second will usually repeat
the same value 59 times and may cause unnecessary load. After testing, set:

    CLOUD_POLL_SECONDS=60

To obtain genuinely new measurements each second, the logger's reading rate would have to be
changed to 1 second in MadgeTech, assuming your relay/cloud configuration supports that rate.
This will use battery and logger memory much faster.

## Windows setup

1. Install Python 3.11 or newer.
2. Open Command Prompt in this folder.
3. Create and activate a virtual environment:

       py -m venv .venv
       .venv\Scripts\activate

4. Install packages:

       pip install -r requirements.txt

5. Copy `.env.example` to `.env`.
6. Put a fresh `userauth` value in `.env`.
7. Start the dashboard:

       python app.py

8. Open:

       http://127.0.0.1:5000

9. Press F11 for full screen.

## Getting a fresh userauth value

While logged in to MadgeTech Cloud:

1. Open Developer Tools > Network.
2. Refresh the Summary page.
3. Select the `browserapi` request whose function is `AccountListLoggerGroups`.
4. Open Payload.
5. Copy only the `userauth` value into `.env`.
6. Do not share that value.

## Raspberry Pi later

The same project works on Raspberry Pi OS. Install Python, run the same commands, and open
Chromium in kiosk mode at `http://127.0.0.1:5000`.

## Notes

This project uses an internal web endpoint observed in the MadgeTech Cloud website. It is not a
documented public API, so MadgeTech could change the request format. For a production deployment,
ask MadgeTech whether they offer an official supported API or permanent dashboard credentials.
