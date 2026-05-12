# network/ntp.py
__version__ = "0.1.0"

"""
NTP time synchronisation with correct UK DST (GMT/BST) handling.

MicroPython's ntptime.settime() sets the RTC to UTC. This module
applies the correct UK offset and writes local time back to the RTC
so that time.localtime() returns local time throughout the codebase.

DST rules for the UK:
  - Clocks go FORWARD 1 hour at 01:00 UTC on the last Sunday in March
  - Clocks go BACK  1 hour at 01:00 UTC on the last Sunday in October
  - BST = UTC+1, GMT = UTC+0

Usage:
    from network.ntp import sync_time, is_time_synced
    sync_time()                  # call at boot after WiFi is up
    is_time_synced()             # returns True if RTC year >= 2024
"""

import time

try:
    import ntptime
    import machine
    ON_PICO = True
except ImportError:
    ON_PICO = False


# -------------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------------

def sync_time(max_attempts=3):
    """
    Sync the Pico RTC with NTP and apply the correct UK local time offset.

    Retries up to max_attempts times with a 2-second delay between attempts.
    Returns True on success, False if all attempts fail.

    On success, time.localtime() will return UK local time (GMT or BST)
    for the remainder of the session — no offset needs to be applied
    anywhere else in the codebase.
    """
    if not ON_PICO:
        print("ℹ️ NTP: Skipping — not on Pico")
        return True   # desktop testing: assume time is correct

    for attempt in range(1, max_attempts + 1):
        try:
            print(f"🕐 NTP: Syncing (attempt {attempt}/{max_attempts})...")

            # Step 1: Set RTC to UTC via NTP
            ntptime.settime()

            # Step 2: Read the UTC time that was just written
            # IMPORTANT: read epoch directly via time.time() rather than
            # time.localtime(), because some MicroPython builds apply an
            # implicit timezone offset in localtime() which would cause
            # the DST offset to be applied twice.
            utc_epoch = time.time()
            utc_tm    = time.gmtime(utc_epoch)   # guaranteed UTC struct

            # Step 3: Compute UK DST offset
            offset = _uk_dst_offset(utc_tm)

            # Step 4: Apply offset to get local epoch, convert to struct
            local_epoch = utc_epoch + offset
            local_tm    = time.gmtime(local_epoch)

            # Step 5: Write local time to RTC
            # machine.RTC().datetime() tuple: (year, month, day, weekday, hour, min, sec, subsec)
            # weekday: MicroPython RTC uses 0=Monday … 6=Sunday
            # time.gmtime() tm[6] is also 0=Monday, so no adjustment needed.
            machine.RTC().datetime((
                local_tm[0],   # year
                local_tm[1],   # month
                local_tm[2],   # day
                local_tm[6],   # weekday (0=Mon)
                local_tm[3],   # hour
                local_tm[4],   # minute
                local_tm[5],   # second
                0              # subseconds
            ))

            offset_label = "BST (UTC+1)" if offset == 3600 else "GMT (UTC+0)"
            print(f"✅ NTP: Synced — {offset_label} — local time: {_fmt(time.localtime())}")
            return True

        except Exception as e:
            print(f"⚠️ NTP: Attempt {attempt} failed: {e}")
            if attempt < max_attempts:
                time.sleep(2)

    print("⚠️ NTP: All attempts failed — using existing RTC time")
    return False


def is_time_synced():
    """
    Return True if the RTC has been set to a plausible date (year >= 2024).
    The Pico RTC resets to 2021-01-01 on power loss, so this is a reliable
    indicator that NTP has run successfully at least once this session.
    """
    return time.localtime()[0] >= 2024


# -------------------------------------------------------------------------
# Private helpers
# -------------------------------------------------------------------------

def _uk_dst_offset(utc_tm):
    """
    Return the UTC offset in seconds for UK time given a UTC time struct.

    Args:
        utc_tm: time struct in UTC (from time.gmtime())

    Returns:
        3600 if BST (last Sunday March 01:00 UTC to last Sunday Oct 01:00 UTC)
        0    if GMT (outside that range)
    """
    year  = utc_tm[0]
    month = utc_tm[1]
    mday  = utc_tm[2]
    hour  = utc_tm[3]

    dst_start = _last_sunday(year, 3)   # last Sunday in March
    dst_end   = _last_sunday(year, 10)  # last Sunday in October

    # BST starts at 01:00 UTC on last Sunday in March
    # BST ends   at 01:00 UTC on last Sunday in October
    in_bst = False

    if month > 3 and month < 10:
        in_bst = True
    elif month == 3:
        if mday > dst_start:
            in_bst = True
        elif mday == dst_start and hour >= 1:
            in_bst = True
    elif month == 10:
        if mday < dst_end:
            in_bst = True
        elif mday == dst_end and hour < 1:
            in_bst = True

    return 3600 if in_bst else 0


def _last_sunday(year, month):
    """
    Return the day-of-month of the last Sunday in the given year/month.

    Works by starting from day 31 and stepping back until we find a Sunday
    (weekday == 6 in MicroPython's time.gmtime() convention, where 0=Monday).
    Skips days that don't exist in the month gracefully.
    """
    for day in range(31, 0, -1):
        try:
            tm = time.gmtime(time.mktime((year, month, day, 0, 0, 0, 0, 0)))
            if tm[6] == 6:   # Sunday
                return day
        except Exception:
            continue   # day doesn't exist in this month (e.g. 31 in April)
    return None   # should never happen for March or October


def _fmt(tm):
    """Format a time struct as a readable string for logging."""
    return (f"{tm[0]:04d}-{tm[1]:02d}-{tm[2]:02d} "
            f"{tm[3]:02d}:{tm[4]:02d}:{tm[5]:02d}")