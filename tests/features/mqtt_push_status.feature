# -*- coding: utf-8 -*-
Feature: MQTT push 상태 반영 (coordinator_pat.py의 handle_mqtt_status)
  LG 서버가 기기 상태 변화를 push할 때마다 실행되는, 실행 빈도가 가장
  높은 코드다. 여기가 깨지면 화면에 조용히 오래된 값만 계속 보인다.

  Scenario: MQTT push로 온도가 갱신되면 코디네이터에 반영되고 available해진다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And 이 기기에 보낸 명령이 오프라인으로 실패한다
    When MQTT push로 현재 온도 27.5가 도착한다
    Then 코디네이터의 현재 온도는 27.5 이어야 한다
    And 코디네이터는 available 이어야 한다

  Scenario: 빈 MQTT push 페이로드는 크래시 없이 무시된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    When 빈 MQTT push 페이로드가 도착한다
    Then 예외가 발생하지 않아야 한다
