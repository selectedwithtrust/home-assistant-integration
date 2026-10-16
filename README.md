# Selected With Trust for Home Assistant

Follow a business on [Selected With Trust](https://selectedwithtrust.com): see whether it is
**open right now**, when it **next opens or closes**, its **logo**, and its **latest announcement**.
Public holidays and the owner's holiday overrides are respected.

## Installation (HACS)

1. HACS → ⋮ → *Custom repositories* → add this repository, category *Integration*.
2. Install **Selected With Trust** and restart Home Assistant.
3. *Settings → Devices & services → Add integration → Selected With Trust*.
4. Type a business name, or paste the link of its page, then pick it from the list.

Add the integration again for each business you want to follow.

## Removal

*Settings → Devices & services → Selected With Trust → ⋮ → Delete.* Nothing else is stored.

## Entities (one device per business)

| Entity | Description |
|---|---|
| `binary_sensor.<name>_open_now` | On while the business is open, evaluated in the **business's** timezone. |
| `sensor.<name>_next_opening_or_closing` | Timestamp of the next open/close moment. |
| `sensor.<name>_latest_announcement` | Title of the newest post; attributes `body`, `published`. |
| `image.<name>_logo` | The business logo (only if it has one). |

## How data updates

The integration polls every 6 hours (opening hours rarely change; the API allows 30 requests per
hour per IP) and uses `ETag`/`If-None-Match`, so unchanged polls are tiny. "Open now" is **not**
polled: it is computed locally from the weekly schedule and flips exactly at the opening/closing
moment.

## Examples

Notify when a shop opens:

```yaml
automation:
  - alias: "Bakery opened"
    triggers:
      - trigger: state
        entity_id: binary_sensor.example_bakery_open_now
        to: "on"
    actions:
      - action: notify.mobile_app_phone
        data: {message: "The bakery just opened"}
```

## Supported functions and use cases

Check opening state in dashboards and automations, get told before closing time, and show a
business's own announcements (special closures are announced as posts, not structured data).

## Known limitations

* One-off closures that are not public holidays only appear in the latest announcement.
* Only businesses that are public on Selected With Trust can be followed.
* Ordering food is not supported yet.

## Troubleshooting

* *Repair "… is no longer listed"*: the business was removed or made private. Delete the entry or
  use *Reconfigure* to follow another business.
* *Entities unavailable*: Selected With Trust was unreachable or rate-limited; it retries automatically.
* Download diagnostics from the device page when reporting a problem.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest --cov=custom_components.selected_with_trust
.venv/bin/mypy custom_components
```

The API contract lives in the SWT repo: `docs/opening-info-api.md`.
