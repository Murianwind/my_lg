# -*- coding: utf-8 -*-
Feature: 에어컨 climate 엔티티의 재시작 후 상태 복원 (RestoreEntity)
  fan_mode/swing_mode/target_temperature는 전부 wideq write-only라서
  읽어올 방법이 없다. HA가 재시작되면 에어컨 자체는 계속 이전 설정으로
  돌아가고 있는데도, 이 복원 로직이 없으면(또는 깨지면) 화면에는 값이
  텅 비어 보인다. 실제로 이런 문제를 고치려고 만든 로직인데 지금까지
  검증이 없었다.

  Scenario: 이전 상태가 있으면 팬모드/스윙모드/온도가 그대로 복원된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When 이전 상태(풍속 SPEED_1, 스윙 STEP_0, 온도 24.5)로 복원된다
    Then 복원된 풍속은 "SPEED_1" 이어야 한다
    And 복원된 스윙 모드는 "STEP_0" 이어야 한다
    And 복원된 목표 온도는 24.5 이어야 한다

  Scenario: 이전 상태 자체가 없으면(최초 실행) 아무 것도 복원되지 않는다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When 이전 상태 없이 복원이 시도된다
    Then 복원된 풍속은 None 이어야 한다

  Scenario: 복원하려는 풍속이 지금 지원 목록에 없으면 무시된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When 이전 상태(풍속 SPEED_99, 스윙 없음, 온도 없음)로 복원된다
    Then 복원된 풍속은 None 이어야 한다

  Scenario: 복원하려는 온도 값이 숫자로 변환되지 않으면 예외 없이 무시된다
    Given 정상 상태(POWER_ON, COOL)의 에어컨 PAT 코디네이터가 있다
    And wideq 팬/스윙 연동 기기(풍속 2단계, 수직 스텝 2단계)가 있다
    And 이 코디네이터와 wideq 기기로 climate 엔티티를 만든다
    When 이전 상태(풍속 없음, 스윙 없음, 온도 이상한값)로 복원된다
    Then 예외가 발생하지 않아야 한다
    And 복원된 목표 온도는 None 이어야 한다
