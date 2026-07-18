# -*- coding: utf-8 -*-
Feature: 꺼진 에어컨을 켤 때 전원 켜기와 모드 전환, 그리고 hvac_mode 표시
  실제 로그에서 두 가지가 각각 확인됐다:
  1) 전원+모드를 한 요청에 같이 보내도 PAT 서버가
     COMMAND_NOT_SUPPORTED_IN_POWER_OFF로 거부하는 경우가 있어서, 전원을
     먼저 보내고 안정화 대기 후 모드를 보내는 순차 전송으로 되돌렸다.
  2) 순차 전송으로 되돌리면 원래 문제(operation_mode/job_mode가 서로
     다른 시점에 갱신되면서 hvac_mode가 잠깐 엉뚱하게 조합되는 것,
     예: 냉방으로 켜는 순간 잠깐 송풍으로 보이는 것)가 다시 생기므로,
     명령을 보낸 뒤 잠깐은 요청한 값을 그대로 보여주는 낙관적 표시
     창으로 이걸 막는다.

  Scenario: 꺼진 에어컨을 켜면 전원 켜기와 모드 전환이 순차적으로 전송된다
    Given 전원이 꺼져 있고 이전 모드가 송풍(FAN)으로 남아있는 에어컨 코디네이터가 있다
    When 이 에어컨의 hvac_mode를 냉방으로 설정한다
    Then 전원 켜기와 모드 전환이 각각 순차적으로 전송되어야 한다

  Scenario: 이미 켜져 있으면 전원 켜기 없이 모드만 바로 전송된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 기기 없이 climate 엔티티를 만든다
    When 이미 켜져 있는 상태에서 hvac_mode를 다른 모드로 바꾼다
    Then 전원 켜기 명령은 전송되지 않아야 한다

  Scenario: 명령을 보낸 직후엔 아직 반영 전이어도 요청한 모드가 그대로 표시된다
    Given 전원이 꺼져 있고 이전 모드가 송풍(FAN)으로 남아있는 에어컨 코디네이터가 있다
    When 이 에어컨의 hvac_mode를 냉방으로 설정한다
    And 이 시점에 hvac_mode를 읽는다
    Then 표시된 hvac_mode는 "cool" 이어야 한다

  Scenario: 명령이 최종적으로 실패하면 낙관적 표시가 즉시 해제되고 실제 값으로 돌아간다
    Given 전원이 꺼져 있고 이전 모드가 송풍(FAN)으로 남아있는 에어컨 코디네이터가 있다
    When hvac_mode 변경을 시도했지만 최종적으로 실패한다
    Then 예외는 ServiceValidationError 이어야 한다
    And 표시된 hvac_mode는 "off" 이어야 한다
