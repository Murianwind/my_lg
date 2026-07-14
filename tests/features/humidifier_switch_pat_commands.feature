# -*- coding: utf-8 -*-
Feature: 제습기·에너지 절약 스위치의 PAT 명령 경로 (공통 헬퍼 검증)
  humidifier.py와 switch.py는 PatCoordinatorEntity.async_send_pat_command
  라는 공통 헬퍼를 거쳐 PAT 명령을 보낸다. 이 헬퍼 자체(NOT_CONNECTED_DEVICE
  처리, 재시도 없음, 성공 시 갱신)는 climate.py 시나리오로 이미 검증했지만,
  humidifier/switch가 실제로 이 헬퍼를 올바르게 호출하는지는 별도로
  확인되지 않았었다.

  Scenario: 제습기 전원을 켜면 PAT 명령이 POWER_ON으로 전송된다
    Given 정상 상태의 제습기 엔티티가 있다
    When 제습기의 turn_on 동작을 호출한다
    Then 제습기의 set_dehumidifier_operation_mode가 POWER_ON으로 호출되어야 한다

  Scenario: 제습기 전원을 끄면 PAT 명령이 POWER_OFF로 전송된다
    Given 정상 상태의 제습기 엔티티가 있다
    When 제습기의 turn_off 동작을 호출한다
    Then 제습기의 set_dehumidifier_operation_mode가 POWER_OFF로 호출되어야 한다

  Scenario: 제습기 명령이 NOT_CONNECTED_DEVICE로 실패하면 예외 없이 처리된다
    Given 정상 상태의 제습기 엔티티가 있다
    When 제습기의 turn_on 동작이 NOT_CONNECTED_DEVICE로 실패한다
    Then 예외가 발생하지 않아야 한다
    And 코디네이터는 unavailable 이어야 한다

  Scenario: 제습기 명령이 다른 에러로 실패하면 ServiceValidationError가 발생한다
    Given 정상 상태의 제습기 엔티티가 있다
    When 제습기의 set_humidity 동작이 INVALID_COMMAND_ERROR로 실패한다
    Then 예외는 ServiceValidationError 이어야 한다

  Scenario: 에너지 절약을 켜면 PAT 명령이 True로 전송된다
    Given 정상 상태의 에너지 절약 스위치 엔티티가 있다
    When 스위치의 turn_on 동작을 호출한다
    Then set_power_save_enabled가 True로 호출되어야 한다

  Scenario: 에너지 절약을 끄면 PAT 명령이 False로 전송된다
    Given 정상 상태의 에너지 절약 스위치 엔티티가 있다
    When 스위치의 turn_off 동작을 호출한다
    Then set_power_save_enabled가 False로 호출되어야 한다

  Scenario: 스위치 명령이 NOT_CONNECTED_DEVICE로 실패하면 예외 없이 처리된다
    Given 정상 상태의 에너지 절약 스위치 엔티티가 있다
    When 스위치의 turn_on 동작이 NOT_CONNECTED_DEVICE로 실패한다
    Then 예외가 발생하지 않아야 한다
    And 코디네이터는 unavailable 이어야 한다

  Scenario: 스위치 명령이 다른 에러로 실패하면 ServiceValidationError가 발생한다
    Given 정상 상태의 에너지 절약 스위치 엔티티가 있다
    When 스위치의 turn_on 동작이 COMMAND_NOT_SUPPORTED_IN_MODE로 실패한다
    Then 예외는 ServiceValidationError 이어야 한다
