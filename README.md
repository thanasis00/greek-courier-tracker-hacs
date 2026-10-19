# Greek Courier Tracker for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/thanasis00/greek-courier-tracker-hacs.svg)](https://github.com/thanasis00/greek-courier-tracker-hacs/releases)
[![License](https://img.shields.io/github/license/thanasis00/greek-courier-tracker-hacs.svg)](LICENSE)

Track shipments from all major Greek courier services in Home Assistant.

**Supported Couriers:** ELTA, ACS, SpeedEx, Box Now, Courier Center, Geniki Taxydromiki, Skroutz Last Mile, Svuum

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
3. Optionally enter your first tracking number (you can add more any time)
4. Set the scan interval (default: 1 hour)

## Adding Tracking Numbers

The courier is detected automatically unless you pick one. Use whichever is handiest:

- **Dashboard card**: type the tracking number, an optional name and an optional courier, then press Add (see below).
- **Shipments to-do list**: add an item such as `SE123456789GR New shoes` to the *Shipments* list (To-do lists in the sidebar, the mobile app or Assist). Delivered shipments are checked off automatically and deleting an item stops tracking it.
- **Actions**: call `greek_courier_tracker.add_tracking` / `greek_courier_tracker.remove_tracking` from scripts and automations:

  ```yaml
  action: greek_courier_tracker.add_tracking
  data:
    tracking_number: SE123456789GR
    name: New shoes          # optional
    courier: elta            # optional, default: auto
  ```

- **Configure**: Settings → Devices & Services → Greek Courier Tracker → ⚙️ Configure, then add, edit or remove tracking numbers or change the scan interval.

## Dashboard Card

The integration ships its own card; there's nothing else to install. Edit a dashboard → Add card → search "Greek Courier Tracker", or add it in YAML:

```yaml
type: custom:greek-courier-tracker-card
```

Each shipment shows its progress (created → in transit → delivered), latest location and time, and its full history on click. The card follows your Home Assistant language (Greek or English).

| Option | Default | Description |
|--------|---------|-------------|
| `title` | Shipments | Card title |
| `show_add_form` | `true` | Show the form for adding tracking numbers |
| `show_delivered` | `true` | Show delivered shipments |
| `entities` | all | Only show these tracking sensors |
| `entry_id` | first entry | Config entry that new numbers are added to |

If the card doesn't show up right after an update, refresh the browser page.

<details>
<summary>Markdown card alternative</summary>

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
    {%- set display_name = tracker.attributes.tracking_name | default(t_num) %}
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

</details>

## Automation Examples

### Get Notified on Every Status Change

This automation notifies you whenever **any** tracked package changes status (moved to next step, delivered, in transit, etc.):

**Automatic (works with all sensors)**

```yaml
alias: Tracking Status Changed
description: Get notified on every package status change
trigger:
  - platform: event
    event_type: state_changed
condition:
  - condition: template
    value_template: >
      {{ trigger.event.data.entity_id.startswith('sensor.greek_courier_tracker_') 
         and trigger.event.data.old_state.state != trigger.event.data.new_state.state
         and trigger.event.data.old_state.state not in ['unknown', 'unavailable']
         and trigger.event.data.new_state.state not in ['unknown', 'unavailable'] }}
action:
  - service: notify.mobile_app_CHANGEME
    data:
      title: 📦 Package Update
      message: >
        {{ trigger.event.data.new_state.attributes.friendly_name }} changed from "{{ trigger.event.data.old_state.state }}" to "{{ trigger.event.data.new_state.state }}"
        ({{ trigger.event.data.new_state.attributes.courier_name }})
      data:
        group: package-tracking
mode: queued
max: 10
```

### Optional: Specific Notifications

#### Delivery Only

```yaml
alias: Package Delivered
description: Notify when a package is delivered
trigger:
  - platform: event
    event_type: state_changed
condition:
  - condition: template
    value_template: >
      {{ trigger.event.data.entity_id.startswith('sensor.greek_courier_tracker_')
         and trigger.event.data.new_state.attributes.delivered == true
         and trigger.event.data.old_state.attributes.delivered == false }}
action:
  - service: notify.mobile_app_CHANGEME
    data:
      title: ✅ Package Delivered!
      message: >
        {{ trigger.event.data.new_state.attributes.friendly_name }} has been delivered!
        Tracking: {{ trigger.event.data.new_state.attributes.tracking_number }}
mode: single
```

#### In Transit Only

```yaml
alias: Package In Transit
description: Notify when a package starts moving
trigger:
  - platform: event
    event_type: state_changed
condition:
  - condition: template
    value_template: >
      {{ trigger.event.data.entity_id.startswith('sensor.greek_courier_tracker_')
         and trigger.event.data.new_state.attributes.status_category == 'in_transit'
         and trigger.event.data.old_state.attributes.status_category != 'in_transit' }}
action:
  - service: notify.mobile_app_CHANGEME
    data:
      title: 🚚 Package In Transit
      message: >
        {{ trigger.event.data.new_state.attributes.friendly_name }} is now on its way!
        Location: {{ trigger.event.data.new_state.attributes.latest_place }}
mode: single
```

## Sensor Attributes

| Attribute | Description |
|-----------|-------------|
| `tracking_number` | The tracking number |
| `tracking_name` | The name you gave the shipment |
| `courier_name` | Full courier name |
| `status` | Current status (translated) |
| `status_category` | delivered, in_transit, created, unknown |
| `latest_date` | Date of latest event |
| `latest_time` | Time of latest event |
| `latest_place` | Location of latest event |
| `events` | All tracking events |
| `delivered` | True if package is delivered |
| `last_updated` | ISO timestamp of last successful API update |

MIT License
