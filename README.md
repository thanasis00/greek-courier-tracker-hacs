# Greek Courier Tracker for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/thanasis00/greek-courier-tracker-hacs.svg)](https://github.com/thanasis00/greek-courier-tracker-hacs/releases)
[![License](https://img.shields.io/github/license/thanasis00/greek-courier-tracker-hacs.svg)](LICENSE)

A comprehensive Home Assistant integration for tracking shipments from **all major Greek courier services** in one place.

## 🚀 Supported Couriers

| Courier | Tracking Format | API Type | Status |
|---------|----------------|----------|--------|
| **ELTA Courier** | SE101046219GR | JSON API | ✅ Working |
| **ACS Courier** | 1234567890 (10 digits) | JSON API | ✅ Working |
| **SpeedEx** | SP12345678, 12 digits | HTML Scraping | ✅ Working |
| **Box Now** | BN12345678 | JSON API | ✅ Working |
| **Courier Center** | CC12345678 | HTML Scraping | ✅ Working |
| **Geniki Taxydromiki** | GT123456789 | HTML Scraping | ✅ Working |

## ✨ Features

- 🔍 **Auto-detection**: Automatically detects courier from tracking number format
- 📦 **Multi-courier**: Track packages from all major Greek couriers
- 🔄 **Auto-refresh**: Configurable scan interval for automatic updates
- 🌐 **Translations**: Greek to English status translations
- 📊 **Full History**: Complete tracking events for each shipment
- 🎨 **Custom Card**: Beautiful Lovelace card included
- 🔔 **Notifications**: Automations for delivery alerts

## 📥 Installation

### Via HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=thanasis00&repository=greek-courier-tracker-hacs&category=integration)

Or manually:
1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add: `https://github.com/thanasis00/greek-courier-tracker-hacs`
3. Category: Integration
4. Search "Greek Courier Tracker" and install
5. Restart Home Assistant

### Manual Installation

```bash
cd /config/custom_components/
git clone https://github.com/thanasis00/greek-courier-tracker-hacs.git greek_courier_tracker
```

Restart Home Assistant.

## ⚙️ Configuration

### Via UI

1. Settings → Devices & Services → Add Integration
2. Search "Greek Courier Tracker"
3. Enter tracking numbers (comma-separated or one per line)
4. Set scan interval (default: 30 minutes)

### Via YAML

```yaml
greek_courier_tracker:
  tracking_numbers:
    - SE101046219GR    # ELTA
    - 1234567890       # ACS
    - SP12345678       # SpeedEx
    - BN12345678       # Box Now
  scan_interval: 30
```

## 📋 Tracking Number Formats

| Courier | Format | Example |
|---------|--------|---------|
| ELTA | `SE` + 9 digits + `GR` | SE101046219GR |
| ELTA | `EL` + 9 digits + `GR` | EL123456789GR |
| ACS | 10 digits | 1234567890 |
| SpeedEx | `SP` + 8-10 digits | SP12345678 |
| SpeedEx | 12 digits | 123456789012 |
| Box Now | `BN` + 8-10 digits | BN12345678 |
| Courier Center | `CC` + 8-10 digits | CC12345678 |
| Geniki | `GT` + 9-11 digits | GT123456789 |

## 🎛️ Sensor Attributes

Each tracking number creates a sensor with:

| Attribute | Type | Description |
|-----------|------|-------------|
| `tracking_number` | string | The tracking number |
| `courier` | string | Courier code (elta, acs, etc.) |
| `courier_name` | string | Full courier name |
| `status` | string | Current status (translated) |
| `status_category` | string | delivered, in_transit, created, unknown |
| `latest_date` | string | Date of latest event |
| `latest_time` | string | Time of latest event |
| `latest_place` | string | Location of latest event |
| `events` | list | All tracking events |
| `delivered` | boolean | True if package is delivered |

## 🎨 Lovelace Card

### Installation

1. Download `greek-courier-card.js` from releases
2. Copy to `/config/www/greek-courier-card.js`
3. Add resource: Settings → Dashboards → Resources → Add
   - URL: `/local/greek-courier-card.js`
   - Type: JavaScript module

### Configuration

```yaml
type: custom:greek-courier-card
title: "My Shipments"
entities:
  - sensor.elta_se101046219gr
  - sensor.acs_1234567890
showAllEvents: true
showCourierLogo: true
```

## 🤖 Automation Examples

### Delivery Notification

```yaml
automation:
  - alias: "Package Delivered"
    trigger:
      - platform: state
        entity_id: sensor.elta_se101046219gr
        attribute: delivered
        to: true
    action:
      - service: notify.mobile_app
        data:
          title: "📦 Package Delivered!"
          message: "Your shipment from ELTA has been delivered!"
```

### Status Change Alert

```yaml
automation:
  - alias: "Shipment Status Changed"
    trigger:
      - platform: state
        entity_id: 
          - sensor.elta_se101046219gr
          - sensor.acs_1234567890
    action:
      - service: notify.mobile_app
        data:
          title: "📦 Shipment Update"
          message: >
            {{ state_attr(trigger.entity_id, 'courier_name') }}:
            {{ state_attr(trigger.entity_id, 'tracking_number') }}
            is now {{ states(trigger.entity_id) }}
```

### Daily Summary

```yaml
automation:
  - alias: "Daily Shipping Summary"
    trigger:
      - platform: time
        at: "18:00:00"
    action:
      - service: notify.mobile_app
        data:
          title: "📦 Shipping Summary"
          message: >
            {% for state in states.sensor %}
              {% if state.entity_id.startswith('sensor.elta_') or 
                    state.entity_id.startswith('sensor.acs_') or
                    state.entity_id.startswith('sensor.speedex_') %}
                {{ state.name }}: {{ state.state }}
              {% endif %}
            {% endfor %}
```

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| Tracking not found | Verify number format, wait for registration |
| Sensor shows "Unknown" | Check internet, try refresh |
| API rate limited | Increase scan interval |
| HTML scraping fails | Courier may have changed website |

## 🧪 Testing

Run the test suite:

```bash
cd custom_components/greek_courier_tracker
python3 test_standalone.py
```

Expected output:
```
============================================================
GREEK COURIER TRACKER - TEST SUITE
============================================================
1. TRACKING NUMBER DETECTION TESTS: PASSED
2. ELTA PATTERN MATCHING TESTS: PASSED
3. LIVE API TESTS: PASSED
============================================================
ALL TESTS PASSED! ✓
============================================================
```

## 📚 API Reference

### ELTA Courier
```
POST https://www.elta-courier.gr/track.php
Body: number={TRACKING_NUMBER}&s=0
Response: JSON with tracking events
```

### Box Now
```
POST https://api-production.boxnow.gr/api/v1/parcels:track
Body: {"parcelId": "{TRACKING_NUMBER}"}
Response: JSON with parcel events
```

### ACS Courier
```
GET https://api.acscourier.net/api/parcels/search/{TRACKING_NUMBER}
Headers: x-encrypted-key (dynamic token)
Response: JSON with status history
```

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) file.

## 🙏 Credits

- Data from official courier APIs and websites
- Inspired by [Greek-Courier-API](https://github.com/DanielPikilidis/Greek-Courier-API)
- Pattern detection from [Greek-Parcel-CLI](https://github.com/eliac7/Greek-Parcel-CLI)

---

**Made with ❤️ for the Greek Home Assistant community**
