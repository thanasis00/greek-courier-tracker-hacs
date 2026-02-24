# Greek Courier Tracker for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/thanasis00/greek-courier-tracker-hacs.svg)](https://github.com/thanasis00/greek-courier-tracker-hacs/releases)
[![License](https://img.shields.io/github/license/thanasis00/greek-courier-tracker-hacs.svg)](LICENSE)

Track shipments from all major Greek courier services in Home Assistant.

**Supported Couriers:** ELTA, ACS, SpeedEx, Box Now, Courier Center, Geniki Taxydromiki

## Installation

### Via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=thanasis00&repository=greek-courier-tracker-hacs&category=integration)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add: `https://github.com/thanasis00/greek-courier-tracker-hacs`
3. Category: Integration
4. Search "Greek Courier Tracker" and install
5. Restart Home Assistant

### Manual

```bash
cd /config/custom_components/
git clone https://github.com/thanasis00/greek-courier-tracker-hacs.git greek_courier_tracker
```

Restart Home Assistant.

## Configuration

1. Settings → Devices & Services → Add Integration
2. Search "Greek Courier Tracker"
3. Enter tracking numbers (comma-separated or one per line)
4. Set scan interval (default: 30 minutes)

### Managing Tracking Numbers

Settings → Devices & Services → Greek Courier Tracker → ⚙️ Configure

- Add new tracking numbers with custom names
- Edit name and settings (like "stop when delivered")
- Delete individual tracking numbers

## Lovelace Card

Auto-discovery card (requires [auto-entities](https://github.com/thomasloven/hass-lovelace-auto-entities)):

```yaml
type: markdown
title: "📦 Active Shipments"
content: >
  {% set trackers = states.sensor | selectattr('entity_id', 'search', 'greek_courier_tracker_') | list %}
  
  {% if trackers | length == 0 %}
    No shipments are currently being tracked.
  {% else %}
    {% for tracker in trackers %}
    * **{{ tracker.name | replace('Greek Courier Tracker ', '') }}**: {{ tracker.state }}
    {% endfor %}
  {% endif %}
```

Enhanced card:

```yaml
type: markdown
title: "📦 Active Shipments"
content: >
  {% set trackers = states.sensor | selectattr('entity_id', 'search', 'greek_courier_tracker_') | list %}
  {% if trackers | length == 0 %}
  *No shipments are currently being tracked.*
  {% else %}
  {% for tracker in trackers %}
  {%- set t_num = tracker.attributes.tracking_number | default('N/A') -%}
  {%- set c_name = tracker.attributes.courier_name | default('Unknown Courier') -%}
  {%- set f_name = tracker.name -%}
  {%- if 'Greek Courier Tracker' in f_name -%}
  {%- set display_name = t_num -%}
  {%- else -%}
  {%- set display_name = f_name | replace(t_num, '') | trim | title -%}
  {%- set display_name = display_name if display_name | length > 0 else t_num -%}
  {%- endif %}
  <div style="border: 1px solid var(--divider-color, #444); padding: 16px; border-radius: 10px; margin-bottom: 16px; background-color: var(--secondary-background-color, rgba(0,0,0,0.1));">
  <h3 style="margin-top: 0px; margin-bottom: 12px;">📦 {{ display_name }}</h3>
  <b>Courier:</b> {{ c_name }}<br>
  <b>Tracking:</b> {{ t_num }}<br>
  <b>Status:</b> {{ tracker.state }}
  {%- if tracker.attributes.latest_place %}<br>
  <b>Location:</b> {{ tracker.attributes.latest_place }}
  {%- endif %}
  {%- if tracker.attributes.latest_date %}<br>
  <b>Updated:</b> {{ tracker.attributes.latest_date }} @ {{ tracker.attributes.latest_time }}
  {%- endif %}
  </div>
  {% endfor %}
  {% endif %}
```

## Automation Examples

Delivery notification:

```yaml
automation:
  - alias: "Package Delivered"
    trigger:
      - platform: state
        entity_id: sensor.greek_courier_tracker_1234567890
        attribute: delivered
        to: true
    action:
      - service: notify.mobile_app
        data:
          title: "Package Delivered!"
          message: "Your shipment has been delivered!"
```

## Sensor Attributes

| Attribute | Description |
|-----------|-------------|
| `tracking_number` | The tracking number |
| `courier_name` | Full courier name |
| `status` | Current status (translated) |
| `status_category` | delivered, in_transit, created, unknown |
| `latest_date` | Date of latest event |
| `latest_time` | Time of latest event |
| `latest_place` | Location of latest event |
| `events` | All tracking events |
| `delivered` | True if package is delivered |

MIT License
