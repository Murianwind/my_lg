# -*- coding: utf-8 -*-
Feature: PAT 명령의 일시적 에러 재시도 (async_send_pat_command)
  "냉방 제어" 스크립트가 climate.set_hvac_mode를 호출했을 때
  FAIL_DEVICE_CONTROL(2208)로 실패해서 자동화가 중단되는 실제 사례가
  있었다. 기기가 직전 명령을 처리 중이라 잠깐 거절하는 경우가
  대부분이라, wideq 엔진과 동일하게 한 번 재시도하도록 만들었다.

  Scenario: FAIL_DEVICE_CONTROL로 실패했다가 재시도에서 성공하면 예외 없이 처리된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When PAT 명령이 FAIL_DEVICE_CONTROL로 실패했다가 재시도에서 성공한다
    Then 예외가 발생하지 않아야 한다

  Scenario: FAIL_DEVICE_CONTROL이 재시도에서도 계속되면 ServiceValidationError가 발생한다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When PAT 명령이 FAIL_DEVICE_CONTROL로 계속 실패한다
    Then 예외는 ServiceValidationError 이어야 한다

  Scenario: 일시적이지 않은 에러 코드는 재시도 없이 즉시 실패한다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When PAT 명령이 일시적이지 않은 에러 코드로 실패한다
    Then 예외는 ServiceValidationError 이어야 한다
    And PAT 호출 횟수는 1 이어야 한다

  Scenario: 첫 시도는 FAIL_DEVICE_CONTROL, 재시도는 기기 오프라인이면 예외 없이 unavailable로 처리된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When PAT 명령이 FAIL_DEVICE_CONTROL로 실패했다가 재시도에서는 기기 오프라인으로 실패한다
    Then 예외가 발생하지 않아야 한다
    And 코디네이터는 unavailable 이어야 한다
