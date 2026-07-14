"""Keyword library for the my_lg test suite.

This module is the "keyword-driven" layer: every function here is a
single, named, reusable action or check ("keyword") that knows how to
talk to the real my_lg/thinqconnect/Home Assistant objects. The BDD
step definitions in tests/step_defs/ never touch my_lg internals
directly - they only call these keywords and pass results through
pytest-bdd's `target_fixture` / context object. This keeps the Gherkin
step wiring thin and the actual test logic in one reusable place, so a
new scenario can be composed from existing keywords without duplicating
setup code.

Naming convention: `given_...` builds/arranges state, `when_...`
performs the action under test, `then_...`/`assert_...` verifies an
outcome. This mirrors Given/When/Then but keywords are plain functions,
independent of any particular feature file wording.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from thinqconnect import ThinQAPIErrorCodes, ThinQAPIException
from thinqconnect.devices.air_conditioner import AirConditionerDevice
from thinqconnect.devices.washer import WasherDevice

import my_lg
import my_lg.climate as climate_mod
import my_lg.sensor as sensor_mod
from my_lg import SmartThinqHybridRuntimeData
from my_lg.coordinator_pat import PatDeviceCoordinator
from my_lg.wideq.core_exceptions import InvalidCredentialError as WideqInvalidCredentialError


# --------------------------------------------------------------------
# Generic scenario context
# --------------------------------------------------------------------


@dataclass
class World:
    """Mutable scratch space shared between keywords within one scenario.

    Equivalent to a pytest-bdd "context" object: Given-keywords stash
    whatever Then-keywords need to inspect here, instead of every step
    definition threading its own bag of fixtures through the test.
    """

    hass: Any = None
    runtime_data: SmartThinqHybridRuntimeData | None = None
    coordinator: PatDeviceCoordinator | None = None
    entity: Any = None
    exception: Exception | None = None
    result: Any = None
    extra: dict = field(default_factory=dict)


def new_world() -> World:
    """Create a fresh, empty scenario context."""
    return World(hass=MagicMock())


# --------------------------------------------------------------------
# Fake device / profile builders
# --------------------------------------------------------------------


def given_pat_ac_device(status: dict | None = None) -> AirConditionerDevice:
    """Build a PAT AirConditionerDevice wrapper with a minimal real profile.

    `status` is applied via the SDK's own `update_status`, exercising
    the real thinqconnect parsing path rather than a hand-rolled fake.
    """
    profile = {
        "property": {
            "airConJobMode": {
                "currentJobMode": {
                    "type": "enum",
                    "mode": ["r", "w"],
                    "value": {"r": ["COOL", "HEAT", "FAN"], "w": ["COOL", "HEAT", "FAN"]},
                }
            },
            "operation": {
                "airConOperationMode": {
                    "type": "enum",
                    "mode": ["r", "w"],
                    "value": {"r": ["POWER_ON", "POWER_OFF"], "w": ["POWER_ON", "POWER_OFF"]},
                }
            },
            "temperature": {
                "currentTemperature": {"type": "range", "mode": ["r"]},
                "targetTemperature": {"type": "range", "mode": ["r", "w"]},
                "minTemperature": {"type": "range", "mode": ["r"]},
                "maxTemperature": {"type": "range", "mode": ["r"]},
                "unit": "C",
            },
            "powerSave": {
                "powerSaveEnabled": {
                    "type": "boolean",
                    "mode": ["r", "w"],
                    "value": {"r": [False, True], "w": [False, True]},
                }
            },
        }
    }
    device = AirConditionerDevice(
        thinq_api=AsyncMock(),
        device_id="ac-device-id",
        device_type="DEVICE_AIR_CONDITIONER",
        model_name="RAC_TEST",
        alias="테스트에어컨",
        reportable=True,
        group_id=None,
        profile=profile,
    )
    if status is not None:
        device.update_status(status)
    return device


def given_pat_washer_device(status: list[dict] | None = None) -> WasherDevice:
    """Build a PAT WasherDevice wrapper (ConnectMainDevice with a MAIN sub-device)."""
    profile = {
        "property": [
            {
                "runState": {
                    "currentState": {
                        "type": "enum",
                        "mode": ["r"],
                        "value": {"r": ["RUNNING", "POWER_OFF", "END", "ERROR"]},
                    }
                },
                "timer": {
                    "remainHour": {"type": "range", "mode": ["r"]},
                    "remainMinute": {"type": "range", "mode": ["r"]},
                },
                "cycle": {"cycleCount": {"type": "range", "mode": ["r"]}},
                "location": {"locationName": "MAIN"},
            }
        ]
    }
    device = WasherDevice(
        thinq_api=AsyncMock(),
        device_id="washer-device-id",
        device_type="DEVICE_WASHER",
        model_name="TLSD_TEST",
        alias="테스트세탁기",
        reportable=True,
        group_id=None,
        profile=profile,
    )
    if status is not None:
        device.update_status(status)
    return device


def given_pat_coordinator(world: World, device) -> PatDeviceCoordinator:
    """Wrap a PAT device in a PatDeviceCoordinator, stored on the world.

    `async_request_refresh` is replaced with an AsyncMock: it internally
    goes through HA's real Debouncer/async_run_hass_job machinery, which
    needs a fully working HomeAssistant instance to await successfully -
    more than these unit tests need, since what they check is that the
    right PAT/wideq command was dispatched, not that the follow-up
    refresh completes.
    """
    coordinator = PatDeviceCoordinator(world.hass, None, AsyncMock(), device)
    coordinator.async_request_refresh = AsyncMock()
    world.coordinator = coordinator
    return coordinator


def given_runtime_data(world: World, wideq_client: Any = "UNSET") -> SmartThinqHybridRuntimeData:
    """Create a SmartThinqHybridRuntimeData, stored on the world.

    `wideq_client` defaults to a MagicMock (wideq available); pass None
    explicitly to simulate wideq being unavailable.
    """
    client = MagicMock() if wideq_client == "UNSET" else wideq_client
    runtime_data = SmartThinqHybridRuntimeData(client, MagicMock())
    world.runtime_data = runtime_data
    return runtime_data


def given_fan_swing_device(fan_speeds=None, vertical_steps=None, horizontal_steps=None):
    """Build a fake wideq AirConditionerFanSwingDevice with configurable capabilities."""
    device = MagicMock()
    device.fan_speeds = fan_speeds or []
    device.vertical_step_modes = vertical_steps or []
    device.horizontal_step_modes = horizontal_steps or []
    return device


# --------------------------------------------------------------------
# "When" keywords - actions under test
# --------------------------------------------------------------------


def when_command_fails_with_not_connected(world: World) -> None:
    """Simulate a command that fails with PAT's NOT_CONNECTED_DEVICE, via mark_unreachable."""
    world.coordinator.mark_unreachable()


def when_status_updates_successfully(world: World) -> None:
    """Simulate a successful status update (push or poll) clearing unreachable."""
    world.coordinator.mark_reachable()


def when_building_climate_entity(world: World, fan_swing_device=None) -> Any:
    """Construct the AC climate entity under test, stored on the world."""
    entity = climate_mod.SmartThinqHybridClimateEntity(
        world.coordinator, fan_swing_device, world.runtime_data
    )
    entity.hass = world.hass
    world.entity = entity
    return entity


def when_setting_temperature(world: World, temperature: float) -> None:
    """Call async_set_temperature on the entity under test."""
    asyncio.run(world.entity.async_set_temperature(temperature=temperature))


def when_temperature_set_then_entity_removed(world: World, temperature: float) -> None:
    """Schedule the debounced temperature task, then remove the entity.

    Runs entirely inside one asyncio.run() call so the real Task created
    by async_set_temperature (via hass.async_create_task) and its
    cancellation (via async_will_remove_from_hass) happen on the same
    live event loop - a MagicMock hass would just return a MagicMock
    instead of a real Task, which wouldn't actually exercise
    Task.cancel() at all.
    """

    async def _run():
        world.hass.async_create_task = lambda coro: asyncio.ensure_future(coro)
        world.entity.hass = world.hass
        # async_set_temperature calls async_write_ha_state() before the
        # debounce, which normally requires a real entity_id (assigned
        # when EntityPlatform adds the entity to hass) - not relevant to
        # what this scenario checks (task scheduling/cancellation), so
        # it's stubbed out rather than standing up a full entity platform.
        world.entity.async_write_ha_state = MagicMock()
        await world.entity.async_set_temperature(temperature=temperature)
        world.extra["pending_task"] = world.entity._pending_temperature_task
        await world.entity.async_will_remove_from_hass()
        # Let the event loop process the cancellation before we inspect it.
        await asyncio.sleep(0)

    asyncio.run(_run())


def then_pending_temperature_task_was_cancelled(world: World) -> bool:
    task = world.extra.get("pending_task")
    return task is not None and task.cancelled()


def when_setting_hvac_mode_with_pat_not_connected(world: World) -> None:
    """Make the PAT power-off call raise NOT_CONNECTED_DEVICE, then call async_set_hvac_mode.

    Exercises the shared PatCoordinatorEntity.async_send_pat_command
    helper end-to-end (not just the coordinator's mark_unreachable
    directly), to catch a regression in that shared implementation
    itself rather than only in the lower-level flag it sets.
    """
    from homeassistant.components.climate import HVACMode
    from thinqconnect import ThinQAPIErrorCodes, ThinQAPIException

    world.entity.device.set_air_con_operation_mode = AsyncMock(
        side_effect=ThinQAPIException(ThinQAPIErrorCodes.NOT_CONNECTED_DEVICE, "offline", {})
    )
    try:
        asyncio.run(world.entity.async_set_hvac_mode(HVACMode.OFF))
    except Exception as exc:  # pylint: disable=broad-except
        world.exception = exc


def when_wideq_call_raises_invalid_credential(world: World) -> None:
    """Drive _async_send_wideq_command with a call that raises InvalidCredentialError."""

    async def failing_call():
        raise WideqInvalidCredentialError("0110 - invalid credential")

    asyncio.run(
        world.entity._async_send_wideq_command(failing_call, description="테스트 명령")
    )


def when_wideq_call_succeeds(world: World) -> None:
    """Drive _async_send_wideq_command with a call that succeeds."""

    async def succeeding_call():
        return None

    asyncio.run(
        world.entity._async_send_wideq_command(succeeding_call, description="테스트 명령")
    )


def when_retrying_wideq_command_while_reauth_needed(world: World) -> None:
    """Retry a wideq command while wideq_reauth_needed is already True.

    Unlike when_wideq_call_succeeds, this stores any raised exception on
    the world instead of letting it propagate, so a Then-step can assert
    that the guard swallowed it (rather than the test itself erroring
    out before reaching that assertion).
    """

    async def should_not_be_called():
        raise AssertionError("wideq command should have been skipped by the guard")

    try:
        asyncio.run(
            world.entity._async_send_wideq_command(
                should_not_be_called, description="테스트 명령"
            )
        )
    except Exception as exc:  # pylint: disable=broad-except
        world.exception = exc


def when_filter_poll_raises_invalid_credential(world: World) -> None:
    """Run AcFilterCoordinator._async_update_data() against a failing wideq device."""
    wideq_device = MagicMock()
    wideq_device.device_info.name = "테스트에어컨"
    wideq_device.async_get_filter_info = AsyncMock(
        side_effect=WideqInvalidCredentialError("0110")
    )
    coordinator = sensor_mod.AcFilterCoordinator(
        world.hass, None, wideq_device, world.runtime_data
    )
    try:
        asyncio.run(coordinator._async_update_data())
    except Exception as exc:  # pylint: disable=broad-except
        world.exception = exc


def when_pat_setup_entry_is_called(world: World, wideq_connects: bool, pat_discovery_fails: bool):
    """Drive my_lg.async_setup_entry() with a controllable wideq/PAT outcome.

    Patches _async_try_connect_wideq and async_discover_pat_devices for
    the duration of the call so the real network-touching code paths in
    those two functions are never exercised - everything else in
    async_setup_entry runs for real.
    """
    from unittest.mock import patch

    async def fake_try_connect_wideq(hass, entry, session):
        if not wideq_connects:
            return None
        client = MagicMock()
        # devices must be a real (empty) list, not an auto-attribute
        # MagicMock, or `for x in wideq_client.devices` in
        # async_setup_entry raises TypeError ("not iterable").
        client.devices = []
        return client

    async def fake_discover_pat_devices(pat_api):
        if pat_discovery_fails:
            raise RuntimeError("PAT device list unavailable")
        return []

    entry = MagicMock()
    entry.data = {
        "pat_access_token": "dummy-token",
        "pat_client_id": "dummy-client-id",
        "pat_country": "KR",
    }
    entry.entry_id = "test-entry-id"
    world.extra["entry"] = entry

    # async_setup_entry awaits this directly (the final step, forwarding
    # setup to each platform); MagicMock's default return value isn't
    # awaitable, so it must be an AsyncMock explicitly.
    world.hass.config_entries.async_forward_entry_setups = AsyncMock()

    with patch.object(my_lg, "_async_try_connect_wideq", fake_try_connect_wideq), patch.object(
        my_lg, "async_discover_pat_devices", fake_discover_pat_devices
    ):
        try:
            world.result = asyncio.run(my_lg.async_setup_entry(world.hass, entry))
        except Exception as exc:  # pylint: disable=broad-except
            world.exception = exc


def when_wideq_reconnects_and_refresh_runs(world: World) -> None:
    """Simulate the periodic wideq refresh task discovering wideq is reachable again."""
    from unittest.mock import patch

    reconnected_client = MagicMock()
    reconnected_client.close = AsyncMock()

    async def fake_try_connect_wideq(hass, entry, session):
        return reconnected_client

    hass = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    scheduled = {}

    def fake_create_task(coro):
        scheduled["coro"] = coro
        return MagicMock()

    hass.async_create_task = fake_create_task
    entry = MagicMock()
    entry.entry_id = "test-entry-id"
    world.extra["hass"] = hass
    world.extra["entry"] = entry

    with patch.object(my_lg, "_async_try_connect_wideq", fake_try_connect_wideq):

        async def _refresh_when_wideq_is_none():
            client = await my_lg._async_try_connect_wideq(hass, entry, MagicMock())
            if client is not None:
                await client.close()
                hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))

        asyncio.run(_refresh_when_wideq_is_none())

    if "coro" in scheduled:
        asyncio.run(scheduled["coro"])
    world.extra["reload_called"] = hass.config_entries.async_reload.called
    world.extra["reload_call_args"] = hass.config_entries.async_reload.call_args


# --------------------------------------------------------------------
# "Then"/assertion keywords
# --------------------------------------------------------------------


def then_coordinator_should_be_available(world: World) -> bool:
    return world.coordinator.available is True


def then_coordinator_should_be_unavailable(world: World) -> bool:
    return world.coordinator.available is False


def then_supported_features_include(world: World, feature) -> bool:
    return bool(world.entity._attr_supported_features & feature)


def then_target_temperature_step_is(world: World, expected_step: float) -> bool:
    return world.entity._attr_target_temperature_step == expected_step


def then_runtime_data_reauth_needed_is(world: World, expected: bool) -> bool:
    return world.runtime_data.wideq_reauth_needed is expected


def then_no_exception_was_raised(world: World) -> bool:
    return world.exception is None


def then_exception_is_instance_of(world: World, exc_type) -> bool:
    return isinstance(world.exception, exc_type)


def then_mqtt_coordinator_handle_status_called(world: World) -> bool:
    coordinator = world.extra["mqtt_coordinators"]["known-device-id"]
    return coordinator.handle_mqtt_status.called


def cleanup_mqtt_loop(world: World) -> None:
    """Stop the background event loop started by when_mqtt_message_received."""
    loop = world.extra.get("loop")
    if loop is not None:
        loop.call_soon_threadsafe(loop.stop)


# --------------------------------------------------------------------
# Washer "remaining time" sensor keywords
# --------------------------------------------------------------------


def given_washer_coordinator_with_remain_time(world: World, hour, minute) -> None:
    """Build a washer PatDeviceCoordinator with the given remainHour/remainMinute."""
    device = given_pat_washer_device(
        status=[
            {
                "timer": {"remainHour": hour, "remainMinute": minute},
                "location": {"locationName": "MAIN"},
            }
        ]
    )
    given_pat_coordinator(world, device)


def when_reading_washer_remain_time_native_value(world: World) -> None:
    """Read WasherRemainTimeSensor.native_value, catching any exception."""
    entity = sensor_mod.WasherRemainTimeSensor(world.coordinator)
    try:
        world.result = entity.native_value
    except Exception as exc:  # pylint: disable=broad-except
        world.exception = exc


def then_native_value_is_not_none(world: World) -> bool:
    return world.result is not None


def then_native_value_is_none(world: World) -> bool:
    return world.result is None


# --------------------------------------------------------------------
# AC filter sensor availability keywords
# --------------------------------------------------------------------


def given_filter_coordinator_with_data(world: World) -> None:
    """Build an AcFilterRemainSensor backed by a filter coordinator that has data."""
    ac_device = given_pat_ac_device(
        status={
            "airConJobMode": {"currentJobMode": "COOL"},
            "operation": {"airConOperationMode": "POWER_ON"},
        }
    )
    pat_coordinator = given_pat_coordinator(world, ac_device)

    filter_coordinator = MagicMock()
    filter_coordinator.data = {"use_time": 38, "max_time": 720, "remain_percent": 94}
    filter_coordinator.last_update_success = True
    filter_coordinator.async_add_listener = MagicMock(return_value=lambda: None)
    world.extra["filter_coordinator"] = filter_coordinator

    world.entity = sensor_mod.AcFilterRemainSensor(pat_coordinator, filter_coordinator)


def given_filter_coordinator_with_no_data(world: World) -> None:
    """Build an AcFilterRemainSensor backed by a filter coordinator with no data yet."""
    ac_device = given_pat_ac_device(
        status={
            "airConJobMode": {"currentJobMode": "COOL"},
            "operation": {"airConOperationMode": "POWER_ON"},
        }
    )
    pat_coordinator = given_pat_coordinator(world, ac_device)

    filter_coordinator = MagicMock()
    filter_coordinator.data = None
    filter_coordinator.last_update_success = False
    filter_coordinator.async_add_listener = MagicMock(return_value=lambda: None)
    world.extra["filter_coordinator"] = filter_coordinator

    world.entity = sensor_mod.AcFilterRemainSensor(pat_coordinator, filter_coordinator)


def when_filter_coordinator_marked_failed(world: World) -> None:
    """Simulate the filter coordinator's most recent poll failing (data unchanged)."""
    world.extra["filter_coordinator"].last_update_success = False


def then_filter_sensor_available(world: World) -> bool:
    return world.entity.available is True


def then_filter_sensor_unavailable(world: World) -> bool:
    return world.entity.available is False


# --------------------------------------------------------------------
# device_router matching keywords
# --------------------------------------------------------------------


def given_pat_device_entries(world: World, alias: str, device_type: str) -> None:
    """Store a single-entry fake PAT /devices list on the world."""
    world.extra["pat_device_entries"] = [
        {"deviceId": "some-id", "deviceInfo": {"deviceType": device_type, "alias": alias}}
    ]


def when_matching_wideq_to_pat(world: World, wideq_type, alias: str) -> None:
    """Call match_wideq_to_pat and store the result on the world."""
    from my_lg.device_router import match_wideq_to_pat

    world.result = match_wideq_to_pat(
        wideq_type, alias, world.extra["pat_device_entries"]
    )


def then_match_result_is_not_none(world: World) -> bool:
    return world.result is not None


def then_match_result_is_none(world: World) -> bool:
    return world.result is None


# --------------------------------------------------------------------
# MQTT robustness keywords
# --------------------------------------------------------------------


def _run_mqtt_message(world: World, payload: bytes) -> None:
    """Shared implementation for feeding a raw payload through the MQTT handler."""
    from my_lg.mqtt import ThinQMQTT

    coordinator = MagicMock()
    coordinator.device.alias = "테스트기기"
    coordinators = {"known-device-id": coordinator}
    world.extra["mqtt_coordinators"] = coordinators

    mqtt = ThinQMQTT(world.hass, MagicMock(), "client-id", coordinators)
    world.extra["mqtt"] = mqtt

    loop = asyncio.new_event_loop()
    world.extra["loop"] = loop
    world.hass.loop = loop
    import threading

    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    world.extra["loop_thread"] = thread

    try:
        mqtt._on_message_received("topic", payload, False, 0, False)
    except Exception as exc:  # pylint: disable=broad-except
        world.exception = exc

    import time

    time.sleep(0.2)


def when_mqtt_receives_malformed_utf8(world: World) -> None:
    _run_mqtt_message(world, b"\xff\xfe\x00\x01invalid utf8 payload")


def when_mqtt_receives_malformed_json(world: World) -> None:
    _run_mqtt_message(world, b"{not valid json")


def when_mqtt_receives_valid_device_status(world: World) -> None:
    import json

    payload = json.dumps(
        {"deviceId": "known-device-id", "pushType": "DEVICE_STATUS", "report": {"foo": "bar"}}
    ).encode()
    _run_mqtt_message(world, payload)


# --------------------------------------------------------------------
# wideq-optional setup outcome keywords
# --------------------------------------------------------------------


def then_setup_succeeded_without_exception(world: World) -> bool:
    return world.exception is None and world.result is True


def then_integration_reload_was_called(world: World) -> bool:
    return bool(world.extra.get("reload_called"))


# --------------------------------------------------------------------
# config_flow unique_id / duplicate-prevention keywords
# --------------------------------------------------------------------


def when_wideq_login_succeeds_in_config_flow(world: World, username: str) -> None:
    """Drive SmartThinqHybridFlowHandler.async_step_user with a mocked login.

    Patches ClientAsync.auth_info_from_user_login (so no real network
    call happens) and the flow's own async_set_unique_id /
    _abort_if_unique_id_configured (so this stays a unit test of "did
    our code call these with the right value", not an integration test
    of HA's config-entry storage).
    """
    from unittest.mock import patch

    import my_lg.config_flow as config_flow_mod

    flow = config_flow_mod.SmartThinqHybridFlowHandler()
    flow.hass = world.hass

    async def fake_auth_info_from_user_login(*args, **kwargs):
        return {"refresh_token": "dummy-refresh-token", "oauth_url": "https://example.invalid"}

    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    flow.async_step_pat = AsyncMock(return_value={"type": "form", "step_id": "pat"})
    world.extra["flow"] = flow

    with patch.object(
        config_flow_mod.ClientAsync,
        "auth_info_from_user_login",
        fake_auth_info_from_user_login,
    ):
        world.result = asyncio.run(
            flow.async_step_user({"username": username, "password": "dummy-pw"})
        )


def then_flow_unique_id_was_set_to(world: World, expected: str) -> bool:
    flow = world.extra["flow"]
    return flow.async_set_unique_id.await_args.args[0] == expected


def then_flow_checked_already_configured(world: World) -> bool:
    return world.extra["flow"]._abort_if_unique_id_configured.called


