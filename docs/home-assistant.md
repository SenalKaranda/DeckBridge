# Home Assistant integration

DeckBridge integrates with Home Assistant via standard MQTT and MQTT
Discovery. There is no custom HA integration to install — once the two
share a broker and Discovery is enabled, the deck shows up in HA as a
device with one trigger entity per key.

## Quick path

1. Point DeckBridge at the same MQTT broker your Home Assistant uses
   (**Settings → MQTT broker** in the DeckBridge web UI).
2. Toggle **Publish Home Assistant Discovery payloads** on (default).
3. Each key on each connected deck appears in Home Assistant as a
   device-trigger entity, ready to wire into automations.

## Two integration directions

### DeckBridge → Home Assistant

Pressing a button fires an MQTT publish that an HA automation can react
to. With Discovery enabled, this is exposed as a device-trigger; without
it, you can still write an `mqtt` trigger by hand against the topic
DeckBridge publishes to.

### Home Assistant → DeckBridge

An HA-managed entity's state is mirrored on the deck. Subscribe a key
to the entity's MQTT state topic (Settings → an entity → its MQTT info,
or the topic your `mqtt` integration publishes on). DeckBridge
re-renders the key whenever HA publishes a state change. Use the
state→icon map on the key to switch icons per state.

## Discovery topic shape

Each Stream Deck appears as a single HA device, with N child
device-trigger entities (one per key). Topics:

```
# Configuration (retained, JSON, one per slot):
homeassistant/device_automation/deckbridge_{serial}_key_{slot}/config

# Press events (str(slot), no retain):
deckbridge/{serial}/key_pressed
```

Example discovery payload for slot 0 of an MK.2:

```json
{
  "automation_type": "trigger",
  "topic": "deckbridge/AL12K1A12345/key_pressed",
  "payload": "0",
  "type": "button_short_press",
  "subtype": "key_0",
  "device": {
    "identifiers": ["deckbridge_AL12K1A12345"],
    "name": "DeckBridge AL12K1A12345",
    "manufacturer": "DeckBridge",
    "model": "Stream Deck MK.2",
    "sw_version": "1.0.0"
  }
}
```

DeckBridge re-publishes the discovery payloads on every broker
reconnect (idempotent — HA deduplicates by topic) and best-effort
retracts them on daemon shutdown by sending an empty retained payload
to each config topic. Toggling Discovery off in Settings takes effect
on the next daemon restart.

## Example: lamp toggle button

The most common pattern is a key that **both publishes on press AND
mirrors the lamp's current state**.

In the DeckBridge editor:

- **Press action**: MQTT publish
  - Topic: `zigbee2mqtt/desk_lamp/set`
  - Payload: `{"state":"TOGGLE"}`
- **State subscription**:
  - Topic: `zigbee2mqtt/desk_lamp`
  - JMESPath: `state`
  - State map:
    - `ON` → bulb-on icon
    - `OFF` → bulb-off icon
  - Default icon: bulb-off icon

Press the key, the lamp toggles; Z2M publishes the new state, the
icon updates. No HA automation needed for this case — the deck talks
to the device directly via the broker. Use HA when you want the
button to trigger something more complex than a single MQTT publish.

## Example: press → HA automation

When the published payload isn't enough on its own (you need
templating, conditional logic, or to call an HA service), drive an HA
automation from the device-trigger entity.

In Home Assistant:

```yaml
automation:
  - alias: "DeckBridge: Bedtime scene on key_0"
    trigger:
      - platform: device
        domain: mqtt
        device_id: <pick the DeckBridge device in the UI>
        type: button_short_press
        subtype: key_0
    action:
      - service: scene.turn_on
        target:
          entity_id: scene.bedtime
```

The device-trigger picker shows up in the HA automation UI once the
discovery payloads are published — no YAML required if you build the
automation through the UI.

## Disabling Discovery

If you'd rather wire automations against bare MQTT topics yourself,
turn off **Publish Home Assistant Discovery payloads** in Settings.
DeckBridge keeps publishing key-press events on the
`deckbridge/{serial}/key_pressed` topic; only the `homeassistant/...`
discovery announcements are suppressed.
