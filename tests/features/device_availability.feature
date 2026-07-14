# -*- coding: utf-8 -*-
Feature: PAT 기기 가용성 추적
  PatDeviceCoordinator는 마지막 상태 갱신 성공 여부(last_update_success)와,
  명령 전송 실패로 알게 된 실제 연결 여부(_device_reachable)를 함께 봐서
  available을 판단해야 한다. MQTT push 구조에서는 마지막 push가 성공한
  이후 기기가 오프라인이 되어도 last_update_success만으로는 알 수 없기
  때문이다.

  Scenario: 정상 상태의 기기는 available이다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    Then 코디네이터는 available 이어야 한다

  Scenario: 명령이 NOT_CONNECTED_DEVICE로 실패하면 즉시 unavailable로 바뀐다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When 이 기기에 보낸 명령이 오프라인으로 실패한다
    Then 코디네이터는 unavailable 이어야 한다

  Scenario: 다음 상태 갱신이 성공하면 다시 available로 돌아온다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When 이 기기에 보낸 명령이 오프라인으로 실패한다
    And 상태 갱신이 성공적으로 도착한다
    Then 코디네이터는 available 이어야 한다

  Scenario: hvac_mode 변경이 NOT_CONNECTED_DEVICE로 실패해도 예외 없이 unavailable로 반영된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 기기 없이 climate 엔티티를 만든다
    When PAT 전원 제어가 NOT_CONNECTED_DEVICE로 실패하는 상태에서 hvac_mode를 off로 설정한다
    Then 예외가 발생하지 않아야 한다
    And 코디네이터는 unavailable 이어야 한다
