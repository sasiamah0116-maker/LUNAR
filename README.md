# LUNAR 🌙

LUNAR shows what type of day is coming from lunar-day analysis, and syncs it into people's phone calendars (iPhone, Android/Google, Outlook) together with the moon phases.

## What it shows
Each date gets the lunar day (1–30) in force at sunrise (06:00 local) and that day's type:

| Lunar days (each half of the month) | Day type |
|---|---|
| 1, 6, 11 | Joyful Day |
| 2, 7, 12 | Good Day |
| 3, 8, 13 | Victory Day |
| **4, 9, 14** | **⛔ Evil Day** (traditionally the "empty" days) |
| 5, 10, 15 (Full / New Moon) | Full Day |

The calendar feed also has an event for each exact New Moon, First Quarter, Full Moon and Last Quarter. If someone ticks the box, they get a reminder the evening before every Evil Day.

## Run it on your computer
Needs only Python 3.9 or newer. There's nothing to install.

```bash
python3 server.py
```
Then open http://localhost:8080.

## Put it online for the public (Render)
Phone calendars can only subscribe to a public **https** address. `render.yaml` sets LUNAR up on [Render](https://render.com).

1. **GitHub:** create a new repository called `lunar`. Choose *uploading an existing file* and drag in `lunar.py`, `server.py`, `requirements.txt`, `render.yaml`, `README.md` and the `public` folder. Click *Commit changes*.
2. **Render:** sign up with your GitHub account, then go to **New → Blueprint** and pick the `lunar` repository. Leave the email settings blank for now and click **Apply**.
3. After a few minutes you get an address like `https://lunar-xxxx.onrender.com`. Open it on your phone and try *Sync my calendar*.

Calendar links look like `/feed/1/Africa/Accra.ics`. They don't depend on any saved data, so they keep working after restarts and redeploys.

**Free vs paid:** the free plan sleeps after 15 minutes with no visitors, and the first visit afterwards takes about a minute. Phone calendars may skip an update when that happens. For a public app, the Starter plan (about $7 a month) keeps LUNAR awake.

### Optional: welcome emails and a permanent email list
Render's free plan wipes `data/subscribers.json` whenever it restarts. To keep the email list safe and send welcome emails, use [Resend](https://resend.com):

1. Create a Resend account and verify a domain you own. Without one, Resend only sends emails to you.
2. Create an API key and an Audience.
3. In Render, under **lunar → Environment**, set:
   - `RESEND_API_KEY`: the API key
   - `MAIL_FROM`: e.g. `LUNAR <hello@yourdomain.com>`
   - `RESEND_AUDIENCE_ID`: every signup is saved here
   - `PUBLIC_URL`: your LUNAR address, e.g. `https://lunar-xxxx.onrender.com`

## Files
- `lunar.py`: moon position, lunar days, day types and calendar (.ics) generation
- `server.py`: website, API, personal calendar feeds and email signup
- `public/`: the web app (works as an "Add to Home Screen" app on phones too)
