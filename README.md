# ✅ Confirmable Actions

**Let your household decide before an automation acts.** 🤝 Ask a question on
your phones, run an action when someone confirms, or ask again later. ⏰

The blueprint and companion integration work together: the blueprint handles
the question, response, and actions, while the integration delivers actionable
notifications to members of a Home Assistant notification group helper.
Create and manage the group in the UI instead of maintaining a YAML notification
group, and let the first person to respond decide for the whole group. 🏠

- ✅ **Confirm, choose an alternative, or remind:** run confirmation actions on
  **Yes**, optional secondary actions on **No**, or optional reminder actions
  before asking again after **Remind me later**.
- 📱 **Include your household:** send to a notification group helper, including
  nested groups; responses and clearing apply to the whole request.
- 🎨 **Make it yours:** use templated titles and messages and custom labels for
  the three Android-compatible buttons.
- ▶️ **Call from another automation:** create a script from the script blueprint
  and reuse the same confirmation flow without adding a trigger.

**Example:** at bedtime, ask the household whether to turn off the living room
lights. Anyone in the group can confirm, decline, or ask to be reminded. 🌙

## 📋 Requirements

- 🏠 Home Assistant **2026.5 or newer** for the integration and notification
  group helpers. The blueprint alone requires **2024.10.0 or newer**.
- 📲 The Home Assistant Companion app for Android or iOS, registered with your
  Home Assistant instance and allowed to receive notifications.
- 🔔 A working `notify.mobile_app_*` action for each recipient's device.

## 🚀 Get started

### 1️⃣ Install the integration

In Home Assistant Marketplace (or HACS):

1. Open the menu and choose **Custom repositories**.
2. Add `https://github.com/pajo30/HA-Confirmable-actions` as an
   **Integration** repository.
3. Find **Confirmable Actions** and download it. 🎉
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**, search for
   **Confirmable Actions**, and complete setup.

Alternatively, copy `custom_components/confirmable_actions` from this
repository to `<config>/custom_components/confirmable_actions`, restart, and
add the integration through **Devices & services**.

Setup registers `confirmable_actions.send_notification` and installs both the
automation and script blueprints automatically. No `configuration.yaml` edit is
required.

### 2️⃣ Create a confirmation automation

Open **Settings → Automations & scenes → Blueprints**, find **Confirmable
notification with reminders**, and select **Create automation**. ✨

Create a notification group under **Settings → Devices & services → Helpers**,
containing Companion app notification entities. In the blueprint, choose it under
**Notification group helper** and select one of its members under **Notification
device**. Choose a trigger, enter your question, and add the actions to run on
**Yes**. 👆

The integration resolves the helper's members to their mobile app notification
actions, preserving the buttons that Home Assistant's standard
`notify.send_message` action does not forward. Nested notification group
helpers are supported. If a member cannot be resolved, the request fails
rather than sending an incomplete notification.

Installed blueprints are never overwritten, including on integration updates.
To update them, back up any edits and remove the relevant file:
`<config>/blueprints/automation/confirmable_actions/confirmable_notification.yaml`,
or `<config>/blueprints/script/confirmable_actions/confirmable_notification.yaml`.
Then restart Home Assistant. The integration reinstalls its bundled versions at
the same paths. Existing automations and scripts keep using those paths; if any
fail to load on restart, reload automations and scripts after the integration
has started.

### ▶️ Create a callable reminder script

Under **Settings → Automations & scenes → Blueprints**, select **Confirmable
notification with reminders (script)** and choose **Create script**. Configure
the recipient, templated question, button actions, and reminder timing just as
for the automation version; no trigger is needed.

From another automation, use **Script: Turn on** to start the request without
waiting for the recipient:

```yaml
- action: script.turn_on
  target:
    entity_id: script.confirm_turning_off_lights
```

Replace the entity ID with your script. Calling `script.confirm_turning_off_lights`
directly instead waits until the request and its selected actions finish.
The reminder button keeps the script running through the delay and resends.

## ⚙️ Configuration

Set the reminder delay (default: 15 minutes) and the response timeout for each
notification (default: 24 hours). Required input names end in `*`. ⏱️

Reminders are optional. Turn off **Enable reminders** when you only want a
confirmation and secondary button. This hides the reminder button and disables
reminder responses, actions, delays, and resends. The toggle defaults to on to
preserve existing configurations; reminder fields can keep their defaults when
it is off.

**Notification icon** provides an optional Material Design icon picker. Choose
an icon such as `mdi:bell-ring`, `mdi:washing-machine`, or `mdi:cctv`; leave it
blank to keep the default. The selected icon is sent on every reminder as well.
Android uses it as the status bar icon. Supported iOS Companion app versions
show it as a communication notification's sender icon, which requires a
notification title. This does not change the phone's Home Assistant app icon.

**Persistent notification (Android)** is optional and off by default. When
enabled, the notification uses Android's `persistent` and `sticky` options:
tapping it does not dismiss it, and the blueprint still clears it on a button
response or timeout. This cannot enforce persistence on iOS. Android 14+ also
allows some manual dismissal, so it is not a guarantee that a notification
cannot be removed.

**Notification tap destination** optionally opens a dashboard or page when the
notification body is tapped, without adding another button. Use a relative path
such as `/lovelace/cameras`, a dashboard view path such as
`/dashboard-home/security`, or a full URL such as `https://example.com`.
It is sent as Android's `clickAction` and iOS's `url`. Templates are supported
and re-evaluated on every send. Leave it blank for the app's default behavior.
Tapping the body does not run confirmation, secondary, or reminder actions and
does not finish the pending request. Enable persistence on Android to keep the
notification available after navigating.

Optionally customize the **Accept button label**, **Secondary button label**, and
**Reminder button label**. Their defaults are **Yes**, **No**, and
**Remind me later**. Changing these labels only changes the displayed text,
not the response behavior. Leave **Secondary button label** or **Reminder button
label** blank to hide that button.

Use **Actions on secondary button** to configure an optional alternative action
sequence. It runs when that button is pressed, then finishes the request without
running the confirmation actions. Rename its label to something appropriate,
such as **Skip** or **Run a different routine**; **No** remains the default.
The YAML input key is still `deny_label` for compatibility.

Use **Actions on Remind me later** for optional actions that run immediately
on every reminder press when reminders are enabled, after clearing the
notification and before the delay.
Leave either action list empty to keep the original behavior. Timeout does not
run either list. A failure in a button's actions fails the request; a failure in
reminder actions prevents the delay and resend.

Extra buttons have been removed so notifications never exceed Android's
three-button limit. When upgrading, remove any `extra_action_1_label`,
`extra_action_1`, `extra_action_2_label`, and `extra_action_2` inputs from existing
YAML automations. Move any still-needed alternative actions to
`secondary_actions` and rename `deny_label`. Use `reminder_actions` for reminder
side effects. 🤳

The **Notification device** picker lists devices registered through the
Companion app (`mobile_app` integration). Even when using a group, select a
valid group member: Home Assistant validates device actions in unused branches.
The helper takes precedence over the device. Sending and clearing use the same destination.
The first response from any member applies to the entire request; the
notification is then cleared on all members. A reminder resends to all members,
not just the device that requested it. 🚦

### 🎯 Blueprint without the integration

For a single device, import the blueprint, select that device, and leave
**Notification group helper** empty; the integration is not required.
For multiple recipients, install the integration and create a notification group
helper in the UI. YAML notification action groups are no longer supported.

To import it, open **Settings → Automations & scenes → Blueprints → Import
Blueprint** and paste:

```text
https://github.com/pajo30/HA-Confirmable-actions/blob/main/blueprints/automation/confirmable_notification.yaml
```

Alternatively, copy `blueprints/automation/confirmable_notification.yaml` to
`<config>/blueprints/automation/confirmable_actions/confirmable_notification.yaml`
and reload automations.

For the script version, import:

```text
https://github.com/pajo30/HA-Confirmable-actions/blob/main/blueprints/script/confirmable_notification.yaml
```

Or copy `blueprints/script/confirmable_notification.yaml` to
`<config>/blueprints/script/confirmable_actions/confirmable_notification.yaml`
and reload scripts. Neither version needs the integration when sending to a
single device.

### 📨 Templated messages

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

If upgrading from a YAML notification group, create a group helper containing
the Companion app notification entities, remove `notification_group` from the
blueprint inputs, and select the new **Notification group helper** instead.
Keep selecting one group member under **Notification device** for validation.

For example, ask whether to turn off a light every evening: 💡

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

The example path matches the integration's automatic installation and the
manual copy above. If you imported through the UI, create the automation
through the UI to use its assigned blueprint path. Replace the device ID and
entity with your own.

## 🧠 Behavior and limitations

- ✅ **Yes** runs the confirmation actions; the secondary button runs only its
  optional actions and ends the request. Timeout ends the request without
  running any button actions. Swiping away a notification is not an answer;
  the request remains pending until timeout.
- 🔁 After **Remind me later**, the notification is cleared, optional reminder
  actions run, and the notification is resent after the delay. Each resend
  starts a fresh response timeout and re-evaluates the title and message templates.
- 🧹 Notifications are cleared on a response or timeout on a best-effort basis.
  Clearing can depend on platform restrictions and whether the app was used
  recently; a failed clear does not prevent the confirmed actions from running.
- 🔢 Up to 10 requests can run independently in parallel. Response identifiers are
  unique per request and resend, so a response to an older notification cannot
  confirm a different request or a subsequent reminder.
- 🛑 Pending waits and reminder delays do **not** survive a Home Assistant restart
  or an automation/script reload. Disabling or cancelling the automation, or
  stopping the script, also stops its pending requests; notifications may remain
  on the device.
- 🔐 The device must be able to communicate its response to Home Assistant.
  This blueprint is a convenience confirmation, not an authorization mechanism
  for safety-critical actions.
- 📡 Response listening starts after the send action completes. A response made
  while the group send is still in progress can be missed.

See the [Companion app actionable notification documentation](https://companion.home-assistant.io/docs/notifications/actionable-notifications/)
for supported devices and notification behavior. 📚

## 🛠️ Development

The tests use Home Assistant's blueprint validation and script runner. In a
Python 3.12 virtual environment, install the runtime and mobile app dependency:

```sh
pip install 'homeassistant==2024.10.0' 'PyNaCl==1.5.0' 'josepy<2' \
  'hass-nabucasa==0.81.1' 'hassil==1.7.4' 'home-assistant-intents==2024.10.2' \
  'numpy==1.26.4' 'PyTurboJPEG==1.7.5' 'ha-av==10.1.1' 'mutagen==1.47.0' \
  'ha-ffmpeg==3.2.0' 'pymicro-vad==1.0.1' 'pyspeex-noise==1.0.2'
python -m unittest discover -s tests -q
```

The `josepy` constraint keeps the older Home Assistant runtime compatible with
its ACME dependency.

The blueprints are also bundled under
`custom_components/confirmable_actions/blueprints/` for integration installs.
The automation copy is `confirmable_notification.yaml`; the script copy is
`script/confirmable_notification.yaml`. Keep each bundled copy identical to its
counterpart under `blueprints/automation/` or `blueprints/script/`.
