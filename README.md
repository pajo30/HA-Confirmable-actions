# HA-Confirmable-actions

A Home Assistant automation blueprint for asking before running an action.
One device or a notification group receives a mobile notification with three
default buttons:

- **Yes** — run your configured actions.
- **No** — finish without running any actions.
- **Remind me later** — wait for the configured delay, then send the same
  question again. Reminders can repeat until the recipient answers or a
  notification times out.

Titles and messages support templates for conditional content. Two optional
extra buttons can each run a separate Home Assistant action sequence.

## Requirements

- Home Assistant **2024.10.0 or newer**.
- The Home Assistant Companion app for Android or iOS, registered with your
  Home Assistant instance and allowed to receive notifications.
- A working `notify.mobile_app_*` action for each recipient's device.

## Installation

1. Open **Settings → Automations & scenes → Blueprints → Import Blueprint**.
2. Paste this URL:

   ```text
   https://github.com/pajo30/HA-Confirmable-actions/blob/main/blueprints/automation/confirmable_notification.yaml
   ```

3. Preview and import, then select **Create automation**.

Alternatively, copy
`blueprints/automation/confirmable_notification.yaml` from this repository to
`<config>/blueprints/automation/confirmable_actions/confirmable_notification.yaml`
and reload automations.

## Configuration

Choose a trigger, the recipient's **Notification device**, a title and message,
and the actions to run on **Yes**. Set the reminder delay (default: 15 minutes)
and the response timeout for each notification (default: 24 hours).

Optionally customize the **Accept button label**, **Deny button label**, and
**Reminder button label**. Their defaults are **Yes**, **No**, and
**Remind me later**. Changing these labels only changes the displayed text,
not the response behavior. Leave **Deny button label** or **Reminder button
label** blank to hide that button.

Use **Extra button 1 label** and **Extra button 1 actions** (or button 2) to
add a button that runs its own action sequence and finishes the request.
Leave an extra button's label blank to disable it. Android supports at most
three notification buttons: hide **No** and/or **Remind me later** when adding
extra buttons to stay within that limit. iOS supports up to ten.

The **Notification device** picker lists devices registered through the
Companion app (`mobile_app` integration). Select one device, and optionally enter
a **Notification group** action such as `notify.family`. When a group is supplied,
it takes precedence over the device picker. Still select a valid group member
in the device picker: Home Assistant validates device actions even in unused
branches. Both sending and clearing use the same destination. A group must contain only
Companion app notification services that support actionable notifications.
The first response received from any member applies to the entire request;
the notification is then cleared on all members. A reminder resends to all
members, not just the device that requested it.

For example, configure a notification group in Home Assistant's
`configuration.yaml` (merge this with any existing `notify` configuration),
then restart Home Assistant:

```yaml
notify:
  - platform: group
    name: family
    services:
      - action: mobile_app_phone_one
      - action: mobile_app_phone_two
```

Use the suffixes of your actual `notify.mobile_app_*` actions for the members.
In the blueprint, set **Notification group** to `notify.family`.

**Notification title** and **Notification message** accept Home Assistant
templates, including `if`/`else` conditions and state lookups. They are evaluated
on every send, so a reminder can reflect changed conditions. For example:

```yaml
notification_message: >-
  {% if is_state('light.living_room', 'on') %}
    The living room light is still on. Turn it off?
  {% else %}
    The living room light is off. Run the evening routine anyway?
  {% endif %}
```

If upgrading from the notification-action text field, edit each existing
automation and select its **Notification device** again. For YAML automations,
replace `notification_service` with `notification_device`, using the device's
registry ID rather than a `notify.mobile_app_*` action or display name.

For example, ask whether to turn off a light every evening:

```yaml
alias: Confirm turning off the living room light
use_blueprint:
  path: confirmable_actions/confirmable_notification.yaml
  input:
    notification_trigger:
      - trigger: time
        at: "22:00:00"
    notification_device: your_mobile_app_device_id
    notification_title: Living room
    notification_message: Turn off the living room light?
    accept_label: Turn it off
    deny_label: Leave it on
    reminder_label: Ask me later
    confirmation_actions:
      - action: light.turn_off
        target:
          entity_id: light.living_room
    reminder_delay:
      minutes: 15
    response_timeout:
      hours: 24
```

The example path matches the manual installation above. If you imported through
the UI, create the automation through the UI to use its assigned blueprint path.
Replace the device ID and entity with your own.

## Behavior and limitations

- **Yes** runs the confirmation actions; each enabled extra button runs only
  its own actions. **No** or an unanswered notification
  reaching its timeout ends the request without running them. Swiping away a
  notification is not an answer; the request remains pending until timeout.
- After **Remind me later**, the notification is cleared and resent after the
  delay. Each resend starts a fresh response timeout.
- Notifications are cleared on a response or timeout on a best-effort basis.
  Clearing can depend on platform restrictions and whether the app was used
  recently; a failed clear does not prevent the confirmed actions from running.
- Up to 10 requests can run independently in parallel. Response identifiers are
  unique per request and resend, so a response to an older notification cannot
  confirm a different request or a subsequent reminder.
- Pending waits and reminder delays do **not** survive a Home Assistant restart
  or automation reload. Disabling or cancelling the automation also stops its
  pending requests; notifications may remain on the device.
- The device must be able to communicate its response to Home Assistant.
  This blueprint is a convenience confirmation, not an authorization mechanism
  for safety-critical actions.

See the [Companion app actionable notification documentation](https://companion.home-assistant.io/docs/notifications/actionable-notifications/)
for supported devices and notification behavior.

## Development

The tests use Home Assistant's blueprint validation and script runner. In a
Python 3.12 virtual environment, install the runtime and mobile app dependency:

```sh
pip install 'homeassistant==2024.10.0' 'PyNaCl==1.5.0' 'josepy<2'
python -m unittest discover -s tests -q
```

The `josepy` constraint keeps the older Home Assistant runtime compatible with
its ACME dependency.