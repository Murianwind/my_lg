# -*- coding: utf-8 -*-
Feature: wideq 재인증 필요 센서 (binary_sensor.py)
  wideq_reauth_needed 플래그 자체는 여러 시나리오에서 이미 검증했지만,
  그걸 사용자에게 노출하는 WideqReauthNeededSensor 엔티티는 한 번도
  직접 인스턴스화해본 적이 없었다. 여기가 깨지면 재인증 필요 알림
  자동화 전체가 조용히 무력화된다.

  Scenario: 재인증이 필요 없으면 센서는 꺼져 있고 안내 속성도 없다
    Given 빈 runtime_data가 있다
    And 이 runtime_data로 재인증 필요 센서를 만든다
    Then 재인증 필요 센서는 꺼져 있어야 한다
    And 재인증 필요 센서의 안내 속성은 없어야 한다

  Scenario: 재인증이 필요하면 센서가 켜지고 안내 속성이 채워진다
    Given 빈 runtime_data가 있다
    And 이 runtime_data로 재인증 필요 센서를 만든다
    When runtime_data에 재인증이 필요하다고 표시한다
    Then 재인증 필요 센서는 켜져 있어야 한다
    And 재인증 필요 센서의 안내 속성이 채워져 있어야 한다
