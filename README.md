# HA-Confirmable-actions

A Home Assistant automation blueprint for asking before running an action.
The recipient receives a mobile notification with three buttons:

- **Yes** — run your configured actions.
- **No** — finish without running any actions.
- **Remind me later** — wait for the configured delay, then send the same
  question again. Reminders can repeat until the recipient answers or a
  notification times out.

## Requirements

- Home Assistant **2024.10.0 or newer**.
- The Home Assistant Companion app for Android or iOS, registered with your
  Home Assistant instance and allowed to receive notifications.
- A working `notify.mobile_app_*` action for the recipient's device.

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

Choose a trigger, the recipient's notification action, a title and message,
and the actions to run on **Yes**. Set the reminder delay (default: 15 minutes)
and the response timeout for each notification (default: 24 hours).

Optionally customize the **Accept button label**, **Deny button label**, and
**Reminder button label**. Their defaults are **Yes**, **No**, and
**Remind me later**. Changing these labels only changes the displayed text,
not the response behavior.

Find the exact notification action in **Developer Tools → Actions**, for example
`notify.mobile_app_my_phone`. Use a single Companion app device rather than a
notification group. A device ID or display name is not a notification action.

For example, ask whether to turn off a light every evening:

```yaml
alias: Confirm turning off the living room light
use_blueprint:
  path: confirmable_actions/confirmable_notification.yaml
  input:
    notification_trigger:
      - trigger: time
        at: "22:00:00"
    notification_service: notify.mobile_app_my_phone
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
Replace the notification action and entity with your own.

## Behavior and limitations

- Only **Yes** runs the configured actions. **No** or an unanswered notification
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