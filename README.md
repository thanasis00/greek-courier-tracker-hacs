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

Later, Configure → Settings lets you change the scan interval and remove delivered shipments automatically a number of days after delivery (off by default).

## Adding Tracking Numbers

The courier is detected automatically unless you pick one: couriers whose number format matches are tried first, and once found, only that courier is asked on later updates. Use whichever is handiest:

- **Dashboard card**: type the tracking number, an optional name and an optional courier, then press Add (see below).
- **Shipments to-do list**: add an item such as `SE123456789GR New shoes` to the *Shipments* list (To-do lists in the sidebar, the mobile app or Assist). Delivered shipments are checked off automatically and deleting an item stops tracking it.
- **Actions**: call `greek_courier_tracker.add_tracking` / `greek_courier_tracker.remove_tracking` from scripts and automations:

  ```yaml
  action: greek_courier_tracker.add_tracking
  data:
    tracking_number: SE123456789GR
    name: New shoes          # optional
    courier: elta            # optional, default: auto
    owner: person.maria      # optional, default: whoever runs the action
  ```

- **Configure**: Settings → Devices & Services → Greek Courier Tracker → ⚙️ Configure, then add, edit or remove tracking numbers or change the scan interval.

### Owners

Every shipment belongs to the person who added it, so the [notification blueprint](#ready-made-blueprint) can notify only their phones. If you add a package for someone else, pick them as the owner:

- **Dashboard card**: the owner dropdown next to Add (shown when more than one person uses Home Assistant). Click the owner of a shipment to change it later.
- **Configure**: the Owner field when adding or editing a tracking number.
- **Actions**: `owner` in `greek_courier_tracker.add_tracking`, or `greek_courier_tracker.set_owner` later:

  ```yaml
  action: greek_courier_tracker.set_owner
  data:
    tracking_number: SE123456789GR
    owner: person.maria      # leave out for a shared shipment
  ```

Shipments without an owner are shared: every phone gets their notifications. Shipments added before owners existed, and those added by automations, are shared until you pick an owner.

## Dashboard Card

The integration ships its own card; there's nothing else to install. Edit a dashboard → Add card → search "Greek Courier Tracker", or add it in YAML:

```yaml
type: custom:greek-courier-tracker-card
```

Each shipment shows its progress (created → in transit → delivered), latest location and time, the expected delivery when the courier gives one (Skroutz Last Mile), and its full history on click. The card follows your Home Assistant language (Greek or English).

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

## Notifications

### Ready-made blueprint

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fthanasis00%2Fgreek-courier-tracker-hacs%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fgreek_courier_tracker%2Fshipment_status_notification.yaml)

Import the blueprint, pick your phones, and you get a notification whenever a shipment changes status (or only when it's delivered).

Turn on **Only their own shipments** and each phone only gets the shipments of its owner, the person signed in to the Companion app on it (see [Owners](#owners)). Shared shipments still go to every phone. To mix both, for example only your own shipments on your phone but everything on another, create two automations from the blueprint.

### `greek_courier_tracker_status_changed` event

The integration fires this event whenever a tracked shipment changes status, so your own automations don't need templates:

```yaml
alias: Package delivered
trigger:
  - platform: event
    event_type: greek_courier_tracker_status_changed
    event_data:
      delivered: true
action:
  - service: notify.mobile_app_CHANGEME
    data:
      title: ✅ Package delivered
      message: "{{ trigger.event.data.name }} ({{ trigger.event.data.courier_name }})"
```

| Event data | Description |
|------------|-------------|
| `name`, `tracking_number`, `entity_id` | Which shipment |
| `courier`, `courier_name` | Courier code and name |
| `status`, `old_status` | New and previous status, in your Home Assistant language |
| `status_en` | New status in English |
| `status_category` | delivered, in_transit, created, unknown |
| `delivered` | True when delivered |
| `location` | Location of the latest event |
| `estimated_delivery` | Expected delivery, when the courier gives one |
| `owner`, `owner_user_id` | Name and user ID of the owner (empty for shared shipments) |
| `owner_device_ids` | Companion app devices of the owner (empty for shared shipments) |

## Sensor Attributes

| Attribute | Description |
|-----------|-------------|
| `tracking_number` | The tracking number |
| `tracking_name` | The name you gave the shipment |
| `owner`, `owner_user_id` | Name and user ID of the owner (empty for shared shipments) |
| `courier_name` | Full courier name |
| `tracking_url` | The shipment on the courier's own website |
| `status` | Current status in English |
| `status_el` | Current status in Greek |
| `status_category` | delivered, in_transit, created, unknown |
| `estimated_delivery` | Expected delivery, when the courier gives one |
| `latest_date` | Date of latest event |
| `latest_time` | Time of latest event |
| `latest_place` | Location of latest event |
| `events` | All tracking events |
| `delivered` | True if package is delivered |
| `last_updated` | ISO timestamp of last successful API update |

The sensor state is the status in your Home Assistant language (Greek or English).

MIT License
