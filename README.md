# ✅ Confirmable Actions

**Let your household decide before an automation acts.** 🤝 Ask a question on
your phones, run an action when someone confirms, or ask again later. ⏰

The blueprint and companion integration work together: the blueprint handles
the question, response, and actions, while the integration delivers actionable
notifications to members of a Home Assistant notification group helper.
Create and manage the group in the UI instead of maintaining a YAML notification
group, and let the first person to respond decide for the whole group. 🏠

- ✅ **Confirm, decline, or remind:** run your actions on **Yes**, stop on **No**,
  or repeat the question after **Remind me later**.
- 📱 **Include your household:** send to a notification group helper, including
  nested groups; responses and clearing apply to the whole request.
- 🎨 **Make it yours:** use templated titles and messages, custom button labels,
  and up to two extra buttons with their own action sequences.

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

Setup registers `confirmable_actions.send_notification` and installs the
blueprint automatically. No `configuration.yaml` edit is required.

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

The installed blueprint is never overwritten, including on integration updates.
To update it, back up any edits, remove
`<config>/blueprints/automation/confirmable_actions/confirmable_notification.yaml`,
then restart Home Assistant. The integration reinstalls its bundled version at
the same path. Existing automations keep using that path; if any fail to load
on restart, reload automations after the integration has started.

## ⚙️ Configuration

Set the reminder delay (default: 15 minutes) and the response timeout for each
notification (default: 24 hours). ⏱️

Optionally customize the **Accept button label**, **Deny button label**, and
**Reminder button label**. Their defaults are **Yes**, **No**, and
**Remind me later**. Changing these labels only changes the displayed text,
not the response behavior. Leave **Deny button label** or **Reminder button
label** blank to hide that button.

Use **Extra button 1 label** and **Extra button 1 actions** (or button 2) to
add a button that runs its own action sequence and finishes the request.
Leave an extra button's label blank to disable it. Android supports at most
three notification buttons: hide **No** and/or **Remind me later** when adding
extra buttons to stay within that limit. iOS supports up to ten. 🤳

The **Notification device** picker lists devices registered through the
Companion app (`mobile_app` integration). Even when using a group, select a
valid group member: Home Assistant validates device actions in unused branches.
The helper takes precedence over a **Notification group** action, which in turn
takes precedence over the device. Sending and clearing use the same destination.
The first response from any member applies to the entire request; the
notification is then cleared on all members. A reminder resends to all members,
not just the device that requested it. 🚦

### 🎯 Blueprint without the integration

For a single device, import the blueprint and select that device; the integration
is not required. You can also use a YAML notification action group instead of a
helper. Leave **Notification group helper** empty and enter an action such as
`notify.family` under **Notification group**. Group members must support
Companion app actionable notifications.

To import it, open **Settings → Automations & scenes → Blueprints → Import
Blueprint** and paste:

```text
https://github.com/pajo30/HA-Confirmable-actions/blob/main/blueprints/automation/confirmable_notification.yaml
```

Alternatively, copy `blueprints/automation/confirmable_notification.yaml` to
`<config>/blueprints/automation/confirmable_actions/confirmable_notification.yaml`
and reload automations.

### 📨 YAML notification action groups

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

- ✅ **Yes** runs the confirmation actions; each enabled extra button runs only
  its own actions. **No** or an unanswered notification
  reaching its timeout ends the request without running them. Swiping away a
  notification is not an answer; the request remains pending until timeout.
- 🔁 After **Remind me later**, the notification is cleared and resent after the
  delay. Each resend starts a fresh response timeout.
- 🧹 Notifications are cleared on a response or timeout on a best-effort basis.
  Clearing can depend on platform restrictions and whether the app was used
  recently; a failed clear does not prevent the confirmed actions from running.
- 🔢 Up to 10 requests can run independently in parallel. Response identifiers are
  unique per request and resend, so a response to an older notification cannot
  confirm a different request or a subsequent reminder.
- 🛑 Pending waits and reminder delays do **not** survive a Home Assistant restart
  or automation reload. Disabling or cancelling the automation also stops its
  pending requests; notifications may remain on the device.
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

The blueprint is also bundled under
`custom_components/confirmable_actions/blueprints/` for integration installs.
Keep both copies identical when making changes.
