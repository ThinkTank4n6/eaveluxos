# Capturing how the Trimlight app talks to the controller

Trimlight's cloud API has no music controls. The Trimlight Edge app runs
music mode over the home network, with messages that aren't documented. A
capture in November 2026 (firmware 1.17.77) showed what they are, and
EaveLuxOS 4.1 uses them for **Music from this computer** (see
`eaveluxos/lanlink.py` and the Manual).

A second capture the same day showed the lights on and off and leaving
Music. A new capture is still useful to learn how many music patterns there
are, or to see what changed if a firmware update breaks **Test connection**.

## What you need

- The controller's IP address on your network. Your router's device list
  shows it.
- One way to record the phone's traffic:
  - **Android:** the free **PCAPdroid** app. Choose the Trimlight Edge app as
    the target and save to a PCAP file. No root needed.
  - **iPhone:** a Mac with Xcode's command-line tools. Plug in the phone,
    then `rvictl -s <phone UDID>` and record the new `rvi0` interface with
    Wireshark or `tcpdump -i rvi0 -w capture.pcap`. Run `rvictl -x <UDID>`
    afterward.
  - **Any phone:** if a computer can see the traffic between the phone and
    the controller (a switch mirror port, or the router or access point both
    connect through, if it lets you run `tcpdump`), record there.

## Record

1. Start recording. Keep a text file open and write one line for every step,
   with the time from the clock of the computer or phone that's recording:

       20:15:05 opened Trimlight app
       20:15:30 opened Music

2. Do these steps, about 10 seconds apart, writing each one down:
   1. Open the Trimlight Edge app and your controller.
   2. Open **Music**.
   3. Choose **Auxiliary IN**.
   4. Choose a different music pattern.
   5. Set **Music Sensitivity** all the way down, then all the way up.
   6. Choose **Microphone**, play music near the phone for about 20 seconds,
      then stay quiet for 10.
   7. Leave Music.
   8. Turn the lights off, then on, in the Trimlight app.
3. Stop recording.

Don't re-pair the controller or change its Wi-Fi during a capture: pairing
traffic can include your Wi-Fi password.

## Summarize

Python 3.10 or newer, no other software:

    python3 summarize_capture.py capture.pcap --controller 192.168.1.50 \
        --marks marks.txt --out report.md

The report lists only home-network traffic: discovery broadcasts, every
conversation with the controller, message shapes with the bytes that change
between them, and a timeline lined up with your notes. Live streams (many
messages a second, as Microphone mode sends) are summarized instead of
listed in full.

Since 4.1 it also puts Trimlight's own messages back together and decodes
them under **Decoded Trimlight messages**: the greeting, keep-alives, "set
the controller's clock", "everything the controller holds" (with the names
in it), "music settings" (input, music pattern, sensitivity), "sound
levels", "lights off" / "lights on" and "back to normal (out of music
mode)", with anything not yet understood shown as "request 0x…" or "mode
0x… (not known yet)" and its bytes. Those unknown requests are what a new capture is for.

**Tip for the marks:** use the clock of the device that records (the phone,
with PCAPdroid). The November capture's notes were about 30 seconds behind
the phone, which made the steps harder to match.

### A short capture for what's still unknown

Leave about 20 seconds between steps and write each one down:

1. Open the Trimlight Edge app and your controller.
2. Open **Music**, then scroll to the **last** music pattern and choose it.
3. Leave Music.

The report's "music pattern" number for step 2 is the last one (counting
from 0).

Read the report before sharing it. It can include the controller's ID or
name. Share `report.md` (and the capture, if you're comfortable) to work out
the messages.
