"""Step definitions binding every tests/features/*.feature file.

Every step body is a thin wrapper that calls into tests/keywords.py -
the keyword-driven layer. No my_lg/thinqconnect/Home Assistant object
is touched directly here; that keeps the Gherkin-to-code wiring
readable and means new scenarios can usually be built by composing
existing keywords rather than writing new glue code.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from thinqconnect import ThinQAPIException

from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers.update_coordinator import UpdateFailed

import keywords as kw
from my_lg.wideq import DeviceType as WideqDeviceType
from my_lg.wideq.core_exceptions import InvalidCredentialError as WideqInvalidCredentialError

# Bind every feature file under tests/features/ to this step module.
scenarios("../features/device_availability.feature")
scenarios("../features/climate_wideq_fallback.feature")
scenarios("../features/wideq_reauth.feature")
scenarios("../features/wideq_optional_setup.feature")
scenarios("../features/washer_sensors.feature")
scenarios("../features/filter_sensor_availability.feature")
scenarios("../features/device_router_matching.feature")
scenarios("../features/mqtt_robustness.feature")
scenarios("../features/config_flow_dedup.feature")
scenarios("../features/washer_course.feature")
scenarios("../features/humidifier_switch_pat_commands.feature")
scenarios("../features/mqtt_push_status.feature")
scenarios("../features/climate_wideq_retry_branches.feature")
scenarios("../features/wideq_reauth_binary_sensor.feature")
scenarios("../features/mqtt_subscribe_failure_counting.feature")
scenarios("../features/mqtt_connection_lifecycle.feature")
scenarios("../features/washer_course_matching.feature")
scenarios("../features/climate_restore_state.feature")
scenarios("../features/humidifier_switch_properties.feature")
scenarios("../features/coordinator_pat_discovery.feature")
scenarios("../features/climate_fan_swing_success.feature")
scenarios("../features/pat_command_retry.feature")
scenarios("../features/pat_command_verify.feature")
scenarios("../features/climate_atomic_power_on.feature")

@pytest.fixture
def world():
    """Fresh scenario context, and MQTT event-loop cleanup afterward."""
    w = kw.new_world()
    yield w
    kw.cleanup_mqtt_loop(w)


_WIDEQ_TYPE_MAP = {"AC": WideqDeviceType.AC, "WASHER": WideqDeviceType.WASHER}

# PAT 에러 코드 문자열 (ThinQAPIErrorCodes는 str, Enum이라 아래 문자열
# 값과 exc.code == ThinQAPIErrorCodes.XXX 비교가 그대로 성립한다)
_PAT_ERROR_CODES = {
    "NOT_CONNECTED_DEVICE": "1222",
    "INVALID_COMMAND_ERROR": "2207",
    "COMMAND_NOT_SUPPORTED_IN_MODE": "2305",
}


# --------------------------------------------------------------------
# Given
# --------------------------------------------------------------------


@given("정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다")
def given_ac_coordinator_normal(world):
    device = kw.given_pat_ac_device(
        status={
            "airConJobMode": {"currentJobMode": "COOL"},
            "operation": {"airConOperationMode": "POWER_ON"},
        }
    )
    # Mocked so PAT-fallback scenarios can assert exactly what climate.py
    # sends, without exercising thinqconnect's own profile-to-payload
    # attribute-command translation (that's the SDK's concern, not ours).
    device.set_cool_target_temperature_c = AsyncMock()
    device.set_heat_target_temperature_c = AsyncMock()
    device.set_air_con_operation_mode = AsyncMock()
    device.set_current_job_mode = AsyncMock()
    kw.given_pat_coordinator(world, device)
    kw.given_runtime_data(world)


@given(parsers.parse("wideq 팬/스윙 연동 기기(풍속 {n1:d}단계, 수직 스텝 {n2:d}단계)가 있다"))
def given_fan_swing_device(world, n1, n2):
    world.extra["fan_swing_device"] = kw.given_fan_swing_device(
        fan_speeds=[f"SPEED_{i}" for i in range(n1)],
        vertical_steps=[f"STEP_{i}" for i in range(n2)],
    )

@given(parsers.parse("wideq 수평 스텝 전용 팬/스윙 연동 기기(풍속 {n1:d}단계, 수평 스텝 {n2:d}단계)가 있다"))
def given_horizontal_only_fan_swing_device(world, n1, n2):
    world.extra["fan_swing_device"] = kw.given_fan_swing_device(
        fan_speeds=[f"SPEED_{i}" for i in range(n1)],
        horizontal_steps=[f"HSTEP_{i}" for i in range(n2)],
    )

@given("이 코디네이터와 wideq 기기로 climate 엔티티를 만든다")
@when("이 코디네이터와 wideq 기기로 climate 엔티티를 만든다")
def build_climate_entity_with_wideq(world):
    kw.when_building_climate_entity(world, world.extra.get("fan_swing_device"))


@given("wideq 기기 없이 climate 엔티티를 만든다")
@when("wideq 기기 없이 climate 엔티티를 만든다")
def build_climate_entity_without_wideq(world):
    kw.when_building_climate_entity(world, None)


@given("wideq 명령이 InvalidCredentialError로 실패한다")
@when("wideq 명령이 InvalidCredentialError로 실패한다")
def wideq_command_fails_invalid_credential(world):
    kw.when_wideq_call_raises_invalid_credential(world)


@given("빈 runtime_data가 있다")
def given_empty_runtime_data(world):
    kw.given_runtime_data(world)


@given(parsers.parse("남은시간이 {hour:d}시간 {minute:d}분인 세탁기 PAT 코디네이터가 있다"))
def given_washer_remain_time(world, hour, minute):
    kw.given_washer_coordinator_with_remain_time(world, hour, minute)


@given("남은시간이 빈 문자열인 세탁기 PAT 코디네이터가 있다")
def given_washer_remain_time_empty_string(world):
    kw.given_washer_coordinator_with_remain_time(world, "", "")


@given("필터 코디네이터에 use_time과 max_time 데이터가 이미 있다")
def given_filter_data_present(world):
    kw.given_filter_coordinator_with_data(world)


@given("필터 코디네이터에 데이터가 전혀 없다")
def given_filter_data_absent(world):
    kw.given_filter_coordinator_with_no_data(world)


@given(parsers.parse('PAT 기기 목록에 별칭 "{alias}", 타입 {device_type}인 항목이 있다'))
def given_pat_device_entries(world, alias, device_type):
    kw.given_pat_device_entries(world, alias, device_type)


@given("세탁기가 꺼진 상태로 코스 코디네이터가 만들어져 있다")
def given_washer_course_coordinator_off(world):
    kw.given_runtime_data(world)
    kw.given_washer_course_coordinator(world, "POWER_OFF")


@given("세탁기가 동작 중인 상태로 코스 코디네이터가 만들어져 있다")
def given_washer_course_coordinator_running(world):
    kw.given_runtime_data(world)
    kw.given_washer_course_coordinator(world, "RUNNING")


@given("정상 상태의 제습기 엔티티가 있다")
def given_dehumidifier_entity(world):
    kw.given_dehumidifier_entity(world)


@given("정상 상태의 에너지 절약 스위치 엔티티가 있다")
def given_ac_energy_saving_switch_entity(world):
    kw.given_ac_energy_saving_switch_entity(world)


@given("이 runtime_data로 재인증 필요 센서를 만든다")
def given_wideq_reauth_sensor(world):
    kw.given_wideq_reauth_sensor(world)


@given("기기 목록 없이 MQTT 매니저가 있다")
def given_mqtt_manager_no_devices(world):
    kw.given_mqtt_manager(world)


@given("기기 2대와 연결된 클라이언트를 가진 MQTT 매니저가 있다")
def given_mqtt_manager_two_devices_connected(world):
    kw.given_mqtt_manager(world, device_ids=["dev-1", "dev-2"], with_connected_client=True)


@given("기기 2대를 가졌지만 클라이언트가 연결되지 않은 MQTT 매니저가 있다")
def given_mqtt_manager_two_devices_not_connected(world):
    kw.given_mqtt_manager(world, device_ids=["dev-1", "dev-2"], with_connected_client=False)


@given("기기 목록 없이 연결된 클라이언트를 가진 MQTT 매니저가 있다")
def given_mqtt_manager_no_devices_connected(world):
    kw.given_mqtt_manager(world, device_ids=[], with_connected_client=True)


@given("wideq 클라이언트 자체가 없는 세탁기 코스 센서 설정이 있다")
def given_washer_course_setup_no_wideq_client(world):
    kw.given_washer_course_sensor_setup(world, wideq_devices=None, wideq_client_present=False)


@given("wideq 기기 목록이 None인 세탁기 코스 센서 설정이 있다")
def given_washer_course_setup_devices_none(world):
    kw.given_washer_course_sensor_setup(world, wideq_devices=None, wideq_client_present=True)


@given("wideq 기기 목록에 에어컨만 있는 세탁기 코스 센서 설정이 있다")
def given_washer_course_setup_only_ac(world):
    ac_info = kw.given_wideq_device_info(WideqDeviceType.AC, "테스트에어컨")
    kw.given_washer_course_sensor_setup(world, wideq_devices=[ac_info])


@given("wideq 기기 목록에 별칭이 다른 세탁기가 있는 코스 센서 설정이 있다")
def given_washer_course_setup_mismatched_alias(world):
    washer_info = kw.given_wideq_device_info(WideqDeviceType.WASHER, "다른세탁기")
    kw.given_washer_course_sensor_setup(world, wideq_devices=[washer_info])


@given("wideq 기기 목록에 별칭이 일치하는 세탁기가 있는 코스 센서 설정이 있다")
def given_washer_course_setup_matching_alias(world):
    washer_info = kw.given_wideq_device_info(WideqDeviceType.WASHER, "테스트세탁기")
    kw.given_washer_course_sensor_setup(world, wideq_devices=[washer_info])

@given("전원이 꺼져 있고 이전 모드가 송풍(FAN)으로 남아있는 에어컨 코디네이터가 있다")
def given_ac_coordinator_powered_off_with_stale_fan_mode(world):
    kw.given_ac_coordinator_powered_off_with_stale_fan_mode(world)
    
# --------------------------------------------------------------------
# When
# --------------------------------------------------------------------


@given("이 기기에 보낸 명령이 오프라인으로 실패한다")
@when("이 기기에 보낸 명령이 오프라인으로 실패한다")
def command_fails_offline(world):
    kw.when_command_fails_with_not_connected(world)


@when("상태 갱신이 성공적으로 도착한다")
def status_update_succeeds(world):
    kw.when_status_updates_successfully(world)


@when(parsers.parse("목표 온도를 {temperature:g}도로 설정한다"))
def set_target_temperature(world, temperature):
    kw.when_setting_temperature(world, temperature)


@when(parsers.parse("목표 온도를 {temperature:g}도로 설정한 직후 엔티티가 제거된다"))
def set_temperature_then_remove_entity(world, temperature):
    kw.when_temperature_set_then_entity_removed(world, temperature)


@when(parsers.parse("재인증이 필요한 상태에서 풍속을 {fan_mode}로 설정한다"))
def set_fan_mode_while_reauth_needed(world, fan_mode):
    kw.when_setting_fan_mode_while_reauth_needed(world, fan_mode)


@when(parsers.parse("재인증이 필요한 상태에서 목표 온도를 {temperature:g}도로 설정하고 디바운스가 끝날 때까지 기다린다"))
def set_temperature_while_reauth_needed(world, temperature):
    kw.when_setting_temperature_while_reauth_needed_and_debounce_elapses(world, temperature)


@when("PAT 전원 제어가 NOT_CONNECTED_DEVICE로 실패하는 상태에서 hvac_mode를 off로 설정한다")
def set_hvac_mode_with_pat_not_connected(world):
    kw.when_setting_hvac_mode_with_pat_not_connected(world)


@when("재인증이 필요한 상태에서 wideq 명령을 다시 시도한다")
def retry_wideq_command_while_reauth_needed(world):
    kw.when_retrying_wideq_command_while_reauth_needed(world)


@when("AC 필터 조회가 InvalidCredentialError로 실패한다")
def filter_poll_fails_invalid_credential(world):
    kw.when_filter_poll_raises_invalid_credential(world)


@when("필터 코디네이터의 마지막 업데이트가 실패로 표시된다")
def filter_coordinator_marked_failed(world):
    kw.when_filter_coordinator_marked_failed(world)


@when("세탁기 남은시간 센서의 native_value를 읽는다")
def read_washer_remain_time(world):
    kw.when_reading_washer_remain_time_native_value(world)


@when(parsers.parse('wideq {wideq_type} 타입, 별칭 "{alias}"으로 매칭을 시도한다'))
def match_wideq_to_pat(world, wideq_type, alias):
    kw.when_matching_wideq_to_pat(world, _WIDEQ_TYPE_MAP[wideq_type], alias)


@when(parsers.parse("wideq 연결 {wideq_outcome}, PAT 기기 조회 {pat_outcome} 상태로 통합구성요소를 설정한다"))
def setup_entry_with_outcomes(world, wideq_outcome, pat_outcome):
    kw.when_pat_setup_entry_is_called(
        world,
        wideq_connects=(wideq_outcome == "성공"),
        pat_discovery_fails=(pat_outcome == "실패"),
    )


@when("wideq가 다시 연결 가능해진 상태에서 주기적 재연결 작업이 실행된다")
def wideq_reconnects(world):
    kw.when_wideq_reconnects_and_refresh_runs(world)


@when("깨진 UTF-8 바이트 페이로드로 MQTT 메시지를 수신한다")
def mqtt_receives_bad_utf8(world):
    kw.when_mqtt_receives_malformed_utf8(world)


@when("잘못된 JSON 페이로드로 MQTT 메시지를 수신한다")
def mqtt_receives_bad_json(world):
    kw.when_mqtt_receives_malformed_json(world)


@when("알려진 기기의 정상적인 DEVICE_STATUS 메시지를 수신한다")
def mqtt_receives_valid_status(world):
    kw.when_mqtt_receives_valid_device_status(world)


@when(parsers.parse("PAT 세탁기 상태가 {run_state}로 바뀐다"))
def pat_washer_run_state_changes(world, run_state):
    kw.when_pat_washer_run_state_changes(world, run_state)


@when(parsers.parse('wideq가 코스 "{current_course}", 스마트코스 "{current_smartcourse}"를 반환한다'))
def wideq_poll_returns_course(world, current_course, current_smartcourse):
    kw.when_wideq_poll_returns_course(world, current_course, current_smartcourse)


@when("wideq 코스 조회가 데이터 없이(None) 끝난다")
def wideq_poll_returns_none_for_course(world):
    kw.when_wideq_poll_returns_none_for_course(world)


@when("wideq 코스 조회가 InvalidCredentialError로 실패한다")
def wideq_poll_raises_invalid_credential_for_course(world):
    kw.when_wideq_poll_raises_invalid_credential_for_course(world)


@when("wideq 코스 조회가 예상치 못한 예외로 실패한다")
def wideq_poll_raises_generic_error_for_course(world):
    kw.when_wideq_poll_raises_generic_error_for_course(world)


@when("재인증이 필요한 상태에서 코스 갱신을 시도한다")
def course_update_attempted_while_reauth_needed(world):
    kw.when_course_update_attempted_while_reauth_needed(world)


@when(parsers.parse('wideq 로그인이 "{username}"으로 성공한다'))
def wideq_login_succeeds(world, username):
    kw.when_wideq_login_succeeds_in_config_flow(world, username)


@when(parsers.parse("제습기의 {action} 동작을 호출한다"))
def dehumidifier_action_invoked(world, action):
    kw.when_dehumidifier_action_invoked(world, action)


@when(parsers.parse("제습기의 {action} 동작이 {error_name}로 실패한다"))
def dehumidifier_pat_command_fails(world, action, error_name):
    kw.when_dehumidifier_pat_command_fails(world, action, _PAT_ERROR_CODES[error_name])


@when(parsers.parse("스위치의 {action} 동작을 호출한다"))
def switch_action_invoked(world, action):
    kw.when_switch_action_invoked(world, action)


@when(parsers.parse("스위치의 {action} 동작이 {error_name}로 실패한다"))
def switch_pat_command_fails(world, action, error_name):
    kw.when_switch_pat_command_fails(world, action, _PAT_ERROR_CODES[error_name])


@when(parsers.parse("MQTT push로 현재 온도 {temperature:g}가 도착한다"))
def mqtt_status_applied(world, temperature):
    kw.when_mqtt_status_applied(world, temperature)


@when("빈 MQTT push 페이로드가 도착한다")
def empty_mqtt_status_applied(world):
    kw.when_empty_mqtt_status_applied(world)


@when("wideq 명령이 NotConnectedError로 실패한다")
def wideq_call_raises_not_connected(world):
    kw.when_wideq_call_raises_not_connected(world)


@when("wideq 세션이 만료됐다가 재시도가 성공한다")
def wideq_session_expires_then_retry_succeeds(world):
    kw.when_wideq_session_expires_then_retry_succeeds(world)


@when("wideq 세션 갱신 자체가 실패한다")
def wideq_session_refresh_itself_fails(world):
    kw.when_wideq_session_refresh_itself_fails(world)


@when("wideq가 일시적 에러 코드로 실패했다가 재시도에서 성공한다")
def wideq_transient_error_then_retry_succeeds(world):
    kw.when_wideq_transient_error_then_retry_succeeds(world)


@when("wideq가 일시적 에러 코드로 계속 실패한다")
def wideq_transient_error_persists(world):
    kw.when_wideq_transient_error_persists(world)


@when("wideq가 일시적이지 않은 에러 코드로 실패한다")
def wideq_non_transient_error(world):
    kw.when_wideq_non_transient_error(world)


@when("runtime_data에 재인증이 필요하다고 표시한다")
def mark_reauth_needed(world):
    world.runtime_data.mark_wideq_reauth_needed()


@when("빈 결과 목록으로 구독 실패 개수를 센다")
def count_subscribe_failures_empty(world):
    kw.when_counting_subscribe_failures(world, [])


@when("이미_구독됨_에러만 있는 결과 목록으로 구독 실패 개수를 센다")
def count_subscribe_failures_already_subscribed(world):
    kw.when_counting_subscribe_failures(world, [ThinQAPIException("1207", "이미 구독됨", {})])


@when("다른_thinq_에러가_섞인 결과 목록으로 구독 실패 개수를 센다")
def count_subscribe_failures_other_thinq_error(world):
    kw.when_counting_subscribe_failures(
        world,
        [
            ThinQAPIException("1207", "이미 구독됨", {}),
            ThinQAPIException("9999", "다른 에러", {}),
        ],
    )


@when("typeerror가_섞인 결과 목록으로 구독 실패 개수를 센다")
def count_subscribe_failures_type_error(world):
    kw.when_counting_subscribe_failures(world, [TypeError("잘못된 타입"), None])


@when("MQTT 연결을 시도해서 성공한다")
def mqtt_connect_succeeds(world):
    kw.when_mqtt_connect_succeeds(world)


@when("MQTT 연결 시도가 클라이언트 없이 끝난다")
def mqtt_connect_returns_no_client(world):
    kw.when_mqtt_connect_returns_no_client(world)


@when("MQTT 연결 시도 중 예외가 발생한다")
def mqtt_connect_raises(world):
    kw.when_mqtt_connect_raises(world)


@when("구독을 시작한다")
def start_subscribes(world):
    kw.when_start_subscribes_called(world)


@when("구독을 해제한다")
def end_subscribes(world):
    kw.when_end_subscribes_called(world)


@when("MQTT 연결을 끊는다")
def mqtt_disconnect(world):
    kw.when_mqtt_disconnect_called(world)


@when("클라이언트 연결 해제가 실패하는 상태에서 MQTT 연결을 끊는다")
def mqtt_disconnect_with_client_failure(world):
    kw.when_mqtt_client_disconnect_raises_then_disconnect_called(world)


@when("구독을 갱신한다")
def refresh_subscribe(world):
    kw.when_refresh_subscribe_called(world)


@when("코스 센서를 만든다")
def build_washer_course_sensor(world):
    kw.when_building_washer_course_sensor(world)


@when("모델 정보 로드가 실패하는 상태로 코스 센서를 만든다")
def build_washer_course_sensor_load_failure(world):
    kw.when_building_washer_course_sensor(world, init_device_info_result="failure")


@when("모델 정보 로드 중 예외가 발생하는 상태로 코스 센서를 만든다")
def build_washer_course_sensor_load_error(world):
    kw.when_building_washer_course_sensor(world, init_device_info_result="error")

@when(parsers.parse('이전 상태(풍속 {fan_mode}, 스윙 {swing_mode}, 온도 {temperature})로 복원된다'))
def entity_restored_with_last_state(world, fan_mode, swing_mode, temperature):
    kw.when_entity_restored_with_last_state(
        world,
        fan_mode=None if fan_mode == "없음" else fan_mode,
        swing_mode=None if swing_mode == "없음" else swing_mode,
        temperature=None if temperature == "없음" else temperature,
    )


@when("이전 상태 없이 복원이 시도된다")
def entity_restored_with_no_last_state(world):
    kw.when_entity_restored_with_no_last_state(world)


@when("PAT 기기 목록 조회 결과가 없다")
def discover_pat_devices_empty(world):
    kw.when_discovering_pat_devices(world, None)


@when("PAT 기기 목록에 지원 기기와 미지원 기기가 섞여 있다")
def discover_pat_devices_mixed(world):
    kw.when_discovering_pat_devices(
        world,
        [
            {"deviceId": "ac-1", "deviceInfo": {"deviceType": "DEVICE_AIR_CONDITIONER"}},
            {"deviceId": "fridge-1", "deviceInfo": {"deviceType": "DEVICE_REFRIGERATOR"}},
        ],
    )


@when("지원하지 않는 타입으로 PAT 기기를 생성한다")
def build_pat_device_unsupported_type(world):
    kw.when_building_pat_device(world, "DEVICE_REFRIGERATOR")


@when("에어컨 타입으로 PAT 기기를 생성한다")
def build_pat_device_ac(world):
    kw.when_building_pat_device(world, "DEVICE_AIR_CONDITIONER")


@when("프로필 로드가 실패하는 상태로 에어컨 타입 PAT 기기를 생성한다")
def build_pat_device_profile_error(world):
    kw.when_building_pat_device(world, "DEVICE_AIR_CONDITIONER", profile_result="error")


@when("REST 폴백 상태 조회가 성공한다")
def rest_fallback_succeeds(world):
    kw.when_rest_fallback_update_succeeds(world)


@when("REST 폴백이 빈 상태를 반환한다")
def rest_fallback_empty(world):
    kw.when_rest_fallback_returns_empty_status(world)


@when("REST 폴백 호출이 실패한다")
def rest_fallback_raises(world):
    kw.when_rest_fallback_raises(world)

@when(parsers.parse('풍속을 "{fan_mode}"로 정상 설정한다'))
def set_fan_mode_normally(world, fan_mode):
    kw.when_setting_fan_mode(world, fan_mode)


@when(parsers.parse('스윙을 "{swing_mode}"로 정상 설정한다'))
def set_swing_mode_normally(world, swing_mode):
    kw.when_setting_swing_mode(world, swing_mode)


@when("세션 만료 후 재시도가 InvalidCredentialError로 실패한다")
def session_expires_then_retry_raises_invalid_credential(world):
    kw.when_wideq_session_expires_then_retry_raises_invalid_credential(world)

@when("PAT 명령이 FAIL_DEVICE_CONTROL로 실패했다가 재시도에서 성공한다")
def pat_command_transient_error_then_retry_succeeds(world):
    kw.when_pat_command_transient_error_then_retry_succeeds(world)


@when("PAT 명령이 FAIL_DEVICE_CONTROL로 계속 실패한다")
def pat_command_transient_error_persists(world):
    kw.when_pat_command_transient_error_persists(world)


@when("PAT 명령이 일시적이지 않은 에러 코드로 실패한다")
def pat_command_non_transient_error(world):
    kw.when_pat_command_non_transient_error(world)


@when("PAT 명령이 FAIL_DEVICE_CONTROL로 실패했다가 재시도에서는 기기 오프라인으로 실패한다")
def pat_command_transient_then_not_connected(world):
    kw.when_pat_command_transient_then_not_connected(world)

@when("PAT 명령이 계속 실패로 응답되지만 기기에는 이미 적용되어 있다")
def pat_command_fails_but_device_applied(world):
    kw.when_pat_command_fails_but_device_actually_applied_it(world)

@when("PAT 명령이 계속 실패로 응답되고 기기에도 끝까지 적용되지 않는다")
def pat_command_fails_and_never_applied(world):
    kw.when_pat_command_fails_and_device_never_applies_it(world)


@when("PAT 명령이 실패했지만 1차 확인 시점에 이미 적용되어 있다")
def pat_command_confirmed_on_first_check(world):
    kw.when_pat_command_fails_once_then_device_state_confirms_after_retry(world)


@when("PAT 명령이 재전송되어야만 실제로 적용된다")
def pat_command_needs_resend(world):
    kw.when_pat_command_needs_actual_resend_to_succeed(world)  

@when("이 에어컨의 hvac_mode를 냉방으로 설정한다")
def setting_hvac_mode_to_cool(world):
    kw.when_setting_hvac_mode_to_cool(world)

@when("PAT 명령이 COMMAND_NOT_SUPPORTED_IN_POWER_OFF로 실패했다가 재시도에서 성공한다")
def pat_command_command_not_supported_then_retry_succeeds(world):
    kw.when_pat_command_fails_with_command_not_supported_in_power_off_then_retry_succeeds(world)
    
# --------------------------------------------------------------------
# Then
# --------------------------------------------------------------------


@then("코디네이터는 available 이어야 한다")
def coordinator_should_be_available(world):
    assert kw.then_coordinator_should_be_available(world)


@then("코디네이터는 unavailable 이어야 한다")
def coordinator_should_be_unavailable(world):
    assert kw.then_coordinator_should_be_unavailable(world)


@then(parsers.parse("목표 온도 스텝은 {step:g} 이어야 한다"))
def target_temperature_step_should_be(world, step):
    assert kw.then_target_temperature_step_is(world, step)


@then("climate 엔티티는 팬 모드 기능을 지원해야 한다")
def fan_mode_supported(world):
    assert kw.then_supported_features_include(world, ClimateEntityFeature.FAN_MODE)


@then("climate 엔티티는 팬 모드 기능을 지원하지 않아야 한다")
def fan_mode_not_supported(world):
    assert not kw.then_supported_features_include(world, ClimateEntityFeature.FAN_MODE)


@then("climate 엔티티는 스윙 모드 기능을 지원해야 한다")
def swing_mode_supported(world):
    assert kw.then_supported_features_include(world, ClimateEntityFeature.SWING_MODE)


@then("climate 엔티티는 스윙 모드 기능을 지원하지 않아야 한다")
def swing_mode_not_supported(world):
    assert not kw.then_supported_features_include(world, ClimateEntityFeature.SWING_MODE)


@then("PAT의 냉방 목표 온도 설정 메서드가 반올림된 값으로 호출되어야 한다")
def pat_cool_temperature_called_with_rounded_value(world):
    mock_call = world.coordinator.device.set_cool_target_temperature_c
    assert mock_call.called
    assert mock_call.call_args.args[0] == 24  # round(24.5) == 24 (banker's rounding)


@then("runtime_data의 재인증 필요 상태는 True 이어야 한다")
def reauth_needed_true(world):
    assert kw.then_runtime_data_reauth_needed_is(world, True)


@then("예외가 발생하지 않아야 한다")
def no_exception_raised(world):
    assert kw.then_no_exception_was_raised(world)


@then("표시되는 풍속은 변경 전 값 그대로여야 한다")
def fan_mode_unchanged(world):
    assert kw.then_fan_mode_unchanged(world)


@then(parsers.parse('표시되는 풍속은 "{expected}" 이어야 한다'))
def entity_fan_mode_equals(world, expected):
    assert kw.then_entity_fan_mode_equals(world, expected)


@then("표시되는 목표 온도는 변경 전 값 그대로여야 한다")
def target_temperature_unchanged(world):
    assert kw.then_target_temperature_unchanged(world)


@then("예외는 UpdateFailed 이어야 한다")
def exception_is_update_failed(world):
    assert kw.then_exception_is_instance_of(world, UpdateFailed)


@then("예외는 ConfigEntryNotReady 이어야 한다")
def exception_is_config_entry_not_ready(world):
    assert kw.then_exception_is_instance_of(world, ConfigEntryNotReady)


@then("native_value는 None이 아니어야 한다")
def native_value_not_none(world):
    assert kw.then_native_value_is_not_none(world)


@then("native_value는 None 이어야 한다")
def native_value_none(world):
    assert kw.then_native_value_is_none(world)


@then("필터 센서는 available 이어야 한다")
def filter_sensor_available(world):
    assert kw.then_filter_sensor_available(world)


@then("필터 센서는 unavailable 이어야 한다")
def filter_sensor_unavailable(world):
    assert kw.then_filter_sensor_unavailable(world)


@then("매칭 결과는 None이 아니어야 한다")
def match_result_not_none(world):
    assert kw.then_match_result_is_not_none(world)


@then("매칭 결과는 None 이어야 한다")
def match_result_none(world):
    assert kw.then_match_result_is_none(world)


@then("설정은 예외 없이 성공해야 한다")
def setup_succeeded(world):
    assert kw.then_setup_succeeded_without_exception(world)


@then("통합구성요소 재로드가 호출되어야 한다")
def reload_was_called(world):
    assert kw.then_integration_reload_was_called(world)


@then("MQTT 처리는 예외를 던지지 않아야 한다")
def mqtt_no_exception(world):
    assert kw.then_no_exception_was_raised(world)


@then("해당 코디네이터의 handle_mqtt_status가 호출되어야 한다")
def mqtt_handler_called(world):
    assert kw.then_mqtt_coordinator_handle_status_called(world)


@then("코스 폴링은 활성 상태여야 한다")
def course_polling_active(world):
    assert kw.then_course_polling_is_active(world)


@then("코스 폴링은 비활성 상태여야 한다")
def course_polling_inactive(world):
    assert kw.then_course_polling_is_inactive(world)


@then(parsers.parse('코스 표시값은 "{expected}" 이어야 한다'))
def course_data_is(world, expected):
    assert kw.then_course_data_is(world, expected)


@then(parsers.parse('코스 결과는 "{expected}" 이어야 한다'))
def course_result_equals(world, expected):
    assert kw.then_course_result_equals(world, expected)


@then("wideq poll은 호출되지 않았어야 한다")
def course_wideq_poll_not_called(world):
    assert kw.then_course_wideq_poll_not_called(world)


@then(parsers.parse('고유 ID는 "{expected}"으로 설정되어야 한다'))
def unique_id_set_to(world, expected):
    assert kw.then_flow_unique_id_was_set_to(world, expected)


@then("이미 등록된 계정인지 확인 절차가 실행되어야 한다")
def already_configured_checked(world):
    assert kw.then_flow_checked_already_configured(world)


@then("대기 중인 온도 전송 작업은 취소되어야 한다")
def pending_temperature_task_cancelled(world):
    assert kw.then_pending_temperature_task_was_cancelled(world)


@then(parsers.parse("예외는 ServiceValidationError 이어야 한다"))
def exception_is_service_validation_error(world):
    assert kw.then_exception_is_instance_of(world, ServiceValidationError)


@then("제습기의 set_dehumidifier_operation_mode가 POWER_ON으로 호출되어야 한다")
def dehumidifier_operation_mode_called_with_on(world):
    assert kw.then_dehumidifier_pat_method_called(world, "turn_on")


@then("제습기의 set_dehumidifier_operation_mode가 POWER_OFF로 호출되어야 한다")
def dehumidifier_operation_mode_called_with_off(world):
    assert kw.then_dehumidifier_pat_method_called(world, "turn_off")


@then("set_power_save_enabled가 True로 호출되어야 한다")
def power_save_called_with_true(world):
    assert kw.then_switch_power_save_called_with(world, True)


@then("set_power_save_enabled가 False로 호출되어야 한다")
def power_save_called_with_false(world):
    assert kw.then_switch_power_save_called_with(world, False)


@then(parsers.parse("코디네이터의 현재 온도는 {expected:g} 이어야 한다"))
def coordinator_current_temperature_is(world, expected):
    assert kw.then_coordinator_current_temperature_is(world, expected)


@then("wideq 결과는 True 이어야 한다")
def wideq_result_true(world):
    assert kw.then_wideq_result_is_true(world)


@then("wideq 결과는 False 이어야 한다")
def wideq_result_false(world):
    assert kw.then_wideq_result_is_false(world)


@then(parsers.parse("wideq 호출 횟수는 {expected:d} 이어야 한다"))
def wideq_call_count_is(world, expected):
    assert kw.then_wideq_call_count_is(world, expected)


@then("재인증 필요 센서는 꺼져 있어야 한다")
def binary_sensor_off(world):
    assert kw.then_binary_sensor_is_off(world)


@then("재인증 필요 센서는 켜져 있어야 한다")
def binary_sensor_on(world):
    assert kw.then_binary_sensor_is_on(world)


@then("재인증 필요 센서의 안내 속성은 없어야 한다")
def binary_sensor_attributes_absent(world):
    assert kw.then_binary_sensor_attributes_absent(world)


@then("재인증 필요 센서의 안내 속성이 채워져 있어야 한다")
def binary_sensor_attributes_present(world):
    assert kw.then_binary_sensor_attributes_present(world)


@then(parsers.parse("구독 실패 개수는 {expected:d} 이어야 한다"))
def subscribe_failure_count_is(world, expected):
    assert kw.then_subscribe_failure_count_is(world, expected)


@then(parsers.parse("MQTT 연결 결과는 {expected} 이어야 한다"))
def mqtt_connect_result_is(world, expected):
    assert kw.then_mqtt_connect_result_is(world, expected == "True")


@then(parsers.parse("thinq_api의 {method_name}는 {expected:d} 번 호출되어야 한다"))
def thinq_api_method_called_times(world, method_name, expected):
    assert kw.then_thinq_api_method_called_times(world, method_name, expected)


@then("MQTT 클라이언트의 async_connect_mqtt가 호출되어야 한다")
def mqtt_client_connect_mqtt_called(world):
    assert kw.then_mqtt_client_connect_mqtt_called(world)


@then("MQTT 클라이언트의 async_disconnect가 호출되어야 한다")
def mqtt_client_disconnect_called(world):
    assert kw.then_mqtt_client_disconnect_called(world)


@then("코스 센서는 None 이어야 한다")
def course_sensor_is_none(world):
    assert kw.then_course_sensor_is_none(world)


@then("코스 센서는 None이 아니어야 한다")
def course_sensor_is_not_none(world):
    assert kw.then_course_sensor_is_not_none(world)


@then("세탁기 wideq 기기가 등록되어야 한다")
def washer_wideq_device_registered(world):
    assert kw.then_washer_wideq_device_registered(world)

@then(parsers.parse('복원된 풍속은 "{expected}" 이어야 한다'))
def entity_fan_mode_is(world, expected):
    assert kw.then_entity_fan_mode_is(world, expected)


@then("복원된 풍속은 None 이어야 한다")
def entity_fan_mode_is_none(world):
    assert kw.then_entity_fan_mode_is(world, None)


@then(parsers.parse('복원된 스윙 모드는 "{expected}" 이어야 한다'))
def entity_swing_mode_is(world, expected):
    assert kw.then_entity_swing_mode_is(world, expected)


@then(parsers.parse("복원된 목표 온도는 {expected:g} 이어야 한다"))
def entity_target_temperature_is(world, expected):
    assert kw.then_entity_target_temperature_is(world, expected)


@then("복원된 목표 온도는 None 이어야 한다")
def entity_target_temperature_is_none(world):
    assert kw.then_entity_target_temperature_is(world, None)


@then("제습기는 켜져 있어야 한다")
def dehumidifier_is_on(world):
    assert kw.then_dehumidifier_is_on(world, True)


@then(parsers.parse('제습기 모드는 "{expected}" 이어야 한다'))
def dehumidifier_mode_is(world, expected):
    assert kw.then_dehumidifier_mode_is(world, expected)


@then(parsers.parse("제습기 현재 습도는 {expected:d} 이어야 한다"))
def dehumidifier_current_humidity_is(world, expected):
    assert kw.then_dehumidifier_current_humidity_is(world, expected)


@then(parsers.parse("제습기 목표 습도는 {expected:d} 이어야 한다"))
def dehumidifier_target_humidity_is(world, expected):
    assert kw.then_dehumidifier_target_humidity_is(world, expected)


@then("제습기 동작 상태는 건조 중이어야 한다")
def dehumidifier_action_drying(world):
    assert kw.then_dehumidifier_action_is_drying(world)


@then(parsers.parse("제습기 습도 범위는 {expected_min:d} 이상 {expected_max:d} 이하이어야 한다"))
def dehumidifier_humidity_range_is(world, expected_min, expected_max):
    assert kw.then_dehumidifier_humidity_range_is(world, expected_min, expected_max)


@then("스위치는 꺼져 있어야 한다")
def switch_is_off(world):
    assert kw.then_switch_is_on(world, False)


@then("PAT 기기 발견 결과는 빈 목록이어야 한다")
def pat_discovery_result_empty(world):
    assert world.result == []


@then("PAT 기기 발견 결과에는 지원 기기만 남아야 한다")
def pat_discovery_result_filtered(world):
    assert len(world.result) == 1
    assert world.result[0]["deviceId"] == "ac-1"


@then("생성된 기기는 None 이어야 한다")
def built_device_is_none(world):
    assert kw.then_built_device_is_none(world)


@then("생성된 기기는 None이 아니어야 한다")
def built_device_is_not_none(world):
    assert kw.then_built_device_is_not_none(world)

@then(parsers.parse('표시되는 스윙 모드는 "{expected}" 이어야 한다'))
def entity_swing_mode_equals(world, expected):
    assert kw.then_entity_swing_mode_equals(world, expected)

@then(parsers.parse("PAT 호출 횟수는 {expected:d} 이어야 한다"))
def pat_call_count_is(world, expected):
    assert kw.then_pat_call_count_is(world, expected)

@then(parsers.parse('수평 스텝 메서드가 "{expected}"로 호출되어야 한다'))
def fan_swing_device_horizontal_step_called_with(world, expected):
    assert kw.then_fan_swing_device_horizontal_step_called_with(world, expected)

@then("전원과 모드가 하나의 명령으로 함께 전송되어야 한다")
def power_and_job_mode_sent_atomically(world):
    assert kw.then_power_and_job_mode_sent_atomically(world)


@then("예전처럼 전원과 모드를 따로 호출하지 않아야 한다")
def separate_power_and_mode_calls_not_used(world):
    assert kw.then_separate_power_and_mode_calls_not_used(world)
