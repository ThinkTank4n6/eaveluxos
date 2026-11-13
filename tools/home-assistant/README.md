# EaveLuxOS in Home Assistant (and Apple Home)

`eaveluxos.yaml` is a Home Assistant *package*: one file that adds the house
lights as a light with brightness and your patterns as effects, plus a sensor
for the pattern showing now and scripts for the security flash and Return to
schedule.

## Set it up

1. In EaveLuxOS, open **Settings › Webhooks**, tick **Allow webhooks**, and
   copy the token.
2. In Home Assistant, turn on packages if you haven't. In `configuration.yaml`:

   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```

3. In Home Assistant's `secrets.yaml`, add (with your app computer's address,
   shown in EaveLuxOS under **Settings › Phones and other computers**):

   ```yaml
   eaveluxos_token: "PASTE-THE-TOKEN"
   eaveluxos_status_url: "http://192.168.1.50:8787/api/hook/status"
   ```

4. Copy `eaveluxos.yaml` to `config/packages/`, and replace `APP-COMPUTER`
   in it (one place, the `rest_command` address) with the same address
   (`192.168.1.50` in this example).
5. Restart Home Assistant. **House lights** appears, with your patterns in its
   **Effect** list.

Turning the light on uses tonight's scheduled pattern; picking an effect shows
that pattern. Either lasts until the next scheduled change, like the buttons in
EaveLuxOS.

## Apple Home (HomeKit)

Add Home Assistant's **HomeKit Bridge** integration and include
`light.house_lights`. Apple Home then shows the house lights with on, off and
brightness. (Apple Home has no pattern list; use scenes or the EaveLuxOS app
for patterns.)

## What the app sends

`GET /api/hook/status` with the `X-Token` header returns:

```json
{"ok": true, "on": true, "effect": "Christmas", "effect_key": "christmas",
 "reason": "schedule", "source": "Holiday", "until": "11:00 PM",
 "brightness": 200, "speed": 128, "flash": false, "music": false,
 "patterns": [{"key": "christmas", "label": "Christmas"}]}
```

Every other webhook (`on`, `off`, `levels`, `flash`, …) is a `POST` and returns
the same.
