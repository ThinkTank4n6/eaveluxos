# Capturing how the Trimlight app switches on music mode

Trimlight's cloud API has no music controls. The Trimlight Edge app switches
music mode on over the home network, with messages that aren't documented.
If a capture shows what those messages are, a later EaveLuxOS version could
switch the controller to Auxiliary IN by itself, and "Start a music show"
would be one tap.

This is research. It may turn out the messages can't be replayed (for
example, if they're encrypted or signed), and a firmware update could change
them later.

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
messages a second, as Microphone mode may send) are summarized instead of
listed in full.

Read the report before sharing it. It can include the controller's ID or
name. Share `report.md` (and the capture, if you're comfortable) to work out
the messages.
